# Narwhal 🐋

> **Dive deep. Stand out.** · 中文副标：独角鲸 —— 深潜，成家。
>
> 把散落的个人经验、对话、笔记、文档**自动扫描、按领域聚类**，沉淀为多个结构化领域知识库，并可将领域知识库**编译输出为该领域的工作技能**（SOP / 检查清单 / 实战手册 / 可安装的 Agent Skill）。
>
> 这不是建百科——是把你验证过的经验编译成可复用的专家资产。

## 核心能力

| 模式 | 触发语 | 做什么 |
|---|---|---|
| 🌊 全域扫描 (discover) | "扫描我的资料，建领域库" | 扫描本地/云端散落文档 → 分诊（经验/参考/噪音）→ 聚类分域 → 批量入库 |
| 🔍 深潜 (ingest) | "帮我把这个沉淀下来" | 单份经历/对话/文档 → 确认 → 入库 → 更新地图与专家画像 |
| 🧭 导航 (query) | "我关于 X 积累了什么" | 顺知识地图引用你的个人判断原文回答 |
| 🩺 体检 (lint) | "体检/检查知识库" | 断链、孤儿条目、矛盾检测、覆盖缺口 |
| ⚒️ 技能输出 (skill-forge) | "输出这个领域的工作技能" | 编译 SOP / CHECKLIST / PLAYBOOK / BRIEF / 可安装 skill.md |

灵感来源：[Karpathy 的 LLM Wiki 模式](https://x.com/karpathy)（三层架构：不可变 raw 层 / agent 拥有的条目层 / SCHEMA 约定层）+ 追加式 log.md + 会话恢复仪式（orientation）。

差异化：**面向个人专家经验**——confidence 确信度分级、专家画像（EXPERT-PROFILE）、待深潜问题反哺（OPEN-QUESTIONS）、"经验 > 信息，不搬运通用知识"质量红线。

## 安装

支持 **GitHub / GitLab / Gitee / 自建 Git** 任意平台（skills CLI 对任意 git 主机通用）：

```bash
# 从 Gitee 安装（换成本人的 Gitee 用户名）
npx skills add https://gitee.com/zhengyuanqidao/narwhal --skill narwhal

# 从 GitHub 安装
npx skills add https://github.com/zhengyuanqidao/narwhal --skill narwhal

# Claude Code（任意平台，git clone 即可）
git clone --depth 1 https://gitee.com/zhengyuanqidao/narwhal.git /tmp/narwhal
mkdir -p ~/.claude/skills && cp -r /tmp/narwhal/skills/narwhal ~/.claude/skills/narwhal

# 不走 git？直接安装单文件包（.skill 即 zip 归档，可托管在任何可下载 URL）
npx skills add https://<任意下载地址>/narwhal.skill

# Codebuddy / 其他读取 skills 目录的 agent
# 把 skills/narwhal/ 整个目录复制进对应 skills 目录即可
```

> 说明：skills CLI 仅对 `owner/repo` 简写默认解析为 GitHub；使用 Gitee 等其他平台时请传**完整 URL**。私有仓库同样支持（使用本机已配置的 Git 凭据）。

## 快速开始

安装后对 agent 说：

1. `扫描我的资料，帮我建领域知识库` —— 指定要扫描的目录（本地或云端）
2. 确认聚类出的领域清单，等待批量入库
3. 之后随时：`深潜这段经历` / `我关于X积累了什么` / `知识库体检` / `输出XX领域的工作技能`

知识库默认生成在 `<工作区>/wiki/`，纯 Markdown，可用 Obsidian / VS Code 直接打开编辑。

## 效果示例

`examples/demo-wiki/` 是一个可直接用 Obsidian 打开的样例库（模拟数据：私域运营 + 直播电商两域，6 条目 + 2 案例）。

**结构长这样**：

```
wiki/
├── SCHEMA.md        # 结构权威 + 领域配置（私域运营 / 直播电商）
├── HOME.md          # 索引：每篇一句话摘要 + 最近更新
├── log.md           # 追加式动作日志（只增不删）
├── raw/             # 不可变源材料：周会纪要、复盘转写原文
├── moc/             # 每个领域一张知识地图（含知识关系图 + 待深潜）
├── entries/<领域>/  # 原子条目：一个条目讲透一个判断
├── cases/<领域>/    # 经验案例：背景 → 做法 → 结果 → 复盘
└── profile/         # 专家画像 + 待深潜问题清单
```

**一条条目长这样**（`entries/私域运营/别用红包做拉新钩子.md` 节选）：

```markdown
---
title: 别用红包做拉新钩子
domain: 私域运营
type: pitfall          # concept / method / pitfall / insight / resource
confidence: 高         # 我对这条经验的确信度
source: 9 月红包活动（380 人）的实际数据
links: ["[[私域不是加好友而是分层运营]]", "[[8000好友做成12万月销社群盘]]"]
---

**一句话结论**：红包拉来的是价格敏感人群，他们不只不买，还会反向拖低你的选品和定价判断。

## 展开
9 月红包拉新 3 元/人，加 380 人，CPA 看着只要 3 元。30 天后：留存 9%、客单价 41 元
（自然流量用户 118 元），群里只剩"什么时候还有红包"。真正的成本不是那 1,140 元，
是用错人群校准了商品结构——这一点在活动报表里永远看不到。

## 适用边界 / 反例
例外：清库存场景有效，但这批人要隔离出主运营池。

⭐ 一句话给三年后的自己：拉新钩子决定你未来一年的客户结构，别用最便宜的那个。
```

**体检输出**（`scripts/wiki_tool.py doctor examples/demo-wiki`）：

```
体检完成，发现问题 0 处。
```

体检会查断链、孤儿条目（无入链无出链）、缺失 frontmatter；`stats` 则给出各领域条目统计，用来判断哪个领域够格做技能输出（≥5 条目 + ≥2 案例）。

## 目录

```
skills/narwhal/
├── SKILL.md              # 技能主指令（触发、五种模式、质量红线）
├── scripts/wiki_tool.py  # 知识库体检：断链 / 孤儿条目 / 缺失元数据 / 统计
└── assets/templates/     # 条目、案例、MOC、专家画像、SCHEMA 模板

examples/demo-wiki/       # 演示库（模拟数据，可用 Obsidian 打开）
dist/narwhal.skill        # 单文件安装包（zip 归档，含 skills/narwhal 全部内容）
```

## License

MIT
