#!/usr/bin/env python3
"""Narwhal 评测 runner —— 对一个 wiki 产物做机械判分。

用法:
  python3 eval/run_eval.py <wiki根目录>
  python3 eval/run_eval.py eval/runs/case-01/wiki --json

判分口径见 eval/README.md；金标准在 eval/golden.json。
退出码: 0 = 通过（score >= thresholds.score_pass），1 = 未通过，2 = 用法/环境错误。
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GOLDEN = json.loads((REPO / "eval" / "golden.json").read_text(encoding="utf-8"))
DOCTOR = REPO / "skills" / "narwhal" / "scripts" / "wiki_tool.py"

FRONT = re.compile(r"^---\n(.*?)\n---", re.S)
LINK = re.compile(r"\[\[([^\]|#]+?)\]\]")
LOG_LINE = re.compile(r"^-\s*\d{4}-\d{2}-\d{2}\s*\|\s*模式[A-E]\s*\|\s*.+$")
LABELS = ("经验", "参考", "噪音")
ENUMS = {
    "type": {"concept", "method", "pitfall", "insight", "resource"},
    "confidence": {"高", "中", "低", "低·外部参考"},
}
REQUIRED_FIELDS = ("title", "domain", "type", "confidence", "source", "links")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def parse_front(text: str) -> dict:
    m = FRONT.search(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("-"):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


class Report:
    def __init__(self):
        self.rows = []

    def add(self, name, ok, detail="", weight=1.0):
        self.rows.append({"check": name, "ok": bool(ok), "detail": detail, "weight": weight})

    @property
    def score(self):
        w = sum(r["weight"] for r in self.rows)
        got = sum(r["weight"] for r in self.rows if r["ok"])
        return got / w if w else 0.0

    def render(self):
        lines = ["", "=" * 78, "Narwhal Eval Report", "=" * 78]
        for r in self.rows:
            mark = "PASS" if r["ok"] else "FAIL"
            lines.append(f"[{mark}] {r['check']}")
            if r["detail"]:
                for d in str(r["detail"]).splitlines():
                    lines.append(f"       {d}")
        lines.append("-" * 78)
        lines.append(f"score = {self.score:.2%}  (pass line {GOLDEN['thresholds']['score_pass']:.0%})")
        lines.append("=" * 78)
        return "\n".join(lines)


# ---------- 各项检查 ----------

def check_required(root: Path, rep: Report):
    need = ["SCHEMA.md", "HOME.md", "log.md", "triage.md"]
    missing = [n for n in need if not (root / n).exists()]
    rep.add("1. 必需产物齐全 (SCHEMA/HOME/log/triage)", not missing,
            "" if not missing else "缺失: " + ", ".join(missing))


def parse_triage(root: Path):
    p = root / "triage.md"
    if not p.exists():
        return {}
    rows = {}
    for line in read(p).splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("文件", "文件名", "file"):
            continue
        name = cells[0].strip("`").split("/")[-1]
        label = next((l for l in LABELS if l in cells[1]), None)
        if label:
            rows[name] = label
    return rows


def check_triage(root: Path, rep: Report):
    got = parse_triage(root)
    if not got:
        rep.add("2. 分诊准确率", False, "triage.md 不存在或没有可解析的表格行")
        return
    hit = total = 0
    wrong = []
    for g in GOLDEN["triage"]:
        name = g["file"].split("/")[-1]
        accept = [g["label"]] + g.get("accept", [])
        total += 1
        if got.get(name) in accept:
            hit += 1
        else:
            wrong.append(f"{name}: 期望 {'/'.join(accept)}，实得 {got.get(name) or '未分诊'}")
    acc = hit / total
    rep.add("2. 分诊准确率", acc >= GOLDEN["thresholds"]["triage_accuracy_min"],
            f"准确率 {acc:.0%}（{hit}/{total}，阀值 {GOLDEN['thresholds']['triage_accuracy_min']:.0%}）"
            + ("\n误判:\n  " + "\n  ".join(wrong) if wrong else ""))


def check_raw_immutable(root: Path, rep: Report):
    raw_dir = root / "raw"
    src_dir = REPO / GOLDEN["scan"]["archive_dir"]
    exp = [g for g in GOLDEN["triage"] if g["label"] == "经验" and not g["file"].startswith("/")]
    if not exp:
        rep.add("3. raw 原样归档（sha256 一致）", False, "golden 中没有经验类样本")
        return
    raw_files = [p for p in raw_dir.rglob("*") if p.is_file()] if raw_dir.exists() else []
    miss, bad = [], []
    for g in exp:
        src = src_dir / g["file"]
        if not src.exists():
            miss.append(f"源文件不存在: {g['file']}")
            continue
        cands = [p for p in raw_files if src.stem in p.name]
        if not cands:
            miss.append(f"未归档: {g['file']}")
            continue
        if not any(sha(p) == sha(src) for p in cands):
            bad.append(f"内容被改动: {g['file']}（源 {sha(src)}，raw {[sha(p) for p in cands]}）")
    ok = not miss and not bad
    rep.add("3. raw 原样归档（sha256 一致）", ok,
            f"{len(exp)} 份经验素材，归档 {len(exp)-len(miss)} 份" + ("\n" + "\n".join(miss + bad) if miss + bad else ""))


def check_noise(root: Path, rep: Report):
    raw_dir = root / "raw"
    files = [p for p in raw_dir.rglob("*") if p.is_file()] if raw_dir.exists() else []
    raw_text = "\n".join(p.name + "\n" + read(p) for p in files)
    leaked = [g["file"].split("/")[-1] for g in GOLDEN["triage"]
              if g["label"] == "噪音" and g["file"].split("/")[-1] in raw_text]
    rep.add("4. 噪音未入库", not leaked,
            "" if not leaked else "泄漏进 raw/: " + ", ".join(leaked))


def check_entries(root: Path, rep: Report):
    files = list((root / "entries").rglob("*.md"))
    problems = []
    for p in files:
        t = read(p)
        fm = parse_front(t)
        body = FRONT.sub("", t)
        if not fm:
            problems.append(f"{p.name}: 无 frontmatter")
            continue
        for k in REQUIRED_FIELDS:
            if k not in fm:
                problems.append(f"{p.name}: 缺 {k}")
        if fm.get("type") and fm["type"] not in ENUMS["type"]:
            problems.append(f"{p.name}: type 非法值 {fm['type']}")
        if fm.get("confidence") not in ENUMS["confidence"]:
            problems.append(f"{p.name}: confidence 非法值 {fm.get('confidence')}")
        if len(body.strip()) < GOLDEN["thresholds"]["entry_body_chars_min"]:
            problems.append(f"{p.name}: 正文 {len(body.strip())} 字 < {GOLDEN['thresholds']['entry_body_chars_min']}")
        if not LINK.search(t):
            problems.append(f"{p.name}: 没有任何 [[链接]]")
    n = len(files)
    ok = not problems and GOLDEN["thresholds"]["entries_min"] <= n <= GOLDEN["thresholds"]["entries_max"]
    rep.add("5. 条目 frontmatter / 体量 / 链接", ok,
            f"{n} 个条目（期望 {GOLDEN['thresholds']['entries_min']}~{GOLDEN['thresholds']['entries_max']}）"
            + ("\n" + "\n".join(problems) if problems else ""))


def check_doctor(root: Path, rep: Report):
    if not DOCTOR.exists():
        rep.add("6. 体检脚本 0 问题", False, f"找不到 {DOCTOR}")
        return
    r = subprocess.run([sys.executable, str(DOCTOR), "doctor", str(root)],
                       capture_output=True, text=True)
    out = r.stdout + r.stderr
    m = re.search(r"发现问题\s*(\d+)\s*处", out)
    n = int(m.group(1)) if m else -1
    rep.add("6. 体检脚本 0 问题", n == GOLDEN["thresholds"]["doctor_issues_max"],
            f"doctor 报告 {n} 处问题" + ("\n" + out.strip() if n else ""))


def check_moc(root: Path, rep: Report):
    dom2titles = {}
    for p in (root / "entries").rglob("*.md"):
        fm = parse_front(read(p))
        if fm.get("title") and fm.get("domain"):
            dom2titles.setdefault(fm["domain"], set()).add(fm["title"])
    moc_texts = {p.stem: read(p) for p in (root / "moc").glob("*.md")}
    problems, found = [], []
    for exp in GOLDEN["expected_domains"]:
        matched = [s for s in moc_texts if any(k in s for k in exp["keywords"])]
        if not matched:
            problems.append(f"缺 MOC: {exp['domain']}")
            continue
        found.append(exp["domain"])
        blob = "\n".join(moc_texts[s] for s in matched)
        for dom, titles in dom2titles.items():
            if any(k in dom for k in exp["keywords"]):
                for t in titles:
                    if t not in blob:
                        problems.append(f"MOC 未挂载: {t}")
    rep.add("7. 领域 MOC 覆盖全部条目", not problems,
            f"识别到领域 {len(found)}/{len(GOLDEN['expected_domains'])}"
            + ("\n" + "\n".join(problems) if problems else ""))


def check_home(root: Path, rep: Report):
    home = read(root / "HOME.md") if (root / "HOME.md").exists() else ""
    titles = [parse_front(read(p)).get("title") for p in (root / "entries").rglob("*.md")]
    missing = [t for t in titles if t and t not in home]
    ok = not missing and "最近更新" in home
    rep.add("8. HOME 索引完整", ok,
            (f"未进索引: {missing}" if missing else "") + ("" if "最近更新" in home else " 缺'最近更新'区块"))


def check_log(root: Path, rep: Report):
    p = root / "log.md"
    if not p.exists():
        rep.add("9. log.md 格式合规", False, "无 log.md")
        return
    lines = [l for l in read(p).splitlines() if l.strip().startswith("-")]
    bad = [l for l in lines if not LOG_LINE.match(l.strip())]
    rep.add("9. log.md 格式合规", bool(lines) and not bad,
            f"{len(lines)} 条日志" + (f"，{len(bad)} 条格式错误: {bad[:2]}" if bad else ""))


def check_forge(root: Path, rep: Report):
    dom_e, dom_c = {}, {}
    for sub, bucket in (("entries", dom_e), ("cases", dom_c)):
        for p in (root / sub).rglob("*.md"):
            d = parse_front(read(p)).get("domain")
            if d:
                bucket[d] = bucket.get(d, 0) + 1
    can = [(d, dom_e.get(d, 0), dom_c.get(d, 0)) for d in set(dom_e) | set(dom_c)
           if dom_e.get(d, 0) >= 5 and dom_c.get(d, 0) >= 2]
    expect = GOLDEN["forge_gate"]["expect_can_compile"]
    ok = bool(can) == expect
    detail = "各领域: " + ", ".join(f"{d}={dom_e.get(d,0)}条目/{dom_c.get(d,0)}案例" for d in sorted(set(dom_e) | set(dom_c)))
    detail += f"\n判定可编译: {[c[0] for c in can] or '无'}（期望 {'有' if expect else '无'}）"
    rep.add("10. 技能输出门槛判定", ok, detail)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    as_json = "--json" in sys.argv
    if not args:
        print(__doc__)
        return 2
    root = Path(args[0]).resolve()
    if not root.exists():
        print(f"wiki 根目录不存在: {root}")
        return 2
    rep = Report()
    for fn in (check_required, check_triage, check_raw_immutable, check_noise,
               check_entries, check_doctor, check_moc, check_home, check_log, check_forge):
        try:
            fn(root, rep)
        except Exception as e:  # 单项异常不拖垮整轮
            rep.add(f"{fn.__name__}", False, f"检查异常: {e!r}")
    if as_json:
        print(json.dumps({"score": rep.score, "checks": rep.rows}, ensure_ascii=False, indent=2))
    else:
        print(rep.render())
    return 0 if rep.score >= GOLDEN["thresholds"]["score_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
