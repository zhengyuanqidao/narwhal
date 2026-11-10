#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wiki_version.py —— 知识库增量生产与版本管理（零依赖）

解决问题：存量不重跑。每次交付只处理「新增 / 修改 / 删除」的部分，
并给每次交付一个可引用的版本号。

数据模型（.narwhal/state.json）：
  version    当前版本号（semver）
  sources    raw/ 下每份源材料的 sha256（用于判增删改）
  entries    条目快照（sha256 + derived_from + status）
  compiled   编译产物快照（sha256 + 依赖条目哈希）
  archive    墓碑：已删除源材料的记录（raw 不可变，删除只登记不销毁）

命令：
  init                      建立基线快照（首次交付时跑）
  diff                      对比当前树与快照，输出增量清单（不改任何文件）
  bump patch|minor|major    版本号 +1，把本次增量写进 CHANGELOG.md
  status                    显示版本、待处理项、stale 条目

设计原则：
1. **raw 不可变**：源文件哈希变了 = 违规（应新增版本文件而非原地改），直接报 VIOLATION；
2. **删除不销毁**：源材料消失只登记墓碑，其派生条目转为 stale 交人判断，绝不自动删；
3. **人改不覆盖**：条目哈希与快照不符 = 人手动改过，标记 human-edit，agent 不得重写；
4. **编译按依赖**：编译产物记录所依赖条目的哈希，依赖未变则跳过重编译。
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

STATE_DIR = ".narwhal"
STATE_FILE = "state.json"
CHANGELOG = "CHANGELOG.md"
VERSION_FILE = "VERSION"

EXCLUDE_DIRS = {"graph", STATE_DIR, ".git", "exports"}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------- 三级指纹 ----------
# 为什么不用 md5：md5 与 sha256 在"是否变化"上行为完全一致（都是全有或全无），
# 只是 md5 抗碰撞更弱、且快的那一点在本项目规模（<1000 文件）毫无意义。
# 真正的问题不是哈希算法，而是**粒度**：整文件哈希对"改几个字"的判定是
# "完全不同"，据此重跑整条 = 误判。所以要三层：
#   L1 sha256   → 是否变化（快路径）
#   L2 块哈希   → 变化在哪几段（定位重算范围）
#   L3 SimHash  → 是否同一份东西搬家/近似（容忍微改）

def split_blocks(text: str):
    """按空行切段（Markdown 的自然块）。"""
    return [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]


def simhash(text: str, bits: int = 64) -> int:
    """字符 3-gram SimHash，用于近似重复/重命名检测。"""
    grams = [text[i:i + 3] for i in range(max(1, len(text) - 2))]
    if not grams:
        return 0
    v = [0] * bits
    for g in grams:
        hv = int(hashlib.md5(g.encode()).hexdigest(), 16)
        for i in range(bits):
            v[i] += 1 if (hv >> i) & 1 else -1
    out = 0
    for i in range(bits):
        if v[i] > 0:
            out |= 1 << i
    return out


def minhash(text: str, k: int = 48, n: int = 3) -> list:
    """MinHash 草图：取 3-gram 哈希中最小的 k 个。

    用途：估算两份文本的 Jaccard 相似度，**对"改几个字"不敏感**——
    这是块哈希做不到的（一个字符变了，整段哈希就全变）。
    存储成本：k 个整数 ≈ 300 字节/条目。
    """
    grams = {text[i:i + n] for i in range(max(1, len(text) - n + 1))}
    hs = sorted({int(hashlib.md5(g.encode()).hexdigest()[:8], 16) for g in grams})[:k]
    return hs


def jaccard(a: list, b: list) -> float:
    """MinHash 的 Jaccard 估计：交集/并集（基于各自的 k 个最小哈希）。"""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


def fingerprints(text: str) -> dict:
    bs = split_blocks(text)
    return {
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "blocks": [hashlib.sha256(b.encode()).hexdigest()[:16] for b in bs],
        "chars": len(text),
        "simhash": simhash(text),
        "mh": minhash(text),
    }


