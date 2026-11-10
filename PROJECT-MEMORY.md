# Narwhal 项目记忆（跨对话交接文档）

> 最后更新：2026-11-10 16:05 · 用途：换对话后让新会话快速恢复全部上下文
> ⚠️ 2026-11-10 下午已**换代到新沙箱**，本地文件曾全部丢失，现按本文档重建。

## 项目是什么

**Narwhal · Dive deep. Stand out.**（独角鲸——深潜，成家）
把散落的个人经验/本地文档/云文档**自动扫描→分诊→按领域聚类→沉淀为多个领域知识库**，并可把领域库**编译输出为工作技能**（SOP/CHECKLIST/PLAYBOOK/BRIEF/skill.md）。
本质：一个 Agent Skill（`narwhal`），模式来自 Karpathy 的 LLM Wiki + 个人专家经验方法论（confidence/画像/深潜循环）。

## 关键文件位置（新沙箱实测有效）

| 内容 | 路径 |
|---|---|
| GitHub 发布仓库（= 本地 git 仓库） | `/workspace/narwhal-repo/` |
| skill 已安装目录（可直接被 agent 调用） | `/root/.codebuddy/skills/narwhal/`（从仓库 skills/narwhal 拷贝） |
| 开发/编辑用源目录 | `/workspace/narwhal-repo/skills/narwhal/`（改完再拷到安装目录） |
| 单文件发布包 | `/workspace/narwhal-repo/dist/narwhal.skill`（zip，7 个文件） |
| 演示知识库（仓库内，随 git 管理） | `/workspace/narwhal-repo/examples/demo-wiki/` |
| 演示知识库（工作副本，Obsidian 可开） | `/workspace/demo-wiki/`（与 examples 同步，勿单方面改） |
| 体检脚本 | `skills/narwhal/scripts/wiki_tool.py`（doctor/stats） |
| skill 打包工具 | `python3 /root/.codebuddy/plugins/cache/codebuddy-plugins-official/hot-skills/unknown/skills/skill-creator/scripts/package_skill.py <文件夹>`（本沙箱未验证路径是否存在） |

已失效的旧路径（上一代沙箱，勿再引用）：`/root/.codebuddy/artifact/2f8a7d30-9c21-4f0b-1d6b-e860f1d14000/narwhal/`、`/tmp/demo-src/`、`/workspace/narwhal.skill`。

## GitHub 状态

- 仓库：**https://github.com/lixh017/narwhal**（public，MIT，用户 lixh017 / ethan）
- **已同步到远程**：`main` HEAD = `ae85be5`（docs: 添加项目记忆文档与 .gitignore）+ tag `v1.0.0`（`bbcbb59`）
- **本地未推送**：用 `git log --oneline origin/main..HEAD` 查看（2026-11-10 16:05 时为 3 个 commit：演示库 + 记忆更新）
- 推送命令：`git push github main --tags`（远程名为 `github` 时；本沙箱 clone 后 remote 叫 `origin`，用 `git push origin main --tags`）
- ⚠️ 推送需认证：CodeBuddy 连接器 Token 只读（建仓/push 均 403）。方案：
  1. Device Flow（上次成功用过）：`curl -s -X POST https://github.com/login/device/code -H "Accept: application/json" -d "client_id=178c6fc778ccc68e1d6a&scope=repo"` → 给用户用户码 → 轮询 access_token
  2. 用户提供 PAT（勾 repo 权限）
- 只读 Token 获取：`source /root/.codebuddy/skills/github-connector/scripts/get_token.sh github`（clone/查看可用）
- 沙箱网络注意：`git ls-remote` 直连曾报 502（走代理不稳定），`git clone --depth 50 https://...` 可成功；`raw.githubusercontent.com` 用 WebFetch 可读。

## SKILL 核心设计（新会话快速理解）

