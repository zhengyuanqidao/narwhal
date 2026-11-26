#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""feedback.py —— 使用反馈回路的入口（零依赖）

解决 narwhal 此前缺的一环：知识库能被增量更新，但没有"用户用了之后发现不对"
的反馈入口。本脚本把一条反馈登记成 wiki 能消化的形式，复用已验证的模式 B/G
增量机制。

设计边界（诚实，不假装自动进化）：
- 本脚本**不自动改条目**。语义修正（改哪句、结论要不要推翻）是模型判断，
  由使用者的 agent 在下次对话中按模式 B/G 完成——这和"编译不代替模型判断"一致。
- 脚本只做确定性的三件事：①落一条带 source 的反馈材料到 incoming/ ②在 log.md
  追加一条待处理记录 ③生成 FEEDBACK-QUEUE.md（给 agent 的修正指令清单）。
- 因此"进化"= 反馈被登记 → 下次增量时被 agent 当作新材料处理 → 版本 bump。
  闭环成立，但触发者是下一次 agent 会话，不是本脚本自己。

命令：
  add     登记一条反馈
  queue   查看待处理反馈

用法：
  python3 feedback.py add <wiki根目录> \\
      --target "条目title原文" \\
      --kind "答错|过期|缺反例|新证据" \\
      --detail "用户反馈原文" \\
      --by "反馈人/来源"

  python3 feedback.py queue <wiki根目录>
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path


def today() -> str:
    return date.today().isoformat()


def cmd_add(root: Path, args) -> int:
    if not (root / "entries").exists():
        print(f"错误: {root} 没有 entries/，不是有效 wiki")
        return 2
    if args.kind not in ("答错", "过期", "缺反例", "新证据"):
        print(f"错误: --kind 必须是 答错/过期/缺反例/新证据 之一，收到 {args.kind}")
        return 2

    incoming = root / "incoming"
    incoming.mkdir(exist_ok=True)
    d = today()
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", args.target).strip("-")[:24] or "entry"
    fname = f"{d}-反馈-{args.kind}-{slug}.md"
    p = incoming / fname
    if p.exists():
        print(f"错误: 反馈文件已存在，不覆盖: {p}")
        return 2

    body = f"""---
title: {d} 反馈：{args.target}
type: feedback
kind: {args.kind}
target: "{args.target}"
source: 用户反馈（{args.by}）
confidence: 中
created: {d}
---

# 反馈：{args.target}

- 类型：{args.kind}
- 针对条目：`{args.target}`
- 反馈人/来源：{args.by}
- 登记日期：{d}

## 反馈原文

{args.detail}

## 给下次增量的处理指令（由 agent 执行，脚本不改条目）

1. 用模式 B/G 读取本文件，定位目标条目 `{args.target}`。
2. 按反馈类型决定动作：
   - 答错：核对条目结论，若确错则**只改结论段**并保留原文于「模式 G 补充」；
   - 过期：在「适用边界/反例」追加时点说明，标 `stale` 待人工确认；
   - 缺反例：从反馈里提炼一条反例，补进「适用边界/反例」；
   - 新证据：作为新 source 归档 raw/，判断是否需要新增条目或局部补充。
3. 修正后走全库体检 + 版本 bump，并在 log.md 记一条来源为本反馈的日志。
4. 人改过的条目（human-edit）不得覆盖，改为在 FEEDBACK-QUEUE.md 标记"需人工确认"。
"""
    p.write_text(body, encoding="utf-8")

    log = root / "log.md"
    with log.open("a", encoding="utf-8") as f:
        f.write(f"- {d} | 反馈登记 | {args.kind}：针对「{args.target}」→ {fname}（待下次增量处理，未改条目）\n")

    refresh_queue(root)
    print(f"反馈已登记: {p}")
    print(f"待处理队列已刷新: {root / 'FEEDBACK-QUEUE.md'}")
    print("提示: 本脚本未改任何条目；下次对使用者 agent 说「接着更新知识库」时按模式 B/G 处理。")
    return 0


def refresh_queue(root: Path) -> None:
    incoming = root / "incoming"
    items = sorted(incoming.glob("*-反馈-*.md")) if incoming.exists() else []
    lines = [
        "# 待处理反馈队列",
        "",
        "> 由 `feedback.py` 维护。每条反馈在下次增量（模式 B/G）中被 agent 处理；",
        "> 处理完成并 bump 版本后，把对应文件从 `incoming/` 移到 `raw/` 归档，队列自动shrink。",
        "",
        f"当前待处理：**{len(items)} 条**",
        "",
    ]
    if items:
        lines.append("| 反馈文件 | 类型 | 针对条目 | 登记日 |")
        lines.append("|---|---|---|---|")
        for it in items:
            fm = parse_kv(it)
            lines.append(f"| `{it.name}` | {fm.get('kind', '?')} | {fm.get('target', '?')} | {fm.get('created', '?')} |")
    else:
        lines.append("队列为空。所有反馈已处理并归档。")
    (root / "FEEDBACK-QUEUE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_kv(p: Path) -> dict:
    text = p.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def cmd_queue(root: Path, args) -> int:
    q = root / "FEEDBACK-QUEUE.md"
    if not q.exists():
        print("队列文件不存在；先登记一条反馈或运行 refresh。")
        return 0
    print(q.read_text(encoding="utf-8"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="知识库使用反馈回路")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="登记一条反馈")
    a.add_argument("root")
    a.add_argument("--target", required=True, help="针对的条目 title 原文")
    a.add_argument("--kind", required=True, help="答错|过期|缺反例|新证据")
    a.add_argument("--detail", required=True, help="反馈原文")
    a.add_argument("--by", default="用户", help="反馈人/来源")

    q = sub.add_parser("queue", help="查看待处理队列")
    q.add_argument("root")

    args = ap.parse_args()
    root = Path(args.root).resolve()
    if args.cmd == "add":
        return cmd_add(root, args)
    return cmd_queue(root, args)


if __name__ == "__main__":
    raise SystemExit(main())
