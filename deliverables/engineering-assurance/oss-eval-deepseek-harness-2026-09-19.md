# OSS 评估：DeepSeek Harness (`dsh`) — 与 LeadGen AI 的适配性

**日期**：2026-09-19
**工作流**：工作流 2（系统设计 / 技术选型）— 前置分诊（Triage）
**参与成员**：Zhen（工程督导 · 编排）／本报告为**分诊级**产出，深度工作流待业主指定方向后启动
**评估对象**：https://github.com/deepseek-ai/deepseek-harness.git

---

## 📌 TL;DR（执行摘要）

- **是什么**：DeepSeek 官方开源的**智能体运行时（agent harness）**，基于 Cordis 插件框架，口号 "Everything is a Plugin"；CLI 名为 `dsh`，MIT 许可。
- **热度极高但极年轻**：**229,721 ★ / 27,488 forks**，但仓库创建于 **2026-08-13**（约 5 周），仍处 **developer preview `0.1.6-alpha.2`**，README 明确警告"会有破坏性变更"。
- **技术栈错配**：TypeScript 单体仓库（54 个包、13,854 个文件、约 206 MB），而 LeadGen 是 Python/FastAPI；引入等于在单台 VPS 上再加一套 Node 运行时。
- **免费额度可行**：模型适配器挂在 `ctx.llm` 接缝上，支持 **"Add a custom provider"**（`baseURL` + `openai-completions` / `openai-responses` / `anthropic-messages` 三选一协议）→ Groq / Cerebras / Mistral / OpenRouter / 本地 vLLM 均可接入，**不违反"全免费 provider"红线**。
- **结论：不建议进入生产。** 建议仅作为**本地开发工具**与**参考架构**使用。
- **严重度分布**：🔴严重 0 项 / 🟠高 1 项 / 🟡中 2 项 / 🟢低 2 项

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| 整体评级 | 🟡 **有条件通过（仅限非生产用途）** |
| 阻塞项数量 | 1（生产集成） |
| 关键行动项 | 4 条 |
| 建议下一步 | 由业主指定：深度评估 / 沙箱试跑 / 模式提取 / 仅存档 |

---

## 🔎 事实核查（全部来自实时抓取，非记忆）

| 字段 | 实测值 | 来源 |
|------|--------|------|
| 仓库 | `deepseek-ai/deepseek-harness` | GitHub API |
| 描述 | "DeepSeek Harness: Everything is a Plugin." | GitHub API |
| 许可证 | **MIT** | GitHub API (`license.spdx_id`) |
| 主语言 | **TypeScript** | GitHub API |
| Stars / Forks | **229,721 / 27,488** | GitHub API |
| 创建时间 | **2026-08-13T11:56:32Z** | GitHub API |
| 最后推送 | 2026-09-17T13:30:15Z | GitHub API |
| 体积 / 文件数 | ~206,488 KB · **13,854 个路径** | GitHub API tree |
| 包数量 | **54 个**（`packages/*`） | GitHub API tree |
| 最新版本 | `0.1.6-alpha.2` | 仓库文件列表 |
| 默认分支 | `master`（HEAD `ddefc45f`） | `git ls-remote` |
| 已归档 | 否 | GitHub API |
| Topics | `ai-agents`, `cordis`, `dsh`, `dsh-plugin` | GitHub API |

---

## 🏗️ 架构摘要

**底层框架 = Cordis**：插件向共享 context 贡献服务、类型化事件与**可回收副作用**；连模型适配器、工具注册表、会话日志、乃至 agent 循环本身都是插件，**没有需要打补丁的特权内核**。扩展方式是"在旁边挂一个插件"。

**插件树 = Profile × Bundle × Layer**，启动时按序组合：
1. Profile 列出的每个 bundle（按序）
2. Profile 的 `cordis.patch.yml`
3. Home 级 `cordis.patch.yml`
4. `--patch` 覆盖层