def compare(old: dict, new: dict) -> dict:
    """对比两份指纹，给出"改动幅度 + 变化块数"。

    近似指标（不读旧正文，只靠块哈希交集）：
      coverage = 未变块字符数 / 新文件字符数
    """
    old_blocks = set(old.get("blocks", []))
    new_blocks = new.get("blocks", [])
    matched = sum(1 for b in new_blocks if b in old_blocks)
    block_cov = matched / len(new_blocks) if new_blocks else 0.0
    # 主判据用 MinHash 相似度（字符级，容忍微改）；块覆盖仅用于定位范围
    if old.get("mh") and new.get("mh"):
        sim = jaccard(old["mh"], new["mh"])
    else:
        # 向后兼容：旧快照没有 MinHash，退化为块覆盖（更严，但不至于全判重写）
        sim = block_cov
    dist = bin(old.get("simhash", 0) ^ new.get("simhash", 0)).count("1")
    return {
        "similarity": sim,
        "block_cov": block_cov,
        "changed_blocks": len(new_blocks) - matched,
        "total_blocks": len(new_blocks),
        "hamming": dist,
        "kind": ("微调" if sim >= 0.90 else
                 "部分重写" if sim >= 0.60 else "重写"),
    }


def walk(root: Path, sub: str, exts=(".md",)):
    d = root / sub
    if not d.exists():
        return []
    out = []
    for p in sorted(d.rglob("*")):
        if p.is_dir() or any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        if exts and p.suffix.lower() not in exts:
            continue
        out.append(p.relative_to(root).as_posix())
    return out


