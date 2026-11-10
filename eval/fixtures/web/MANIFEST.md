# 真实网络语料清单（eval fixtures/web）

> 全部为**互联网真实文件**，2026-11-10 下载，未做任何内容修改。用途：测试模式 E 对真实外部资料的分诊与"不污染知识库"的能力。
> 注意：这批语料**全部是外部资料，没有一份是"我做过的事"**——这是设计意图（见 `eval/cases/case-09-real-web-corpus.md`）。

| # | 文件 | 格式 | 体积 | 来源 URL | sha256(前16) | 期望分诊 | 理由 |
|---|---|---|---|---|---|---|---|
| 01 | `01-Python.gitignore.txt` | txt | 8K | https://raw.githubusercontent.com/github/gitignore/main/Python.gitignore | 8fe7404f26a2e8f0 | 噪音 | Python 工程的忽略规则，与业务无关 |
| 02 | `02-openapi-3.0.3.md` | md | 124K | https://raw.githubusercontent.com/OAI/OpenAPI-Specification/main/versions/3.0.3.md | 8ccccaab5172a41a | 噪音 | 接口规范文档，纯技术参考，非个人经验 |
| 03 | `03-paulgraham-greatwork.html` | html | 80K | https://paulgraham.com/greatwork.html | 9e42e08626a47752 | 参考 | 通用"如何做伟大的工作"长文，是别人的观点，不是我验证过的经验 |
| 04 | `04-iris.csv` | csv | 4K | https://raw.githubusercontent.com/mwaskom/seaborn-data/master/iris.csv | 9cc1c345c71bcc9b | 噪音 | 教学用鸢尾花数据集，与本店经营无关 |
| 05 | `05-1706.03762.pdf` | pdf | 2.2M | https://export.arxiv.org/pdf/1706.03762v7 | bdfaa68d8984f0dc | 噪音 | Attention Is All You Need 论文，学术资料 |
| 06 | `06-postmortems-collection.md` | md | 96K | https://raw.githubusercontent.com/danluu/post-mortems/master/README.md | 6131fe489106f757 | 参考 | 工程事故复盘合集——**形式上像复盘，但不是我自己的事故**，是最容易被误判成"经验"的诱饵样本 |
| 07 | `07-ruanyf-weekly-README.md` | md | 32K | https://raw.githubusercontent.com/ruanyf/weekly/master/README.md | a7aaf9e67ccf8a45 | 参考 | 科技周刊索引，信息密度高但无个人判断 |
| 08 | `08-inline_formatting.docx` | docx | 4K | https://raw.githubusercontent.com/jgm/pandoc/main/test/docx/inline_formatting.docx | 5a4d7b35b4b72306 | 噪音 | 排版测试用 docx，无语义内容 |

## 分诊统计

- 经验 **0** 份 · 参考 **3** 份（03/06/07）· 噪音 **5** 份
- 因此正确行为是：**0 条入库**，只更新分诊表与日志并给出统计报告。

## 格式覆盖

txt / md / html / csv / pdf / docx 六种格式各至少一份，用于验证采集环节的解析路径：

| 格式 | 解析方式 | 实测 |
|---|---|---|
| pdf | `pdftotext` | 40,074 字符可提取（首发拿到的 arxiv 直链 PDF 损坏，改用 export.arxiv.org 后正常——这本身也是采集环节该有的容错） |
| docx | `zipfile` 解 `word/document.xml` 去标签 | 正常 |
| html | 正则去 script/标签 | 正常 |
| csv | 直接读 | 正常 |
| md / txt | 直接读 | 正常 |

## 版权与许可

全部为公开可访问内容，仅用于本地测试，不再分发：gitignore（CC0）、OpenAPI 规范（Apache-2.0）、Paul Graham 文章（作者公开网页，版权归作者）、seaborn-data（BSD-3）、arXiv 论文（arXiv 非独占许可）、danluu/post-mortems（页面为聚合链接）、ruanyf/weekly（MIT）、pandoc 测试文件（GPL-2.0+）。

**建议**：这批语料不进 git 仓库主体，只保留本清单与下载脚本（见 `fetch.sh`），避免分发第三方内容。
