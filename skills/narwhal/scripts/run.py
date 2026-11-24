#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键收尾：把一个【已编译好的】知识库变成「可交付 + 可转发」的成品包。

边界（不改这条，就会变成空头支票）：
  编译（散文档 → entries/ 结构化条目）由 agent 按 SKILL.md 完成，
  需要模型判断，不是脚本能自动的。本脚本只负责编译【之后】的确定性链路：

    doctor 体检 → report 五项验收 → human/rag 双导出 → 传播节点 → 打包

  所以输入必须是已含 entries/ 的 wiki 根目录；没有就明确报错，
  不假装「丢一堆原始文档进来就自动出知识库」。

为什么要有它（OPC）：这套链路过去每一步都要人在场看结果、手动敲命令。
串成一条命令后，作者只在第一次写规格时出现，之后每个产物都自己跑完、
自带传播节点 —— 做一次，以后零次。

用法:
  python3 scripts/run.py <wiki根目录> [--out <成品目录>] [--title 标题]
                         [--by 落款] [--zip] [--allow-fail]
退出码:
  0 = 体检 0 问题 + 五项验收全 PASS，成品已生成
  1 = 体检有问题或验收未达标（默认不产出成品；--allow-fail 可强制产出用于自查）
  2 = 输入不合法（没有 entries/ 等）
零第三方依赖，仅用标准库 + 同目录的 4 个脚本。
"""
import argparse
import html
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_MD = HERE.parent / "SKILL.md"
SCRIPTS = {
    "doctor": HERE / "wiki_tool.py",
    "report": HERE / "report.py",
    "export": HERE / "export.py",
}

# 传播节点里唯一允许出现的占位符：技能上架后的市场链接。
# 显式标注，不能伪装成已发布 —— 上架前这里就是待替换状态。
LINK_PLACEHOLDER = "{上架后替换为技能市场链接；未上架时保留本行，不要删}"


def run_step(name: str, args: list) -> subprocess.CompletedProcess:
    """用当前解释器跑同目录脚本，实时透传输出。"""
    cmd = [sys.executable, str(SCRIPTS[name])] + [str(a) for a in args]
    print(f"\n$ {name} {' '.join(str(a) for a in args)}")
    return subprocess.run(cmd, capture_output=True, text=True)


def show(proc: subprocess.CompletedProcess) -> None:
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)


def skill_version() -> str:
    try:
        m = re.search(r"(?m)^version:\s*(\S+)", SKILL_MD.read_text(encoding="utf-8"))
        return m.group(1) if m else "unknown"
    except OSError:
        return "unknown"


def collect_samples(root: Path, limit: int = 6) -> list:
    """从条目里抽「标题 + 一句话结论」，用于传播节点展示。抽不到就降级用标题。"""
    samples = []
    for p in sorted((root / "entries").rglob("*.md")):
        text = p.read_text(encoding="utf-8")
        fm = re.match(r"^---\n(.*?)\n---", text, re.S)
        title = ""
        if fm:
            t = re.search(r"(?m)^title:\s*(.+)$", fm.group(1))
            title = t.group(1).strip() if t else ""
        title = title or p.stem
        body = text[fm.end():] if fm else text
        one = re.search(r"\*\*一句话结论\*\*[：:]\s*(.+)", body)
        if not one:
            one = re.search(r"(?m)^#\s+(.+)$", body)
        gist = (one.group(1).strip() if one else "").strip("*# ")
        gist = re.sub(r"\s+", " ", gist)[:120]
        samples.append({"title": title, "gist": gist})
        if len(samples) >= limit:
            break
    return samples


def write_share_node(out: Path, root: Path, title: str, by: str,
                     report: dict, samples: list, version: str) -> None:
    """产物自带的传播节点：可转发、带落款、能当作品集。纯静态零依赖。"""
    n = report.get("meta", {}).get("entries", len(samples))
    metrics = report.get("metrics", {})
    passed = sum(1 for v in metrics.values() if v.get("verdict") == "PASS")
    total = len(metrics) or 5

    items_md = "\n".join(
        f"- **{s['title']}** — {s['gist'] or '（见条目正文）'}" for s in samples
    ) or "- （暂无条目）"
    items_html = "\n".join(
        f"<li><b>{html.escape(s['title'])}</b><span>{html.escape(s['gist'] or '见条目正文')}</span></li>"
        for s in samples
    ) or "<li>暂无条目</li>"

    share_md = f"""# {title}

