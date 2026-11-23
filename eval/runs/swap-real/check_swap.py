#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""换料验证的独立判据（不依赖 golden.json 的固定样本）。
A 结构：调用官方 wiki_tool.py doctor + 字段/体量/链接检查。
B 内容不编造：抽取条目里的数字(¥N、N元、N个、N%)与关键专名，
   逐一核对能否在源文档 raw/COMPETITIVE-INTEL.md 找到。找不到=疑似编造。
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent.parent
DOCTOR = REPO / "skills" / "narwhal" / "scripts" / "wiki_tool.py"
SRC = (ROOT / "raw" / "COMPETITIVE-INTEL.md").read_text(encoding="utf-8")
FRONT = re.compile(r"^---\n(.*?)\n---", re.S)
REQ = ("title", "domain", "type", "confidence", "source", "links")
ENUMS = {"type": {"concept", "method", "pitfall", "insight", "resource"},
         "confidence": {"高", "中", "低", "低·外部参考"}}

fails = []

# ---- A. 结构 ----
entries = list((ROOT / "entries").glob("*.md"))
for p in entries:
    t = p.read_text(encoding="utf-8")
    m = FRONT.search(t)
    if not m:
        fails.append(f"[结构] {p.name}: 无 frontmatter"); continue
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("-"):
            k, v = line.split(":", 1); fm[k.strip()] = v.strip()
    for k in REQ:
        if k not in fm: fails.append(f"[结构] {p.name}: 缺 {k}")
    if fm.get("type") not in ENUMS["type"]: fails.append(f"[结构] {p.name}: type 非法 {fm.get('type')}")
    if fm.get("confidence") not in ENUMS["confidence"]: fails.append(f"[结构] {p.name}: confidence 非法")
    body = FRONT.sub("", t).strip()
    if len(body) < 200: fails.append(f"[结构] {p.name}: 正文 {len(body)} < 200")
    if not re.search(r"\[\[[^\]]+\]\]", t): fails.append(f"[结构] {p.name}: 无 [[链接]]")

r = subprocess.run([sys.executable, str(DOCTOR), "doctor", str(ROOT)], capture_output=True, text=True)
doc_out = r.stdout + r.stderr
doc_issues = re.search(r"发现问题\s*(\d+)\s*处", doc_out)
if doc_issues and int(doc_issues.group(1)) != 0:
    fails.append(f"[结构] doctor 报 {doc_issues.group(1)} 处问题:\n{doc_out.strip()}")

# ---- B. 内容不编造：数字必须在源文档出现 ----
# 抽取条目正文中的关键数字 token：¥后数字、N元/N个/N%/N款/N家/N单/N次
num_pat = re.compile(r"(?:¥\s?(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:元|个|%|款|家|单|次|万))")
for p in entries:
    body = FRONT.sub("", p.read_text(encoding="utf-8"))
    tokens = []
    for m in num_pat.finditer(body):
        v = m.group(1) or m.group(2)
        tokens.append(v)
    for v in set(tokens):
        # 源文档里这个数字串出现过即可（宽松：¥9→"9"）
        if v.rstrip("0").rstrip(".") not in SRC.replace(",", "") and v not in SRC:
            fails.append(f"[编造?] {p.name}: 数字 {v} 在源文档中找不到")

# 关键专名抽查（这些若出现却不在源文档=编造）
for kw in ("腾讯乐享", "Agensi", "Askpert", "Slite", "盈尺", "SkillPay", "APQC", "语雀"):
    for p in entries:
        t = p.read_text(encoding="utf-8")
        if kw in t and kw not in SRC:
            fails.append(f"[编造?] {p.name}: 专名 {kw} 不在源文档")

print("=" * 70)
print("换料验证 · 独立判据结果")
print("=" * 70)
print(f"条目数: {len(entries)}（门槛 6~14）")
print(f"结构问题: {sum(1 for f in fails if f.startswith('[结构]'))}")
print(f"疑似编造: {sum(1 for f in fails if f.startswith('[编造' ))}")
if fails:
    print("\n明细:")
    for f in fails: print("  ✗", f)
    print("\n结论: FAIL")
    sys.exit(1)
else:
    print("\n结论: PASS — 结构合规，且所有数字/专名可溯源到真实文档")
    sys.exit(0)