def load_state(root: Path):
    f = root / STATE_DIR / STATE_FILE
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def save_state(root: Path, st):
    (root / STATE_DIR).mkdir(exist_ok=True)
    (root / STATE_DIR / STATE_FILE).write_text(
        json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_fm(text: str):
    """抽 frontmatter 里的关键字段（不引入 yaml 依赖）。"""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    fm = m.group(1) if m else ""
    def g(k):
        mm = re.search(rf"^{k}:\s*(.+)$", fm, re.M)
        return mm.group(1).strip().strip('"') if mm else ""
    conf = g("confidence")
    src = g("source")
    return {"confidence": conf, "source": src}


def scan(root: Path):
    """扫描当前树：源材料 + 条目/案例 + 编译产物。"""
    sources = {}
    for rel in walk(root, "raw", exts=None):
        p = root / rel
        txt = p.read_text(encoding="utf-8", errors="replace")
        fp = fingerprints(txt)
        sources[rel] = {"sha256": fp["sha256"], "size": p.stat().st_size,
                        "blocks": fp["blocks"], "chars": fp["chars"],
                        "simhash": fp["simhash"], "mh": fp["mh"]}
    entries = {}
    for sub in ("entries", "cases"):
        for rel in walk(root, sub):
            p = root / rel
            txt = p.read_text(encoding="utf-8", errors="replace")
            fm = parse_fm(txt)
            fp = fingerprints(txt)
            entries[rel] = {
                "sha256": fp["sha256"],
                "confidence": fm["confidence"],
                "source": fm["source"],
                "blocks": fp["blocks"],
                "chars": fp["chars"],
                "simhash": fp["simhash"],
                "mh": fp["mh"],
            }
    compiled = {}
    for sub in ("methods", "exports"):
        for rel in walk(root, sub):
            p = root / rel
            compiled[rel] = {"sha256": sha(p)}
    return {"sources": sources, "entries": entries, "compiled": compiled}


def _norm(s: str) -> str:
    """归一化：去掉标点/空格/括号，只留中日韩、字母、数字。"""
    return re.sub(r"[^\w\u4e00-\u9fff]", "", s).lower()


DATE_RE = re.compile(r"(20\d{2})[-年/.]?(\d{1,2})")


def _date(s: str):
    """抽 YYYY-MM 作为源材料的时间锚点。"""
    m = DATE_RE.search(s)
    return f"{m.group(1)}-{int(m.group(2)):02d}" if m else None


def _match(source: str, files) -> list:
    """把条目的 source 文本（自由书写）匹配到具体源文件路径。

    三条规则，命中任一即算匹配：
      1. 归一化后互为子串；
      2. 有 ≥8 个连续字符重合（中文 8 字已足够区分）；
      3. 日期锚点相同且该日期在源材料里唯一（"2025-07 周会决议" → 2025-07 那份纪要）。
    """
    ns = _norm(source)
    if not ns:
        return []
    hits = []
    for f in files:
        stem = _norm(Path(f).stem)
        if not stem:
            continue
        if stem in ns or ns in stem:
            hits.append(f)
            continue
        win = min(8, len(stem))
        if any(stem[i:i + win] in ns for i in range(0, max(1, len(stem) - win + 1))):
            hits.append(f)
            continue
        d_src, d_file = _date(source), _date(Path(f).name)
        if d_src and d_src == d_file:
            same_date = [x for x in files if _date(Path(x).name) == d_src]
            if len(same_date) == 1:
                hits.append(f)
    return hits


def derive_map(entries, all_sources):
    """从条目的 source 字段反推「条目 → 源材料」映射。"""
    m = {}
    for rel, meta in entries.items():
        src = meta.get("source", "")
        hits = _match(src, all_sources)
        if hits:
            m[rel] = hits
    return m


def cmd_init(root: Path, args):
    st = scan(root)
    state = {
        "version": args.version or "0.1.0",
        "updated": datetime.now().isoformat(timespec="seconds"),
        "sources": st["sources"],
        "entries": st["entries"],
        "compiled": st["compiled"],
        "archive": [],
    }
    save_state(root, state)
    (root / VERSION_FILE).write_text(state["version"] + "\n", encoding="utf-8")
    print(f"基线建立：{len(st['sources'])} 源材料 / {len(st['entries'])} 条目·案例 / "
          f"{len(st['compiled'])} 编译产物 → version {state['version']}")
    return 0


def compute_diff(root: Path, state):
    """返回增量清单（含三级指纹判定：微调 / 部分重写 / 重写）。"""
    cur = scan(root)
    old_src = state["sources"]
    old_ent = state["entries"]
    old_cmp = state.get("compiled", {})
    notes = {}   # path -> 改动幅度说明

    # ---- 源材料 ----
    src_added = [k for k in cur["sources"] if k not in old_src]
    src_removed = [k for k in old_src if k not in cur["sources"]]
    src_modified = [k for k in cur["sources"]
                    if k in old_src and cur["sources"][k]["sha256"] != old_src[k]["sha256"]]
    src_kind = {}
    for k in src_modified:
        c = compare(old_src[k], cur["sources"][k])
        src_kind[k] = c["kind"]
        notes[f"SRC:{k}"] = (f'{c["kind"]}（相似度 {c["similarity"]:.0%}，'
                             f'{c["changed_blocks"]}/{c["total_blocks"]} 块变更）')

    # ---- 条目/案例 ----
    ent_added = [k for k in cur["entries"] if k not in old_ent]
    ent_removed = [k for k in old_ent if k not in cur["entries"]]
    ent_changed = [k for k in cur["entries"]
                   if k in old_ent and cur["entries"][k]["sha256"] != old_ent[k]["sha256"]]
    for k in ent_changed:
        c = compare(old_ent[k], cur["entries"][k])
        notes[k] = (f'{c["kind"]}（相似度 {c["similarity"]:.0%}，'
                    f'{c["changed_blocks"]}/{c["total_blocks"]} 块变更）')

    # 重命名识别：新增文件与删除文件 SimHash 距离 ≤3 视为同一份搬家
    renames = []
    for a in list(ent_added):
        for r in list(ent_removed):
            d = bin(cur["entries"][a].get("simhash", 0) ^ old_ent[r].get("simhash", 0)).count("1")
            if d <= 3:
                renames.append((r, a, d))
                ent_added.remove(a)
                ent_removed.remove(r)
                notes[f"RENAME:{a}"] = f"重命名（自 {Path(r).name}，SimHash 距离 {d}）"
                break

    # 条目被人改过？（哈希变了但源材料没变）
    derived = derive_map(cur["entries"], list(cur["sources"]) + src_removed)
    affected_by_src_changed = set()
    for ent, srcs in derived.items():
        if set(srcs) & set(src_modified):
            affected_by_src_changed.add(ent)
    ent_human_edit = [e for e in ent_changed if e not in affected_by_src_changed]
    # 人工改动也分级：微调（agent 应保留）vs 重写（需人确认意图）
    for e in ent_human_edit:
        c = compare(old_ent[e], cur["entries"][e])
        notes[e] = notes[e] + f" · 人工{c['kind']}"

    # 源材料被删 → 其派生条目变 stale
    stale = [ent for ent, srcs in derived.items() if set(srcs) & set(src_removed)]
    stale = sorted(set(stale) - set(ent_removed))
    for e in stale:
        hit = [s for s in derived.get(e, []) if s in src_removed]
        notes[e] = f"源已删：{Path(hit[0]).name if hit else '?'}"

    # 受影响条目：源材料变更的"严重度"决定要不要重跑
    ent_affected = sorted(affected_by_src_changed - set(ent_added) - set(ent_removed))
    for e in ent_affected:
        kinds = {src_kind.get(s) for s in derived.get(e, []) if s in src_kind}
        if "重写" in kinds or "部分重写" in kinds:
            notes[e] = "源材料实质变更 → 需重跑"
        elif "微调" in kinds:
            notes[e] = "源材料仅微调 → 建议人工确认，不必全量重跑"

    # ---- 编译产物 ----
    changed_entries = set(ent_added) | set(ent_changed) | set(ent_removed)
    stale_compiled = []
    for rel in cur["compiled"]:
        parts = Path(rel).parts
        cands = set(parts[:-1]) | {Path(rel).stem.split("-")[0].split("_")[0]}
        if any(c and any(c in e for e in changed_entries) for c in cands):
            stale_compiled.append(rel)
    cmp_added = [k for k in cur["compiled"] if k not in old_cmp]
    stale_compiled = [x for x in stale_compiled if x not in cmp_added]

    return {
        "notes": notes, "renames": renames, "src_kind": src_kind,
        "ent_affected": ent_affected,
        "src_added": src_added, "src_modified": src_modified, "src_removed": src_removed,
        "ent_added": ent_added, "ent_changed": ent_changed, "ent_removed": ent_removed,
        "ent_human_edit": ent_human_edit, "stale": stale,
        "stale_compiled": stale_compiled, "cmp_added": cmp_added,
        "snapshot": cur,
    }


def print_diff(d, root: Path):
    notes = d.get("notes", {})

    def sec(title, items, note="", key_prefix=""):
        if items:
            print(f"  {title}（{len(items)}）")
            for i in items[:20]:
                extra = notes.get(key_prefix + i, "")
                print(f"    - {i}" + (f"   {extra}" if extra else ""))
            if len(items) > 20:
                print(f"    … 另有 {len(items)-20} 项")
        elif note:
            print(f"  {title}  无")

    print("【增量清单】")
    sec("源材料 新增", d["src_added"], "无")
    sec("源材料 修改", d["src_modified"], "无", key_prefix="SRC:")
    if d["src_modified"]:
        print("    ⚠ VIOLATION：raw 应不可变。正确做法是新增一份带版本后缀的源文件，")
        print("      并在条目 source 里注明；原地修改会破坏溯源与防搬运指纹检测。")
    sec("源材料 删除", d["src_removed"], "无")
    sec("条目 新增", d["ent_added"], "无")
    sec("条目 内容变化（源材料驱动）", [e for e in d["ent_changed"] if e not in d["ent_human_edit"]], "无")
    sec("条目 受源材料变更影响 → 需重新生成", d["ent_affected"], "无")
    sec("条目 疑似人工修改（agent 不得覆盖）", d["ent_human_edit"], "无")
    if d["renames"]:
        print(f"  条目 重命名识别（{len(d['renames'])}）")
        for old, new, dist in d["renames"]:
            print(f"    - {Path(old).name} → {Path(new).name}   SimHash 距离 {dist}")
    sec("条目 删除", d["ent_removed"], "无")
    sec("条目 转 stale（源材料已删，需人工判断保留/归档）", d["stale"], "无")
    sec("编译产物 需重编译", d["stale_compiled"], "无")
    sec("编译产物 新增", d["cmp_added"], "无")

    total = (len(d["src_added"]) + len(d["ent_affected"]) + len(d["ent_added"])
             + len(d["ent_changed"]) + len(d["stale_compiled"]))
    n_all = len(d["snapshot"]["entries"])
    reuse = n_all - len(set(d["ent_added"]) | set(d["ent_changed"]) | set(d["ent_affected"]))
    print(f"\n【工作量估算】需处理 {total} 项；存量 {n_all} 条目中 {reuse} 条无需重跑"
          f"（复用率 {reuse / n_all * 100:.0f}%）。")


def cmd_diff(root: Path, args):
    state = load_state(root)
    if not state:
        print("尚未建立基线，先跑：wiki_version.py init", file=sys.stderr)
        return 2
    d = compute_diff(root, state)
    print(f"当前版本 {state['version']}（上次快照 {state['updated']}）\n")
    print_diff(d, root)
    return 0


def cmd_bump(root: Path, args):
    state = load_state(root)
    if not state:
        print("尚未建立基线，先跑：wiki_version.py init", file=sys.stderr)
        return 2
    d = compute_diff(root, state)
    ver = tuple(int(x) for x in state["version"].split("."))
    major, minor, patch = ver
    if args.part == "major":
        major, minor, patch = major + 1, 0, 0
    elif args.part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    new_ver = f"{major}.{minor}.{patch}"

    head = f"## v{new_ver} — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    bullets = []
    pairs = [
        ("源材料新增", d["src_added"]), ("源材料修改", d["src_modified"]),
        ("源材料删除", d["src_removed"]), ("新增条目/案例", d["ent_added"]),
        ("更新条目/案例", [e for e in d["ent_changed"] if e not in d["ent_human_edit"]]),
        ("受源材料变更影响重跑", d["ent_affected"]),
        ("人工修改条目（保留）", d["ent_human_edit"]),
        ("删除条目/案例", d["ent_removed"]), ("转 stale", d["stale"]),
        ("重编译产物", d["stale_compiled"]),
        ("新增编译产物", d["cmp_added"]),
    ]
    for title, items in pairs:
        if items:
            bullet = (f"- **{title}**（{len(items)}）："
                      + "、".join(f"`{Path(i).name}`" for i in items[:12]))
            if len(items) > 12:
                bullet += f" 等 {len(items)} 项"
            bullets.append(bullet)
    if d.get("renames"):
        bullets.append("- **重命名**（%d）：" % len(d["renames"]) +
                       "、".join(f"`{Path(o).name}`→`{Path(n).name}`"
                                 for o, n, _ in d["renames"][:6]))
    if not bullets:
        bullets.append("- 无内容变更，仅版本号推进")

    cl = root / CHANGELOG
    old = cl.read_text(encoding="utf-8") if cl.exists() else "# 知识库变更日志"
    block = "\n\n" + head
    if args.note:
        block += "\n\n" + args.note
    block += "\n\n" + "\n".join(bullets) + "\n"
    cl.write_text(old.rstrip() + block, encoding="utf-8")
    (root / VERSION_FILE).write_text(new_ver + "\n", encoding="utf-8")

    state["version"] = new_ver
    state["updated"] = datetime.now().isoformat(timespec="seconds")
    state["sources"] = d["snapshot"]["sources"]
    state["entries"] = d["snapshot"]["entries"]
    state["compiled"] = d["snapshot"]["compiled"]
    for r in d["src_removed"]:
        state["archive"].append({"path": r, "removed_at": state["updated"]})
    save_state(root, state)
    print(f"版本推进：{new_ver}  已写入 {CHANGELOG}")
    return 0


def cmd_status(root: Path, args):
    state = load_state(root)
    if not state:
        print("尚未建立基线，先跑：wiki_version.py init", file=sys.stderr)
        return 2
    d = compute_diff(root, state)
    pending = (len(d["src_added"]) + len(d["ent_added"]) + len(d["ent_changed"])
               + len(d["stale_compiled"]))
    print(f"版本 {state['version']}  |  快照 {state['updated']}")
    print(f"源材料 {len(state['sources'])}  条目/案例 {len(state['entries'])}  "
          f"编译产物 {len(state.get('compiled', {}))}  墓碑 {len(state['archive'])}")
    print(f"待处理增量 {pending} 项" + ("（干净）" if pending == 0 else ""))
    if d["stale"]:
        print(f"stale 条目 {len(d['stale'])} 条，待人工判断：" + "、".join(Path(x).name for x in d["stale"][:5]))
    return 0


def main():
    ap = argparse.ArgumentParser(description="知识库增量生产与版本管理")
    ap.add_argument("root", help="知识库根目录")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="建立基线快照")
    p_init.add_argument("--version", default=None, help="初始版本号，默认 0.1.0")
    p_init.set_defaults(func=cmd_init)

    p_diff = sub.add_parser("diff", help="输出增量清单")
    p_diff.set_defaults(func=cmd_diff)

    p_bump = sub.add_parser("bump", help="推进版本号并记录 CHANGELOG")
    p_bump.add_argument("part", choices=["patch", "minor", "major"])
    p_bump.add_argument("--note", default="")
    p_bump.set_defaults(func=cmd_bump)

    p_st = sub.add_parser("status", help="版本与待办概览")
    p_st.set_defaults(func=cmd_status)

    args = ap.parse_args()
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"目录不存在：{root}", file=sys.stderr)
        return 2
    return args.func(root, args)


if __name__ == "__main__":
    sys.exit(main())