- 三层架构：`raw/`（不可变源材料）→ entries/cases/methods/moc（agent 拥有）→ SCHEMA.md（结构权威）
- 五模式：A 初始化 / B 深潜(ingest) / C 导航(query) / D 体检(lint) / **E 全域扫描(discover)**
- **skill-forge**：领域库 ≥5条目+2案例 后可编译输出到 `wiki/exports/<领域>/`
- 会话恢复仪式（orientation）：SCHEMA → HOME → log.md 末 20-30 行，强制先读后动
- `log.md` 只追加；`confidence: 高/中/低` 分级；质量红线"经验>信息，不搬运通用知识"
- 模板 5 套在 `assets/templates/`（entry/case/moc/expert-profile/schema）
- 体检脚本判据（写内容时必须遵守，否则 doctor 报错）：
  - `[[链接]]` 目标必须精确等于某条目的 frontmatter `title`，或 moc 文件名、`HOME`
  - 每个条目/案例至少要有一条出链或入链，否则算孤儿
  - moc 文件允许无 frontmatter，其它文档必须有

## EVAL 评测集（2026-11-10 新增）

项目现在有回归测试了：`eval/`

| 内容 | 说明 |
|---|---|
| `eval/golden.json` | 金标准：12 份 fixture 的分诊标签、4 个期望领域、各项阈值 |
| `eval/run_eval.py` | 机械判分器，10 项检查（分诊准确率/raw sha256/噪音隔离/元数据/doctor/MOC/索引/log/门槛），输出 score + 退出码可直接接 CI |
| `eval/fixtures/archive/` | 10 份模拟散落文档（亚马逊卖家场景），+ 2 份真实噪音（`/root/.nvm/README.md`、`/root/.oh-my-zsh/README.md`） |
| `eval/fixtures/inject/` | 5 个故意做坏的条目（断链/孤儿/缺 frontmatter/互相矛盾 ×2） |
| `eval/cases/` | 9 个用例定义，只有 case-01/09 走机械判分，其余是人工/LLM 评审要点 |
| 新发现 | paulgraham.com 的 HTML **哈希漂移**（每次下载 sha256 不同）→ 真实语料比对必须以内容指纹为准；xlsx/pptx 指纹需解 OOXML（sharedStrings/slideN.xml），实现已在 run_eval.py 验证 |
| `eval/fixtures/web/` | **13 份真实网络文件**（2026-11-10 下载，9 种格式：pdf/html/docx/xlsx/pptx/json/yml/eml/md/csv/txt）+ MANIFEST（URL/哈希/许可）+ fetch.sh |
| `eval/runs/case-01/wiki` | 基线产物，score **100%**（10/10） |
| `eval/runs/case-04/wiki` | 反例（注入坏数据），**60%**（4 项 FAIL，doctor 4/4 命中） |
| `eval/runs/case-09/wiki` | 真实网络语料增量扫描，**100%**（11/11），经验 0 → 入库 0 条 |
| `eval/runs/case-09-fail/wiki` | 反例（抄 PG 文章原句进条目），**72.73%**，第 11 项指纹检测抓到 |

`.gitignore` 已改为 `/wiki/`（只忽略仓库根的知识库），`eval/runs/**` 全部入库作为回归基线；`eval/fixtures/web/*` 的二进制不入库（只留 MANIFEST + fetch.sh），需重新拉取时跑 `bash eval/fixtures/web/fetch.sh`。

运行：`python3 eval/run_eval.py eval/runs/case-01/wiki`（退出码 0 通过 / 1 未通过 / 2 用法错误）。

评测暴露的五个 SKILL 缺口（v1.1 候选）：
1. **模式 E 应产出 `wiki/triage.md`**——现在分诊只在对话里，无法审计与回归；
2. **`methods/` 目录边界不清**——实战中 SOP 全落进 `entries/` 的 method 类型，`methods/` 零文件，要么说清边界要么合并；
3. **零经验语料无处置规则**——素材全是外部资料时，应明确"拒绝建库 + 给统计"，否则 agent 会硬建空领域；
4. **"参考类"能否进 `raw/` 未定义**（本次实践：不进，raw 只存自己的源材料）；
5. **采集容错未要求**——解析出 0 字符应视为失败并报告（arxiv 直链那次拿到损坏 PDF 却静默通过）。

