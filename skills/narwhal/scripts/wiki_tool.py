#!/usr/bin/env python3
"""expert-wiki 知识库体检与统计工具。

用法:
  python3 wiki_tool.py doctor <wiki根目录>   # 检查断链、孤儿条目、缺失元数据
  python3 wiki_tool.py stats  <wiki根目录>   # 输出领域/条目/案例统计
"""
import re
import sys
from pathlib import Path

FRONT = re.compile(r"^---\n(.*?)\n---", re.S)
LINK = re.compile(r"\[\[([^\]|#]+?)\]\]")
# 反引号内的 [[]] 是说明性 code span（如在 SCHEMA/MOC 里举例"[[条目标题]]"），
# 不是真链接——markdown 语义上 code span 是字面文本，不应做断链检查。
CODE_SPAN = re.compile(r"`[^`]*`")


def link_targets(text: str):
    """产出可用于断链检查的链接目标：剔除反引号 code span、跳过日志类文件。"""
    return (m.group(1) for m in LINK.finditer(CODE_SPAN.sub("", text)))


def collect(root: Path):
    docs = {}  # title -> path
    raw = []   # (path, text)
    for sub in ("entries", "cases", "methods", "moc"):
        for p in (root / sub).rglob("*.md"):
            t = p.read_text(encoding="utf-8")
            raw.append((p, t))
            m = FRONT.search(t)
            title = None
            if m and re.search(r"^title:\s*(.+)$", m.group(1), re.M):
                title = re.search(r"^title:\s*(.+)$", m.group(1), re.M).group(1).strip()
            docs[norm(title or p.stem)] = p
    if (root / "HOME.md").exists():
        docs["HOME"] = root / "HOME.md"
    return docs, raw


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def doctor(root: Path):
    docs, raw = collect(root)
    issues = 0
    for p, text in raw:
        # log.md 是动作日志，不是知识内容：里面写"加了 44 处 [[双链]]"这类
        # 统计说明不应被当断链。真正的链接只在 entries/cases/moc 的知识正文里。
        if p.name == "log.md":
            pass
        else:
            for target in link_targets(text):
                if norm(target) not in docs:
                    print(f"✗ 断链: {p.relative_to(root)} -> [[{target}]]")
                    issues += 1
        fm = FRONT.search(text)
        if not fm and "moc" not in p.parts and p.name != "HOME.md":
            print(f"✗ 缺少 frontmatter: {p.relative_to(root)}")
            issues += 1
    # 孤儿条目：没有出链也没有入链
    inbound = {norm(t) for _, text in raw for t in link_targets(text)}
    for title, p in docs.items():
        if not p:
            continue
        if p.name == "HOME.md":
            continue  # HOME 是入口，允许无链接
        text = p.read_text(encoding="utf-8")
        if norm(title) not in inbound and not LINK.search(text):
            print(f"⚠ 孤儿条目(无链接关系): {p.relative_to(root)}")
            issues += 1
    print(f"\n体检完成，发现问题 {issues} 处。")
    return issues


def stats(root: Path):
    total = 0
    for sub in ("entries", "cases", "methods", "moc"):
        files = list((root / sub).rglob("*.md"))
        print(f"{sub:8s}: {len(files)} 个文件")
        total += len(files)
    print(f"合计 {total} 个文档")


if __name__ == "__main__":
    cmd, root = sys.argv[1], Path(sys.argv[2])
    if cmd == "doctor":
        # 退出码用标准布尔语义：有问题=1，无问题=0。
        # 不能用「问题数」当退出码：进程退出码仅 8 位，问题数恰好是 256 的倍数时
        # 会回绕成 0，run.py 门禁会误判「PASS 可对外」（已由 256 断链用例实测复现）。
        # 真实问题数由 doctor() 打印在输出里，需要的调用方从输出解析。
        sys.exit(1 if doctor(root) else 0)
    else:
        stats(root)