**内置 bundle**：`dsh-base`（共享首层：模型适配器/工具/持久化/沙箱审批策略/凭据/遥测）、`dsh-web-app`、`dsh-headless`、`dsh-sdk-app`、`dsh-acp-app`、`dsh-sdk-minimal`（唯一不套 `dsh-base` 的例外）。

**核心组件**（`ctx` 键）：`core/session`、`core/system-prompt`、`core/tools`、`core/agent`、`core/agent-loop`、`core/scope`、`llm/llm`、`webhook/webhook`；另有约 15 个子系统（Session Projection、Subagents、Agent Teams、Goals、Commands、Jobs、Shell、Terminals、Filesystem、Sandbox…）。

**关键设计原则**：
- **"Model-visible means logged"** —— 任何进入模型请求的内容都必须能从会话日志重建，有运行时不变式断言。
- **能力接缝（capability seam）三角色**：Service Definition / Service Provider / Consumer。换一个 provider（如 fs/subprocess → 远程沙箱）会**同时**移动 Bash、PTY、LSP。

**SDK**：TypeScript 与 **Python 双支持**。Python wheel 打包了 `dsh` CLI 本体（`deepseek-harness-sdk-runtime-<platform>-<arch>`），客户端以 `dsh --profile sdk` 启动，对外暴露"profile 选择 + 有序 patch 文件"。

---

## 💰 免费 provider 兼容性（对 LeadGen 最关键）

`docs/user/guide/providers.md` 实测结论：

- **内置目录**：DeepSeek 自有路由（独立适配器 `dsh-llm-deepseek`），以及 catalog 中的 `anthropic`、`openai`、`moonshotai`(Kimi)、`zai`(GLM)。
- **自定义 provider**（"Add a custom provider"）：填写 `Provider ID` + `baseURL` + `API protocol` + 凭据 + 至少一个模型。**协议三选一**：
  - `openai-completions`（OpenAI Chat Completions）
  - `openai-responses`（OpenAI Responses API）
  - `anthropic-messages`（Anthropic Messages API）
- 一个 provider 只能说一种协议；网关若同时提供两种协议，需要建两个 provider。
- 配置落盘 `$DSH_HOME/settings.yaml`（凭据在 `.credentials.yaml`，**只写不可读**，页面只拿到脱敏描述符）。
- **兼容性开关**（多数网关需要）：`compat.supportsDeveloperRole: false`、`compat.maxTokensField: max_tokens`。
- **OAuth 登录类 provider（如 Codex）目前不支持。**

> ✅ **对 LeadGen 的意义**：Groq / Cerebras / Mistral / OpenRouter / 本地 vLLM 都是 OpenAI 兼容端点，全部可通过"自定义 provider"接入。**免费额度红线不被违反。**
> ⚠️ 但注意：dsh 只提供"客户端"能力，它**不会**给我们任何新的免费额度；LeadGen 现有的免费 provider 池（`app/voice_agent/free_ai.py`，含 429 熔断）才是额度来源。

---

## ⚖️ 与 LeadGen AI 的适配性评估

| 维度 | 评估 | 说明 |
|------|------|------|
| 运行时匹配 | 🔴 差 | dsh = Node/TypeScript；LeadGen = Python/FastAPI + Docker |
| 成熟度 | 🟠 风险 | alpha.2，明确破坏性变更警告；创建仅 5 周 |
| 功能重叠 | 🟠 高 | 我们已有 31 agents + ADR-131 skill 注册表 + 任务台账 + 9-worker 调度 |
| 免费额度红线 | 🟢 通过 | 自定义 OpenAI 兼容 provider 可接免费池 |
| 部署面 | 🟠 增加 | 单台 Hostinger VPS 已跑 ~13+ 容器；再加 Node 单体仓库（206 MB） |
| 许可 | 🟢 友好 | MIT |
| 安全姿态 | 🟢 良好 | 有 `SAFETY.md`、沙箱/审批策略接缝、凭据只写 |
| 可借鉴价值 | 🟢 高 | 插件可回收副作用、capability seam、Agent Teams、session 投影 |