**检索栈 v1.1 三档定稿（实验数据见 eval/RESULTS.md 第七、八节）**：
- 档1 纯内存（MOC+双链导航）：≤100 条目，orientation ~1.3K tokens，query ~2.3K，零工具；
- 档2 BM25+图索引（wiki_search + wiki_graph + aka 锚点）：100~500 条目，零依赖，命中保底 8/9，锚点修词汇不相交；
- 档3 embedding 插件（Qwen3-Embedding-0.6B-Q，1.12GB）：>500 条目或档2 连续 miss 时启用，基准 9/9 但启用前必须在真实语料复测（e5-large 2.24G 反而垫底的教训）；
- 升档触发条件：query 返回空或 top3 全不相关 ≥2 次 → 档1→2；aka 锚点补了仍 miss、或条目 >500 → 2→3。

（原第七节定稿描述：：BM25 零依赖（hit@3 8/9，胜过本地 embedding 的 7/9）+ 图索引 + frontmatter `aka` 写入时锚点（修复"词汇不相交"的模糊查询）；embedding 只做可选插件；第八节规格阶梯实验（bge-small 7/9 → jina 9/9 → Qwen3-0.6B 9/9+hit@1 7/9 → e5-large 2.24GB 反而垫底 7/9）确认规格影响非单调，插件推荐模型定为 Qwen3-Embedding-0.6B-Q，启用前须在真实语料复测。注意 pyenv 3.11 与系统 python3.12 并存，装 Python 包必须用 `python3 -m pip`（sudo pip3 会装到 3.12 导致 import 失败）；HF 下载需 `SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt`。

诚实声明：case-01 的 wiki 是同一模型按 SKILL 生成、又由同一份 golden 判分，100% 只证明"结构守纪律"，不证明"提示词有效"。要真实判别力需换真实素材 + 换模型复跑（见 `eval/RESULTS.md` 第六节）。

## 变现结论（已讨论定调）

卖文件不成立；正解是**"骨架开源（已做），判断力闭源"**：
1. 先免费铺量（提交 skills.sh/TypingMind/Skillselion 收录）
2. 用 Narwhal 武装自己的领域经验 → 编译领域技能包
3. 卖服务（深潜陪跑/建库咨询 retainer）而非文件
4. 远期：垂直领域付费版（$99-499/月档）或托管应用
保护：wiki 内容永不进公开仓库（`.gitignore` 已加 `wiki/`）；品牌名 Narwhal 可注册商标；付费版走私有仓库+商业授权。

## 待办清单

- [x] 推送 CHANGELOG commit + v1.0.0 标签（上一代沙箱已完成，远程已确认）
- [x] narwhal-repo 加 `.gitignore`（含 `wiki/`）
- [x] README 补效果演示 —— 已加"效果示例"章节 + `examples/demo-wiki/` 16 个文件（文本版，0 断链）
- [ ] **推送 `ac223a0` 起的本地 commit**（等认证）
- [x] **建立 eval 评测集**：8 用例 + 10 项机械检查 + 基线/反例双跑（2026-11-10）
- [ ] 用**真实用户文档**跑 eval（换料），看分诊准确率是否仍 ≥90%
- [ ] **换模型/换会话复跑** case-01（换手），比较两份产物差异
- [ ] v1.1 候选：模式 E 增加 `triage.md` 产物；澄清 `methods/` 边界；把 eval score ≥90% 设为发版门槛
- [ ] README 加截图/GIF 版演示（文本版已有，视觉版待做：把 demo-wiki 渲染成 HTML 截图）
- [ ] 提交 skills.sh、TypingMind、Skillselion 收录（需账号；可先写投放文案与提交清单）
- [ ] **第一次真实深潜**：用户提供自己的散落文档，跑模式 E 建真实领域库
- [ ] （用户曾问 Gitee，暂缓；如需：完整 URL 形式 `npx skills add https://gitee.com/<user>/narwhal`）

## 环境备忘

- 用户身份：GitHub lixh017（ethan）；当前项目：ExpertLoop · Narwhal
- git 仓库身份已配置：`lixh017` / `lixh017@users.noreply.github.com`
- 用户语言：简体中文；偏好：直接给结论+行动建议，喜欢先对比再决策
- 上一代沙箱的 demo 数据（`/tmp/demo-src/`）已丢；当前 demo 内容为本次重建的**模拟数据**（私域运营 + 直播电商：6 条目 + 2 案例 + 2 raw），标注在 SCHEMA 与 EXPERT-PROFILE 顶部
