#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内容层验收报告（B 端交付用）。

回答一个问题：这份知识库，能不能作为交付物签字？
指标全部是**内容层**的——不涉及向量库、权限、响应时间（那些属于系统层，由总包负责）。

五项指标：
  1. 覆盖率    源文档二级标题块中，被条目覆盖的比例        —— 证明没漏料
  2. 溯源率    条目里的数字能在源文档找到的比例            —— 证明没编造
  3. 孤儿条目率 无任何入链的条目占比                        —— 证明结构连通
  4. 重复率    近似重复（MinHash Jaccard ≥ 阈值）条目占比   —— 证明去了重
  5. 反例密度  含「适用边界/反例」小节的条目占比            —— 证明不是复述文档

用法：
    python3 report.py <wiki根目录> [--src <源目录或文件>] [--json]

退出码：0 全部达标；1 有指标未达标（便于 CI/交付前闸门）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

FRONT = re.compile(r"^---\n(.*?)\n---", re.S)
H2 = re.compile(r"^##\s+(.+)$", re.M)
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
NUM = re.compile(r"(?:¥\s?(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:元|个|%|款|家|单|次|万|份|条))")
CN = re.compile(r"[\u4e00-\u9fa5]")
# 结构性章节（目录/致谢/参考/附录等）不计入覆盖率分母——
# 它们不是知识单元，若计入会让任何含目录页的真实文档永远无法达标。
STRUCT_RE = re.compile(
    r"目录|contents|contributors?|致谢|acknowledg|references?|参考文献|"
    r"附录|appendix|changelog|更新日志|other lists|相关阅读|延伸阅读|索引",
    re.I,
)

# 阈值（写进交付合同的判据）
THRESHOLDS = {
    "coverage": ("ge", 0.70),      # 覆盖率 ≥ 70%
    "traceability": ("ge", 0.98),  # 溯源率 ≥ 98%
    "orphan": ("le", 0.20),        # 孤儿率 ≤ 20%
    "duplicate": ("le", 0.10),     # 重复率 ≤ 10%
    "counter_example": ("ge", 0.80),  # 反例密度 ≥ 80%
}
DUP_JACCARD = 0.50


# ---------- 读取 ----------
def parse_fm(text: str) -> dict:
    m = FRONT.search(text)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("-"):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def minhash(text: str, k: int = 48, n: int = 3) -> list:
    grams = {text[i:i + n] for i in range(max(1, len(text) - n + 1))}
    return sorted({int(hashlib.md5(g.encode()).hexdigest()[:8], 16) for g in grams})[:k]


def jaccard(a: list, b: list) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


EN_STOP = {"with", "that", "this", "from", "when", "were", "have", "been", "into", "over",
           "their", "there", "which", "would", "could", "after", "before", "during",
           "because", "about", "other", "these", "those", "while", "under", "where"}


def features(s: str) -> set:
    """取匹配特征：英文取词（长度≥4、去停用词），中文取中文字符 2-gram，两者并集。

    为什么要分开：英文的字符 2-gram（at/te/or）在任何英文文本里都出现，
    匹配率恒为 1，等于没有判别力；而中文没有词边界，2-gram 才是有意义的近似。
    注意两边的字符集必须隔离——否则英文会被拼进中文 2-gram 产生噪声，
    中文标题也会因缺少英文词而匹配不到混合语料。
    """
    en = set(re.findall(r"[A-Za-z]{4,}", s.lower())) - EN_STOP
    cn_text = "".join(re.findall(r"[\u4e00-\u9fa5]+", s))
    cn = {cn_text[i:i + 2] for i in range(len(cn_text) - 1)}
    return en | cn


# ---------- 指标 ----------
def load_entries(root: Path):
    d = root / "entries"
    out = []
    if not d.exists():
        return out
    for p in sorted(d.rglob("*.md")):
        t = p.read_text(encoding="utf-8")
        out.append({
            "name": p.stem,
            "fm": parse_fm(t),
            "body": FRONT.sub("", t).strip(),
            "text": t,
        })
    return out


def load_sources(root: Path, src_arg: str | None):
    if src_arg:
        p = Path(src_arg)
        files = [p] if p.is_file() else sorted(p.rglob("*.md"))
    else:
        raw = root / "raw"
        files = sorted(raw.rglob("*.md")) if raw.exists() else []
    return [(f, f.read_text(encoding="utf-8")) for f in files]


