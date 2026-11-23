#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出：把知识库转成「给人读」或「给 RAG 吃」两种格式，并支持按 scope 切分。

为什么需要两种：
  human —— 保留一句话结论 / 展开 / 反例 / ⭐，给人阅读和培训用；
  rag   —— 去装饰、加元数据头、按小节切 chunk、单 chunk ≤ max_chars，给检索系统入库用。
同一份知识库两种投喂方式，这是「交到总包手里就能直接用」的关键。

用法：
    python3 export.py <wiki根目录> --format rag  --out <输出目录>
    python3 export.py <wiki根目录> --format human --out <输出目录>
    python3 export.py <wiki根目录> --format rag  --out <目录> --scope 研发部
    python3 export.py <wiki根目录> --format rag  --out <目录> --split-scope

--split-scope：按 frontmatter 的 scope 字段分别导出到 <out>/<scope>/ 子目录，
               没有 scope 的条目进 <out>/_shared/。用于「不同部门拿不同子集」。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

FRONT = re.compile(r"^---\n(.*?)\n---\n?", re.S)
H1 = re.compile(r"^#\s+(.+)$", re.M)
STAR = re.compile(r"^⭐.*$", re.M)
RELATED = re.compile(r"^相关[:：].*$", re.M)


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


def split_sections(body: str):
    """按 ## 小节切分，返回 [(小节标题, 内容)]。首段（## 之前）记为 ('', 首段)。"""
    parts = re.split(r"^##\s+(.+)$", body, flags=re.M)
    out = []
    if parts[0].strip():
        out.append(("", parts[0].strip()))
    for i in range(1, len(parts), 2):
        out.append((parts[i].strip(), parts[i + 1].strip() if i + 1 < len(parts) else ""))
    return out


def to_rag(entry_text: str, fm: dict, max_chars: int):
    """转成 RAG 友好的 chunk 列表：每个 chunk 自带元数据头，去装饰。"""
    body = FRONT.sub("", entry_text)
    body = STAR.sub("", body)      # 去掉 ⭐ 一句话（对内，不用于检索）
    body = RELATED.sub("", body)   # 去掉相关链接行（链接关系用元数据表达）
    title = fm.get("title", "")
    body = H1.sub("", body).strip()

    chunks = []
    for sec, content in split_sections(body):
        content = re.sub(r"\n{3,}", "\n\n", content).strip()
        if not content:
            continue
        # 只输出非空元数据，避免 [scope] 这类空字段变成检索噪声
        fields = [("title", title), ("section", sec or "概述"), ("domain", fm.get("domain", "")),
                  ("type", fm.get("type", "")), ("confidence", fm.get("confidence", "")),
                  ("source", fm.get("source", "")), ("scope", fm.get("scope", "")),
                  ("owner", fm.get("owner", ""))]
        head = "".join(f"[{k}] {v}\n" for k, v in fields if v)
        # 超长内容按段落切，保证单 chunk ≤ max_chars
        if len(content) > max_chars:
            buf = ""
            for para in content.split("\n\n"):
                if len(buf) + len(para) + 2 > max_chars and buf:
                    chunks.append(head + "\n" + buf.strip())
                    buf = para
                else:
                    buf = f"{buf}\n\n{para}" if buf else para
            if buf.strip():
                chunks.append(head + "\n" + buf.strip())
        else:
            chunks.append(head + "\n" + content)
    return chunks


def main() -> int:
    ap = argparse.ArgumentParser(description="知识库导出")
    ap.add_argument("root")
    ap.add_argument("--format", choices=["human", "rag"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--scope", default=None, help="只导出该 scope 的条目")
    ap.add_argument("--split-scope", action="store_true", help="按 scope 分目录导出")
    ap.add_argument("--max-chars", type=int, default=500)
    a = ap.parse_args()

    root = Path(a.root).resolve()
    out = Path(a.out).resolve()
    entries = sorted((root / "entries").rglob("*.md"))
    if not entries:
        print(f"未找到条目：{root / 'entries'}", file=sys.stderr)
        return 2

    manifest = []
    written = 0

    for p in entries:
        text = p.read_text(encoding="utf-8")
        fm = parse_fm(text)
        scope = fm.get("scope", "") or "_shared"

        if a.scope and scope != a.scope:
            continue

        target_dir = out / (scope if a.split_scope else "")
        target_dir.mkdir(parents=True, exist_ok=True)

        if a.format == "human":
            dst = target_dir / p.name
            shutil.copy2(p, dst)
            written += 1
            manifest.append({"file": str(dst.relative_to(out)), "chunks": 1})
        else:
            chunks = to_rag(text, fm, a.max_chars)
            chunk_dir = target_dir / p.stem
            chunk_dir.mkdir(exist_ok=True)
            for i, c in enumerate(chunks, 1):
                (chunk_dir / f"{i:02d}.txt").write_text(c, encoding="utf-8")
            written += len(chunks)
            manifest.append({"file": str(chunk_dir.relative_to(out)), "chunks": len(chunks)})

    (out / "_manifest.json").write_text(
        json.dumps({"format": a.format, "entries": len(manifest),
                    "chunks": written, "items": manifest},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")

    print(f"导出完成：{a.format} → {out}")
    print(f"条目 {len(manifest)} 个，输出单元 {written} 个"
          + (f"（max_chars={a.max_chars}）" if a.format == "rag" else ""))
    if a.split_scope:
        scopes = sorted({m["file"].split("/")[0] for m in manifest})
        print(f"scope 分目录：{', '.join(scopes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
