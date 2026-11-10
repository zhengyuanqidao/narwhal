# -*- coding: utf-8 -*-
"""实验2：embedding 规格阶梯对检索质量的影响（用户假设：规格不够导致表现差）。

同一语料（case-01 wiki，17 文档）、同一 9 条金标准查询，四个模型规格：
bge-small-zh(0.09G) → jina-v2-zh(0.64G) → Qwen3-0.6B-Q(1.12G) → e5-large(2.24G)
并测试最优模型 + BM25 混合是否到 9/9。
"""
import re, json, math, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "eval/runs/case-01/wiki"

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
        docs.append({"id": rel,
                     "title": title.group(1).strip() if title else p.stem,
                     "tags": [t.strip().strip('"') for t in tags.group(1).split(",")] if tags else [],
                     "body": body})
    return docs

def tokenize(s):
    s = s.lower(); out = []
    for m in re.finditer(r"[a-z0-9]+|[\u4e00-\u9fff]+", s):
        t = m.group(0)
        if re.match(r"^[a-z0-9]+$", t): out.append(t)
        else:
            for i in range(len(t)):
                out.append(t[i])
                if i+1 < len(t): out.append(t[i:i+2])
    return out

def bm25_scores(q, docs_toks, avgdl, df, N, k1=1.5, b=0.75):
    qt = tokenize(q); scores = []
    for toks in docs_toks:
        tf = {}
        for t in toks: tf[t] = tf.get(t,0)+1
        s = 0.0
        for t in qt:
            if t not in df: continue
            idf = math.log(1+(N-df[t]+0.5)/(df[t]+0.5)); f = tf.get(t,0)
            s += idf*f*(k1+1)/(f+k1*(1-b+b*len(toks)/avgdl))
        scores.append(s)
    return scores

QUERIES = [
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

E5_INSTR = "为这个句子生成表示以检索相关文章："
QWEN_INSTR = "Instruct: Given a web search query, retrieve relevant passages\nQuery: "

def emb_query_prefix(model):
    if "e5" in model.lower(): return E5_INSTR
    if "qwen" in model.lower(): return QWEN_INSTR
    return ""

def main(models):
    docs = load_docs()
    N = len(docs)
    docs_toks = [tokenize(d["title"]+" "+" ".join(d["tags"])+" "+d["body"]) for d in docs]
    avgdl = sum(map(len,docs_toks))/N
    df = {}
    for toks in docs_toks:
        for t in set(toks): df[t]=df.get(t,0)+1

    from fastembed import TextEmbedding
    import numpy as np
    results = {}
    for model in models:
        print(f"\n>>> {model}")
        t0 = time.perf_counter()
        emb = TextEmbedding(model_name=model)
        print(f"    加载 {time.perf_counter()-t0:.1f}s")
        prefix = emb_query_prefix(model)
        corpus = [f"{d['title']} {' '.join(d['tags'])} {d['body'][:800]}" for d in docs]
        M = np.array(list(emb.embed(corpus)), dtype="float32")
        M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
        hits3 = []; hits1 = []
        for q, kind, exp in QUERIES:
            qv = np.array(list(emb.embed([prefix + q])), dtype="float32")
            qv /= np.linalg.norm(qv) + 1e-9
            sims = M @ qv[0]
            order = np.argsort(-sims)[:3]
            top3 = [docs[i]["id"] for i in order]
            h3 = any(any(e in d for d in top3) for e in exp)
            h1 = any(e in top3[0] for e in exp)
            hits3.append(h3); hits1.append(h1)
            mark3 = "✓" if h3 else "✗"; mark1 = "✓" if h1 else "✗"
            print(f"    [{kind}] {q}  top1={mark1} hit3={mark3}  {top3[:2]}")
        results[model] = (sum(hits1), sum(hits3))
        print(f"    小计: hit@1 {sum(hits1)}/9  hit@3 {sum(hits3)}/9")
        del emb, M

    # 混合：BM25 + 最强模型 rerank（分数归一后等权相加）
    print("\n>>> 混合检索（BM25 归一 + 最优 embedding 归一，等权）")
    # 取 e5 或最后一个大模型重算相似度
    model = models[-1]
    emb = TextEmbedding(model_name=model)
    prefix = emb_query_prefix(model)
    corpus = [f"{d['title']} {' '.join(d['tags'])} {d['body'][:800]}" for d in docs]
    M = np.array(list(emb.embed(corpus)), dtype="float32")
    M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
    h3 = []
    for q, kind, exp in QUERIES:
        bm = np.array(bm25_scores(q, docs_toks, avgdl, df, N))
        bm = bm / (bm.max() + 1e-9)
        qv = np.array(list(emb.embed([prefix + q])), dtype="float32")
        sims = M @ qv[0]; sims = sims / (sims.max() + 1e-9)
        comb = bm + sims
        order = np.argsort(-comb)[:3]
        top3 = [docs[i]["id"] for i in order]
        hit = any(any(e in d for d in top3) for e in exp)
        h3.append(hit)
        print(f"    [{kind}] {q}  hit3={'✓' if hit else '✗'}  {top3[:2]}")
    print(f"    混合: hit@3 {sum(h3)}/9")

    print("\n===== 规格阶梯汇总 =====")
    for m_, (h1, h3_) in results.items():
        print(f"  {m_:55s} hit@1 {h1}/9  hit@3 {h3_}/9")
    print(f"  {'BM25 零依赖':55s} hit@1  6/9  hit@3 8/9（上轮实测）")

if __name__ == "__main__":
    main([
        "BAAI/bge-small-zh-v1.5",          # 0.09GB 基线
        "jinaai/jina-embeddings-v2-base-zh",   # 0.64GB
        "Qwen/Qwen3-Embedding-0.6B-Q",     # 1.12GB 当前小模型 SOTA
        "intfloat/multilingual-e5-large",  # 2.24GB
    ])