> 由散落文档编译而成的结构化知识库：{n} 条可复用判断，每条都带适用边界与反例。

## 这里面有什么（节选）

{items_md}

## 质量说明

- 内容层验收：{passed}/{total} 项通过（覆盖率 / 溯源率 / 孤儿率 / 重复率 / 反例密度）
- 验收报告、未覆盖章节清单见同目录 `MANIFEST.json` 与 `human/`、`rag/` 两份成品
- 本报告只覆盖内容层；命中率、响应时间、越权拦截属系统层，不在本库范围

## 我自己也想要一份，怎么做

1. 在支持 **Agent Skills** 的助手里安装技能「文档变知识库」（narwhal）。
2. 把你的会议纪要、方案、复盘放进一个文件夹，说一句「把这个文件夹变成知识库」。
3. 编译由助手完成；体检、验收、导出、生成这份说明由 `scripts/run.py` 一条命令收尾。

技能地址：{LINK_PLACEHOLDER}

---
*本库由「文档变知识库」v{version} 编译 · {by} · {datetime.now().strftime('%Y-%m-%d')}*
"""
    (out / "SHARE.md").write_text(share_md, encoding="utf-8")

    page = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{color-scheme:light dark}}
body{{margin:0;padding:32px 20px;font:16px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;max-width:720px;margin:auto}}
h1{{font-size:26px;line-height:1.3;margin:0 0 8px}}
.lead{{opacity:.75;margin:0 0 28px}}
.badge{{display:inline-block;padding:2px 10px;border:1px solid currentColor;border-radius:20px;font-size:13px;opacity:.8}}
h2{{font-size:17px;margin:32px 0 12px;opacity:.9}}
ul{{list-style:none;padding:0;margin:0}}
li{{padding:12px 14px;margin:8px 0;border:1px solid rgba(128,128,128,.3);border-radius:10px}}
li b{{display:block}} li span{{display:block;opacity:.72;font-size:14px;margin-top:4px}}
footer{{margin-top:36px;padding-top:16px;border-top:1px solid rgba(128,128,128,.25);font-size:13px;opacity:.65}}
code{{background:rgba(128,128,128,.15);padding:1px 5px;border-radius:4px}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p class="lead">由散落文档编译而成的结构化知识库 · {n} 条可复用判断 · 每条带适用边界与反例</p>
<span class="badge">内容层验收 {passed}/{total} 通过</span>
<h2>这里面有什么（节选）</h2>
<ul>{items_html}</ul>
<h2>我也想要一份</h2>
<p>在支持 <b>Agent Skills</b> 的助手里安装「文档变知识库」，把文档放进一个文件夹，
说「把这个文件夹变成知识库」。编译由助手完成，
<code>scripts/run.py</code> 负责体检、验收、导出和本页生成。</p>
<p>技能地址：{html.escape(LINK_PLACEHOLDER)}</p>
<footer>由「文档变知识库」v{html.escape(version)} 编译 · {html.escape(by)} · {datetime.now().strftime('%Y-%m-%d')}</footer>
</body></html>
"""
    (out / "index.html").write_text(page, encoding="utf-8")


def make_zip(out: Path, name: str) -> Path:
    zp = out.parent / f"{name}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob("*")):
            if p.is_file():
                z.write(p, str(Path(out.name) / p.relative_to(out)))
    return zp