def metric_coverage(sources, entries) -> tuple[float, dict]:
    """源文档二级标题块 → 是否被条目正文/标题覆盖（标题 2-gram 命中 ≥40%）。"""
    if not sources:
        return 0.0, {"note": "未找到源文档，覆盖率记 0（请在 wiki 根放 raw/ 或用 --src）"}
    corpus = "\n".join(e["text"] for e in entries)
    total = covered = 0
    missed = []
    skipped = []
    for f, text in sources:
        blocks = H2.findall(text)
        if not blocks:  # 无二级标题则整篇算 1 块，用首行标题
            first = next((l.strip("# ").strip() for l in text.splitlines() if l.startswith("#")), f.stem)
            blocks = [first]
        for b in blocks:
            if STRUCT_RE.search(b):  # 结构性章节不计入分母
                skipped.append(b.strip()[:30])
                continue
            total += 1
            g = features(b)
            if not g:
                covered += 1
                continue
            hit = len(g & features(corpus)) / len(g)
            if hit >= 0.40:
                covered += 1
            else:
                missed.append(f"{f.name} → ## {b.strip()[:40]}")
    ratio = covered / total if total else 0.0
    return ratio, {"blocks": total, "covered": covered,
                   "excluded_sections": skipped, "missed_sample": missed[:8]}


def metric_traceability(sources, entries) -> tuple[float, dict]:
    """条目中的数字 token，能在源文档找到的比例。"""
    if not sources:
        return 0.0, {"note": "无源文档，无法核对溯源"}
    src = "\n".join(t for _, t in sources).replace(",", "")
    total = ok = 0
    bad = []
    for e in entries:
        for m in NUM.finditer(e["body"]):
            v = m.group(1) or m.group(2)
            total += 1
            if v in src or v.rstrip("0").rstrip(".") in src:
                ok += 1
            else:
                bad.append(f"{e['name']}: {v}")
    ratio = ok / total if total else 1.0
    return ratio, {"tokens": total, "found": ok, "unfound_sample": bad[:8]}


def metric_orphan(root: Path, entries) -> tuple[float, dict]:
    """无入链条目占比（被条目正文双链或 MOC 引用即为有入链）。

    关键：入链解析必须和 doctor 对齐——doctor 用条目的 title 字段建索引，
    这里原来只用文件名（e["name"]）建索引。当文件名是 E01 这类 ID、title 是
    中文时，正文里按规格写的 [[title 原文]] 永远匹配不到文件名 → 100% 误判孤儿。
    修法：为每个条目同时登记 title 与文件名两个键，任一被链接即视为有入链。
    """
    if not entries:
        return 0.0, {}
    # 条目身份：文件名 -> 它自己的 title（用于排除自链）
    own = {e["name"]: e["fm"].get("title", "").strip() for e in entries}
    aliases = {}  # 链接目标写法（title 或文件名） -> 规范化的条目名
    for e in entries:
        aliases[e["name"]] = e["name"]
        t = own[e["name"]]
        if t:
            aliases[t] = e["name"]
    inbound = {e["name"]: 0 for e in entries}

    def resolve(tgt: str, self_name: str) -> str | None:
        tgt = tgt.split("|")[0].split("#")[0].strip()
        hit = aliases.get(tgt)
        return hit if hit and hit != self_name else None

    for e in entries:
        for tgt in WIKILINK.findall(e["text"]):
            hit = resolve(tgt, e["name"])
            if hit:
                inbound[hit] += 1
    moc = root / "moc"
    if moc.exists():
        for p in moc.rglob("*.md"):
            hits = set()
            for tgt in WIKILINK.findall(p.read_text(encoding="utf-8")):
                hit = resolve(tgt, "")
                if hit:
                    hits.add(hit)
            for h in hits:
                inbound[h] += 1
    orphan = [n for n, c in inbound.items() if c == 0]
    ratio = len(orphan) / len(entries)
    return ratio, {"entries": len(entries), "orphan_count": len(orphan), "orphan_sample": orphan[:8]}


def metric_duplicate(entries) -> tuple[float, dict]:
    """近似重复条目占比（MinHash 两两 Jaccard ≥ 0.5）。"""
    n = len(entries)
    if n < 2:
        return 0.0, {"pairs": 0}
    mh = [(e["name"], minhash(e["body"])) for e in entries]
    dup_with = set()
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            sim = jaccard(mh[i][1], mh[j][1])
            if sim >= DUP_JACCARD:
                dup_with.add(mh[i][0]); dup_with.add(mh[j][0])
                pairs.append((mh[i][0], mh[j][0], round(sim, 2)))
    ratio = len(dup_with) / n
    return ratio, {"pairs": len(pairs), "sample": pairs[:5]}