### 为什么**不建议**进生产
1. **运行时错配**：为一套 alpha 的 Node harness 在单台 VPS 上引入第二套运行时与依赖树，与"最小可验证变更"原则冲突。
2. **功能重叠**：我们的 agent/skill/ledger 三件套已经跑在真实付费客户上；迁移是数月级工程，收益不明。
3. **成熟度**：作者自己写明"会有破坏性变更"——生产依赖 alpha 是明确的反模式。
4. **无新增额度**：它不提供免费额度，只提供编排能力，而我们已有编排。

### 有价值的**非生产**用途
1. **本地开发加速器**：作为本仓库的编码 agent harness 试跑（类比 Claude Code 定位）。
2. **参考架构**：`packages/skill`、`packages/subagent`、`packages/schedule`、`packages/guard`、`packages/deliverables`、`packages/goal`、`packages/plan` 与我们自建能力高度同构，值得对标抄作业。
3. **插件可回收副作用（reversible effects）**：这是我们对 ADR-131 skill 注册表可以借鉴的健壮性模式。
4. **"Model-visible means logged" 不变式**：可直接启发我们的审计/合规留痕设计。

---

## ✅ 行动清单

| # | 行动 | 负责角色 | 紧急度 | 预期完成 |
|---|------|---------|--------|---------|
| 1 | 业主指定方向（深度评估 / 沙箱试跑 / 模式提取 / 仅存档） | 业主 | P0 | 本轮 |
| 2 | 若选沙箱试跑：本地克隆 + `pnpm install` + 接一个免费 OpenAI 兼容 provider，**完全不碰生产** | Rex（SRE） | P1 | 待批 |
| 3 | 若选模式提取：精读 `packages/skill` + `packages/subagent` + `packages/guard`，产出 adopt/adapt/reject 备忘 | Archi（架构师） | P1 | 待批 |
| 4 | 明确写下"不引入生产"的决策记录（ADR），避免以后重复讨论 | Docu（文档师） | P2 | 待批 |

---

## ⚠️ 待完善 / 已知局限

- 本报告为**分诊级**：仅覆盖"是什么 / 多成熟 / 能否用"。**未做**：源码级安全审计、性能基准、与 `app/agents/` 的逐项能力映射、许可证兼容性逐包核查（`THIRD_PARTY_NOTICES.md` 未读）。
- 未实际克隆运行 —— 所有结论来自 GitHub API + 官方 README / `docs/architecture.md` / `docs/user/guide/providers.md` 的实时抓取。
- Star 数异常高（229,721）且 `open_issues_count = 0`，与"5 周新仓库"组合不寻常；**未验证**其统计口径，评估时不应把 star 数当作质量证据。
- `docs/config-catalog.md`（完整配置字段目录）与 `docs/cookbook/adding-an-llm-adapter.md` 未细读。

---

## 📚 数据来源 & 成员产出索引

| 来源 | 内容 |
|------|------|
| GitHub REST API `/repos/deepseek-ai/deepseek-harness` | 许可、star、fork、创建/推送时间、体积、topics |
| GitHub REST API `/git/trees/master?recursive=1` | 13,854 路径、54 个 package、文档定位 |
| `git ls-remote` | 默认分支 `master`、HEAD `ddefc45f` |
| `README.md`（raw） | 定位、运行方式、developer preview 警告、许可、引用 |
| `docs/architecture.md`（raw） | Cordis、插件树、核心组件、事件、Agent/Subagent、扩展映射 |
| `docs/user/guide/providers.md`（raw） | 内置 provider、自定义 provider 表单、三种协议、compat 开关、排障 |

> 本报告由工程保障团队 AI 协作生成，关键决策请由人类工程负责人复核。