def main() -> int:
    ap = argparse.ArgumentParser(description="知识库一键收尾（编译之后的确定性链路）")
    ap.add_argument("root", help="已编译好的 wiki 根目录（必须含 entries/）")
    ap.add_argument("--out", default=None, help="成品目录，默认 <root>/dist")
    ap.add_argument("--title", default="知识库", help="传播节点标题")
    ap.add_argument("--by", default="由 narwhal 编译", help="落款")
    ap.add_argument("--zip", action="store_true", help="额外打一个 zip")
    ap.add_argument("--allow-fail", action="store_true",
                    help="验收未达标也产出成品（仅用于自查，禁止对外交付）")
    a = ap.parse_args()

    root = Path(a.root).resolve()
    if not (root / "entries").is_dir() or not list((root / "entries").rglob("*.md")):
        print(f"✗ {root/'entries'} 不存在或没有条目。\n"
              "  run.py 只处理【已编译】的知识库；编译（散文档→条目）由 agent 按 SKILL.md 完成。",
              file=sys.stderr)
        return 2

    out = Path(a.out).resolve() if a.out else root / "dist"
    if out.exists():
        import shutil
        shutil.rmtree(out)
    out.mkdir(parents=True)

    version = skill_version()
    print(f"知识库: {root}\n成品目录: {out}\n技能版本: {version}")

    # 1) 体检：退出码 = 问题数
    d = run_step("doctor", ["doctor", root])
    show(d)
    doctor_ok = d.returncode == 0
    if not doctor_ok:
        print(f"✗ 体检发现 {d.returncode} 处问题。", file=sys.stderr)

    # 2) 五项验收：--json 便于机器判定
    r = run_step("report", [root, "--json"])
    report = {}
    try:
        report = json.loads(r.stdout)
    except json.JSONDecodeError:
        show(r)
    overall = report.get("meta", {}).get("overall", "UNKNOWN")
    print(f"内容层验收总体结论: {overall}")
    for k, v in report.get("metrics", {}).items():
        print(f"  {k:16s} {v['ratio']*100:6.1f}%  {v['verdict']}")
    report_ok = (r.returncode == 0 and overall == "PASS")

    gate_ok = doctor_ok and report_ok
    if not gate_ok and not a.allow_fail:
        print("\n✗ 未通过体检/验收，不产出成品（模式 F 纪律：不达标不导出）。\n"
              "  修好条目后重跑；仅自查可加 --allow-fail。", file=sys.stderr)
        return 1

    # 3) 双导出
    e1 = run_step("export", [root, "--format", "human", "--out", out / "human"])
    show(e1)
    e2 = run_step("export", [root, "--format", "rag", "--out", out / "rag", "--max-chars", "500"])
    show(e2)

    # 4) 传播节点（产物自带，自动带落款与「怎么做一份」）
    samples = collect_samples(root)
    write_share_node(out, root, a.title, a.by, report, samples, version)
    print("\n✓ 传播节点已生成: SHARE.md + index.html（可转发、带落款）")

    # 5) 清单
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "skill_version": version,
        "wiki_root": str(root),
        "entries": report.get("meta", {}).get("entries", len(samples)),
        "doctor_issues": d.returncode,
        "acceptance": overall,
        "metrics": {k: v["verdict"] for k, v in report.get("metrics", {}).items()},
        "delivered": gate_ok,
        "outputs": ["human/", "rag/", "SHARE.md", "index.html"],
        "link_placeholder": LINK_PLACEHOLDER,
        "note": "仅内容层验收；命中率/P95/越权拦截属系统层，不在本清单范围。",
    }
    (out / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    zp = make_zip(out, out.name) if a.zip else None
    print(f"\n{'='*60}\n成品就绪: {out}")
    print(f"  交付判定: {'PASS（可对外）' if gate_ok else 'FAIL（仅自查，禁止对外）'}")
    print(f"  传播节点: SHARE.md / index.html")
    print(f"  待替换: {LINK_PLACEHOLDER}")
    if zp:
        print(f"  打包: {zp}")
    print("=" * 60)
    return 0 if gate_ok else 1


if __name__ == "__main__":
    sys.exit(main())