def metric_counter_example(entries) -> tuple[float, dict]:
    """含「适用边界」或「反例」小节的条目占比。"""
    if not entries:
        return 0.0, {}
    hit = [e for e in entries if re.search(r"适用边界|反例|不成立", e["body"])]
    return len(hit) / len(entries), {"with": len(hit), "total": len(entries)}


# ---------- 报告 ----------
LABEL = {
    "coverage": "覆盖率",
    "traceability": "溯源率",
    "orphan": "孤儿条目率",
    "duplicate": "重复率",
    "counter_example": "反例密度",
}
DESC = {
    "coverage": "源文档章节被条目覆盖（证明没漏料）",
    "traceability": "条目数字可回溯到源文档（证明没编造）",
    "orphan": "无入链条目占比（证明结构连通）",
    "duplicate": "近似重复条目占比（证明去了重）",
    "counter_example": "含反例/边界的条目占比（证明不是复述）",
}


def verdict(ratio: float, rule: tuple) -> str:
    op, th = rule
    ok = ratio >= th if op == "ge" else ratio <= th
    return "PASS" if ok else "FAIL"


def main() -> int:
    ap = argparse.ArgumentParser(description="内容层验收报告")
    ap.add_argument("root", help="wiki 根目录（含 entries/）")
    ap.add_argument("--src", default=None, help="源文档目录或文件（默认 <root>/raw）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    a = ap.parse_args()

    root = Path(a.root).resolve()
    entries = load_entries(root)
    sources = load_sources(root, a.src)

    results = {}
    results["coverage"] = metric_coverage(sources, entries)
    results["traceability"] = metric_traceability(sources, entries)
    results["orphan"] = metric_orphan(root, entries)
    results["duplicate"] = metric_duplicate(entries)
    results["counter_example"] = metric_counter_example(entries)

    out = {}
    for k, (ratio, detail) in results.items():
        out[k] = {"ratio": round(ratio, 4), "rule": f"{THRESHOLDS[k][0]} {THRESHOLDS[k][1]}",
                  "verdict": verdict(ratio, THRESHOLDS[k]), "detail": detail}

    all_pass = all(v["verdict"] == "PASS" for v in out.values())
    meta = {"wiki_root": str(root), "entries": len(entries),
            "sources": [f.name for f, _ in sources],
            "overall": "PASS" if all_pass else "FAIL"}

    if a.json:
        print(json.dumps({"meta": meta, "metrics": out}, ensure_ascii=False, indent=2))
        return 0 if all_pass else 1

    print("=" * 68)
    print("内容层验收报告（Content-Level Acceptance Report）")
    print("=" * 68)
    print(f"知识库: {root}")
    print(f"条目数: {len(entries)}   源文档: {', '.join(meta['sources']) or '无'}")
    print("-" * 68)
    print(f"{'指标':<12}{'实测':>8}  {'判据':<12}{'结论':<6}说明")
    for k in ("coverage", "traceability", "orphan", "duplicate", "counter_example"):
        v = out[k]
        pct = f"{v['ratio'] * 100:.1f}%"
        print(f"{LABEL[k]:<12}{pct:>8}  {v['rule']:<12}{v['verdict']:<6}{DESC[k]}")
    print("-" * 68)
    for k, v in out.items():
        d = v["detail"]
        if k == "coverage" and d.get("excluded_sections"):
            print("已排除结构性章节（不计入覆盖率分母）:", "、".join(d["excluded_sections"]))
        if k == "coverage" and d.get("missed_sample"):
            print("未覆盖章节（样例）:")
            for s in d["missed_sample"]:
                print("  ·", s)
        if k == "traceability" and d.get("unfound_sample"):
            print("疑似失源数字（样例）:")
            for s in d["unfound_sample"]:
                print("  ·", s)
        if k == "orphan" and d.get("orphan_sample"):
            print("孤儿条目（样例）:", ", ".join(d["orphan_sample"]))
        if k == "duplicate" and d.get("sample"):
            print("近似重复对（样例）:")
            for x, y, s in d["sample"]:
                print(f"  · {x} ≈ {y}  (jaccard {s})")
    print("-" * 68)
    print(f"总体结论: {meta['overall']}")
    print("说明: 本报告只覆盖内容层。命中率/P95/越权拦截属系统层，不在本报告范围。")
    print("=" * 68)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
