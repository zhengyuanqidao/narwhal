# -*- coding: utf-8 -*-
"""实验：BM25 vs 本地 embedding vs 混合，在小型 wiki 上的检索质量对比。

数据：eval/runs/case-01/wiki（7 条目 + 2 案例 + 4 MOC）
金标准：人工标注每个查询的期望命中文档。
"""
import re, json, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "eval/runs/case-01/wiki"

# ---------- 语料 ----------
def load_docs():
    docs = []
    for p in sorted(ROOT.rglob("*.md")):
        rel = str(p.relative_to(ROOT))
        if rel in ("SCHEMA.md", "HOME.md", "log.md", "triage.md"):
            continue
        text = p.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        fm = m.group(1) if m else ""
        body = text[m.end():] if m else text
        title = re.search(r"^title:\s*(.+)$", fm, re.M)
        tags = re.search(r"^tags:\s*\[(.*?)\]", fm, re.M)
        conf = re.search(r"^confidence:\s*(.+)$", fm, re.M)
        docs.append({
            "id": rel,
            "title": title.group(1).strip() if title else p.stem,
            "tags": [t.strip().strip('"') for t in tags.group(1).split(",")] if tags else [],
            "confidence": conf.group(1).strip() if conf else "",
            "body": body,
        })
    return docs

# ---------- BM25（零依赖：CJK bigram + ASCII 词） ----------
def tokenize(s):
    s = s.lower()
    out = []
    for m in re.finditer(r"[a-z0-9]+|[\u4e00-\u9fff]+", s):
        t = m.group(0)
        if re.match(r"^[a-z0-9]+$", t):
            out.append(t)
        else:  # 中文按 bigram + 单字
            for i in range(len(t)):
                out.append(t[i])
                if i + 1 < len(t):
                    out.append(t[i:i+2])
    return out

def bm25_build(docs):
    N = len(docs)
    docs_toks = [tokenize(d["title"] + " " + " ".join(d["tags"]) + " " + d["body"]) for d in docs]
    avgdl = sum(len(t) for t in docs_toks) / N
    df = {}
    for toks in docs_toks:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    return docs_toks, avgdl, df, N

def bm25_search(q, docs_toks, avgdl, df, N, k1=1.5, b=0.75, top=5):
    qt = tokenize(q)
    scores = []
    for i, toks in enumerate(docs_toks):
        s, tf = 0.0, {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        for t in qt:
            if t not in df:
                continue
            idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
            f = tf.get(t, 0)
            s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(toks) / avgdl))
        scores.append((i, s))
    scores.sort(key=lambda x: -x[1])
    return [(i, round(s, 3)) for i, s in scores[:top] if s > 0]

# ---------- 金标准查询 ----------
QUERIES = [
    # (query, 类型, 期望命中文档 id 关键词)
    ("断货",              "精确词",   ["断货一次权重掉三个月", "旺季断货12天"]),
    ("ACOS 飙升 怎么办",  "精确词",   ["ACOS飙升"]),
    ("安全库存公式",      "精确词",   ["安全库存"]),
    ("链接排名掉了怎么办", "同义改写", ["断货一次权重掉三个月", "旺季断货12天"]),
    ("新品测款要备多少货", "同义改写", ["小批量测款"]),
    ("广告费烧得太快",    "同义改写", ["ACOS飙升", "品牌词广告"]),
    ("那个退货亏钱的事",   "口语模糊", ["旺季断货12天", "宠物饮水机"]),
    ("上次为什么亏本",     "口语模糊", ["旺季断货12天", "宠物饮水机"]),
    ("找人对下分工",       "口语模糊", ["运营分工"]),
]

def hit_at(results, expected, k):
    topk = [docs[i]["id"] for i, _ in results[:k]]
    return any(any(e in d for d in topk) for e in expected)

# ---------- 主流程 ----------
docs = load_docs()
docs_toks, avgdl, df, N = bm25_build(docs)
print(f"语料: {N} 文档（{sum(len(t) for t in docs_toks)} tokens 词法）\n")

# embedding（本地 bge-small-zh，onnx）
from fastembed import TextEmbedding
MODEL = "BAAI/bge-small-zh-v1.5"
print(f"加载 embedding 模型: {MODEL} ...")
emb = TextEmbedding(model_name=MODEL)
corpus_texts = [f"{d['title']} {' '.join(d['tags'])} {d['body'][:800]}" for d in docs]
vecs = list(emb.embed(corpus_texts))
import numpy as np
M = np.array(vecs, dtype="float32")
M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
print("语料向量构建完成\n")

def emb_search(q, top=5):
    qv = np.array(list(emb.embed([f"为这个句子生成表示以检索相关文章：{q}"])), dtype="float32")
    qv /= np.linalg.norm(qv) + 1e-9
    sims = M @ qv[0]
    idx = np.argsort(-sims)[:top]
    return [(int(i), round(float(sims[i]), 3)) for i in idx]

rows = []
for q, kind, exp in QUERIES:
    b = bm25_search(q, docs_toks, avgdl, df, N)
    e = emb_search(q)
    b_hit = hit_at(b, exp, 3); e_hit = hit_at(e, exp, 3)
    rows.append((q, kind, b_hit, e_hit))
    bnames = [docs[i]["title"][:16] for i, _ in b[:3]]
    enames = [docs[i]["title"][:16] for i, _ in e[:3]]
    print(f"[{kind}] {q}")
    print(f"  BM25 top3: {bnames}  hit@3={b_hit}")
    print(f"  EM B top3: {enames}  hit@3={e_hit}")

print("\n===== 汇总 =====")
for label, col in [("BM25", 2), ("Embedding", 3)]:
    n = sum(1 for r in rows if r[col])
    print(f"{label:10s} hit@3 = {n}/{len(rows)}")
