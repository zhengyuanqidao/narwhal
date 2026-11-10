#!/usr/bin/env python3
"""wiki_graph —— 把 Narwhal wiki 的 [[链接]] 编译成图索引（实验特性，v1.1 候选）。

动机：wiki 大于 ~100 条目后，模式 C（读 HOME→MOC→条目）的 token 开销线性上涨。
图索引把"跳转关系"编译成一份紧凑 JSON，agent 检索时只读索引 + 命中条目，
定位成本从 O(库) 降到 O(命中+1跳邻居)。

用法:
  python3 wiki_graph.py build  <wiki根目录>   # 生成 <wiki>/graph/index.json
  python3 wiki_graph.py query  <wiki根目录> <关键词>   # 命中节点 + 1 跳邻居（紧凑 JSON）
  python3 wiki_graph.py stats  <wiki根目录>   # 图规模统计
"""
import json
import re
import sys
from pathlib import Path

FRONT = re.compile(r"^---\n(.*?)\n---", re.S)
LINK = re.compile(r"\[\[([^\]|#]+?)\]\]")
SUBS = ("entries", "cases", "methods", "moc")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def front(text: str) -> dict:
    m = FRONT.search(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("-"):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def load(wiki: Path):
    nodes, by_title = [], {}
    for sub in SUBS:
        for p in (wiki / sub).rglob("*.md"):
            t = p.read_text(encoding="utf-8")
            fm = front(t)
            title = fm.get("title") or p.stem
            kind = "case" if sub == "cases" else "moc" if sub == "moc" else "entry"
            node = {
                "id": norm(title),
                "title": title,
                "kind": kind,
                "domain": fm.get("domain", ""),
                "type": fm.get("type", ""),
                "confidence": fm.get("confidence", ""),
                "path": str(p.relative_to(wiki)),
                "tokens": len(re.findall(r"[\u4e00-\u9fff]", t)) + int((len(t) - len(re.findall(r"[\u4e00-\u9fff]", t))) * 0.3),
            }
            nodes.append(node)
            by_title[node["id"]] = node
    edges, dangling = [], set()
    for sub in SUBS:
        for p in (wiki / sub).rglob("*.md"):
            t = p.read_text(encoding="utf-8")
            src = norm(front(t).get("title") or p.stem)
            for m in LINK.finditer(t):
                dst = norm(m.group(1))
                if dst in by_title:
                    edges.append({"from": src, "to": dst})
                else:
                    dangling.add(m.group(1))
    return nodes, edges, sorted(dangling), by_title


def build(wiki: Path):
    nodes, edges, dangling, _ = load(wiki)
    out = wiki / "graph"
    out.mkdir(exist_ok=True)
    payload = {"nodes": nodes, "edges": edges, "dangling": dangling}
    (out / "index.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    kb = (out / "index.json").stat().st_size / 1024
    print(f"图索引已写入 {out/'index.json'}：{len(nodes)} 节点 / {len(edges)} 边 / {len(dangling)} 断链，{kb:.1f} KB")


def query(wiki: Path, kw: str):
    nodes, edges, _, by_title = load(wiki)
    hits = [n for n in nodes if kw in n["title"] or kw in n["domain"] or kw in n["type"]]
    result = []
    for n in hits:
        neigh = sorted({e["to"] for e in edges if e["from"] == n["id"]} |
                       {e["from"] for e in edges if e["to"] == n["id"]})
        result.append({
            "hit": n["title"], "kind": n["kind"], "domain": n["domain"],
            "confidence": n["confidence"], "path": n["path"], "tokens": n["tokens"],
            "neighbors_1hop": [by_title[i]["title"] for i in neigh if i in by_title],
        })
    print(json.dumps({"keyword": kw, "hits": len(result), "results": result},
                     ensure_ascii=False, indent=1))


def stats(wiki: Path):
    nodes, edges, dangling, _ = load(wiki)
    domains = {}
    for n in nodes:
        domains.setdefault(n["domain"] or "(未分域)", []).append(n)
    print(f"节点 {len(nodes)}  边 {len(edges)}  断链 {len(dangling)}  索引体积约 "
          f"{(len(json.dumps(nodes, ensure_ascii=False)) + len(json.dumps(edges))) / 1024:.1f} KB")
    for d, ns in sorted(domains.items()):
        print(f"  {d}: {len(ns)} 节点")
    deg = {}
    for e in edges:
        deg[e["from"]] = deg.get(e["from"], 0) + 1
        deg[e["to"]] = deg.get(e["to"], 0) + 1
    top = sorted(deg.items(), key=lambda x: -x[1])[:5]
    if top:
        print("  度最高的节点（知识枢纽）: " + ", ".join(f"{k}({v})" for k, v in top))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    root = Path(sys.argv[2])
    if sys.argv[1] == "build":
        build(root)
    elif sys.argv[1] == "query":
        query(root, sys.argv[3] if len(sys.argv) > 3 else "")
    elif sys.argv[1] == "stats":
        stats(root)
    else:
        print(__doc__)
        sys.exit(2)
