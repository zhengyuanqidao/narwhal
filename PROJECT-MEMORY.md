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
- **本地未推送**：`ac223a0` docs: 添加演示样例库与 README 效果示例（18 files, +611）
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
- [ ] **推送 `ac223a0`**（等认证）
- [ ] README 加截图/GIF 版演示（文本版已有，视觉版待做：把 demo-wiki 渲染成 HTML 截图）
- [ ] 提交 skills.sh、TypingMind、Skillselion 收录（需账号；可先写投放文案与提交清单）
- [ ] **第一次真实深潜**：用户提供自己的散落文档，跑模式 E 建真实领域库
- [ ] （用户曾问 Gitee，暂缓；如需：完整 URL 形式 `npx skills add https://gitee.com/<user>/narwhal`）

## 环境备忘

- 用户身份：GitHub lixh017（ethan）；当前项目：ExpertLoop · Narwhal
- git 仓库身份已配置：`lixh017` / `lixh017@users.noreply.github.com`
- 用户语言：简体中文；偏好：直接给结论+行动建议，喜欢先对比再决策
- 上一代沙箱的 demo 数据（`/tmp/demo-src/`）已丢；当前 demo 内容为本次重建的**模拟数据**（私域运营 + 直播电商：6 条目 + 2 案例 + 2 raw），标注在 SCHEMA 与 EXPERT-PROFILE 顶部
