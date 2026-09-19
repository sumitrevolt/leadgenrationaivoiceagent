# 技术选型报告：DeepSeek Harness (`dsh`) 对 LeadGen AI 的适配性

**日期**：2026-09-19
**工作流**：工作流 2（系统设计 / 技术选型）— 完整评估（承接同日分诊）
**参与成员**：Zhen（工程督导·编排）· Archi（架构师）· Cody（安全审查）· Rex（SRE·可运维性）· Tessa（测试）· Docu（文档·骨架与规范）
**评估对象**：https://github.com/deepseek-ai/deepseek-harness · 克隆 HEAD `ddefc45f` · 版本 `0.1.6-alpha.2`
**证据标签**：`PRODUCTION-PROVEN` · `LIVE-VERIFIED` · `TEST-PROVEN` · `READY-TO-DEPLOY` · `CODE-PRESENT` · `LOCAL-ONLY` · `PARTIAL` · `GATED-INERT` · `STALE` · `BLOCKED` · `UNKNOWN`

---

## 📌 TL;DR（执行摘要）

- **本次评估的核心发现不是"要不要引入 dsh"——而是我们早就引入了。** 仓库内已存在两套独立的 dsh 集成：一个 **pattern steal**（ADR-180，typed SessionEvent + hash-chain）和一个 **hardened child-process 运行时**（`app/tasks/dsh_jobs.py`）。**两者在生产中都是 GATED-INERT。**
- **我（主理人）先前的分诊结论"不要进生产"是基于不完整信息，此处正式更正。** 实际做法比那条建议更好：不引入依赖，只取模式；运行时隔离在子进程里。这不是失误，是正确的工程判断。
- **真正的风险不在"引入"，而在"已引入部分的缺口"**：durability 无 fail-closed 保证、loop 无自愈、invariant 无 runtime 自检、版本 pin 到 `47f943859bef` 而 upstream 已在 `ddefc45f` 且厂商明示破坏性变更。
- **顺带发现两个真实的生产缺陷**（非 dsh 相关，由本次评估暴露）：`register_skill()` 静默覆盖（`app/agents/skills.py:263-271`，零测试覆盖），以及 `skill_pack` 删除技能后 300s 内仍向 prompt 注入（`app/platform/skill_pack.py`，无 unload 路径）。
- **严重度分布**：🔴严重 1 / 🟠高 2 / 🟡中 2 / 🟢低 2 · 阻塞项 1（全部 owner-gated 或代码可解）

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| 整体评级 | 🟡 **有条件通过** — 现有集成保留并加固；不新增生产依赖 |
| 阻塞项数量 | 1（dsh 版本 pin 与 upstream 漂移，需 owner 定 upgrade 触发条件） |
| 关键行动项 | 6 条 |
| 建议下一步 | 先补 3 个缺口（fail-closed durability / runtime invariant / loop 自愈），再决定是否升 pin |

---

## 🧭 评估范围与方法

**读了什么**：`C:/tmp/dsh` 的 sparse clone（59 MB — `packages/{skill,subagent,guard,schedule,goal,plan,session,core,deliverables,runtime-diagnostics}` + `docs/`）；GitHub REST API（repo 元数据、tree）；`README.md` / `docs/architecture.md` / `docs/capability-seams.md` / `docs/user/guide/providers.md`；以及本仓库的 `app/tasks/dsh_jobs.py`、`app/api/dsh_internal.py`、`app/agents/harness/`、`app/agents/skills.py`、`app/platform/skill_pack.py`、`app/telephony/compliance.py`、`app/worker.py`。

**跑了什么**：`git ls-remote`、`git clone --depth 1 --sparse`、GitHub API 调用、本仓库 pytest（只读）。**未**运行 dsh 本体，**未**触碰生产 VPS。

**没做什么**：源码级逐包安全审计；性能基准；`THIRD_PARTY_NOTICES.md` 逐包许可核查；未在 WSL2/容器内实跑 dsh 取真实 RSS。

**证据规则**：每条结论**恰好一个标签**，且标签是**措辞强度的上限**——`CODE-PRESENT` 的结论不得写成"生产可用"；`STALE` 的文档结论不得用现在时陈述。此约定与仓库既有 runbook 一致。

> **诚实声明（Docu 建议，采纳）**：**我们对 dsh 的认知来自读它的代码，对本仓库的认知来自运行中的系统——所以"dsh 做了 X"的可信度低于"我们有 Y"。** 下表中凡涉及 dsh 的行几乎全是 `CODE-PRESENT`。

---

## 🔎 事实核查表

| 字段 | 实测值 | 来源 | 标签 |
|------|--------|------|------|
| 仓库 | `deepseek-ai/deepseek-harness` | GitHub API | LIVE-VERIFIED |
| 描述 | "DeepSeek Harness: Everything is a Plugin." | GitHub API | LIVE-VERIFIED |
| 许可证 | **MIT** | GitHub API `license.spdx_id` | LIVE-VERIFIED |
| 主语言 | **TypeScript** | GitHub API | LIVE-VERIFIED |
| Stars / Forks | **229,721 / 27,488** | GitHub API | LIVE-VERIFIED |
| 创建 / 最后推送 | **2026-08-13** / 2026-09-17 | GitHub API | LIVE-VERIFIED |
| 体积 / 路径数 | ~206,488 KB · **13,854** | GitHub API tree | LIVE-VERIFIED |
| 包数量 | **54** | GitHub API tree | LIVE-VERIFIED |
| 版本 | `0.1.6-alpha.2`（developer preview） | 仓库文件列表 | LIVE-VERIFIED |
| 默认分支 / HEAD | `master` / `ddefc45f` | `git ls-remote` | LIVE-VERIFIED |
| 依赖闭包 | **561 pkgs / 72 direct**，含 native（node-pty、sharp、koffi、ripgrep） | `dependency-catalog.json` | CODE-PRESENT |
| 许可风险 | 仅宽松许可；copyleft = MPL-2.0（libreoffice-kit）+ dev-only LGPL/MPL。**无 GPL/AGPL/SSPL** | `THIRD_PARTY_NOTICES.md` | CODE-PRESENT |
| **本仓库既有集成** | `app/tasks/dsh_jobs.py`（20,098 B）· `app/api/dsh_internal.py`（14,268 B）· `app/agents/harness/`（20+ 模块） | 直接读取 | **CODE-PRESENT / GATED-INERT** |
| 我们 pin 的版本 | `RUNTIME_VERSION = "47f943859bef"` | `app/tasks/dsh_jobs.py:29` | CODE-PRESENT |
| ADR-180 状态 | 已 DEPLOYED 2026-08-14（`150bf898`，PR #356） | `docs/context/CURRENT_STATE.md:197` | CODE-PRESENT |
| ADR-180 开关 | `HARNESS_SESSION_EVENTS` — **OFF default** | `app/api/automation_flags.py:238` | CODE-PRESENT |

---

## 🏗️ 架构与适配性

### 我们已有的两套 dsh 集成（本次评估的关键发现）

**集成 A — Pattern steal（ADR-180）** `CODE-PRESENT / GATED-INERT`
- `app/agents/harness/session.py:1` — `"""Typed session events + per-run hash-chain (dsh pattern steal, ADR-180)."""`
- 取的是 dsh 的 **append-only session event + 哈希链** 思路（`seq` / `prev_hash` / `event_hash`）
- 开关 `HARNESS_SESSION_EVENTS` 默认 **OFF**，历史键不变
- 同一 pattern 已复用至 `app/dev_control/ledger_hash.py`、`app/models/dev_task_event.py`
- 记录：`docs/HARNESS_HEALTH.md:23`、`app/agents/harness/audit.py:78`

**集成 B — Hardened child-process 运行时** `CODE-PRESENT / GATED-INERT`
- `app/tasks/dsh_jobs.py`：`DSH_QUEUE="dsh"`、`DOMAIN_QUEUE="celery"`
- `RUNTIME_BINARY="/usr/local/bin/dsh-jsonrpc-agent"`、`RUNTIME_CONFIG="/usr/local/bin/cordis.yml"`、`RUNTIME_VERSION="47f943859bef"`
- 子进程 env **白名单化**：`{DSH_RUN_TOKEN, DSH_MCP_URL, DSH_LLM_BASE_URL, DSH_CORDIS_CONFIG, HOME}` — 无任意 env 泄漏
- `app/worker.py:35` 注释：*"Hardened DSH orchestration + governed domain bridge (INERT default)"*；任务路由 `:257-258`
- `app/api/dsh_internal.py`：token 绑定的 MCP + OpenAI 兼容网关；`app/main.py:1464-1466` 挂载，`_dsh_internal_auth_gate` 中间件 `:1474`
- 边界设计：**子进程 + JSON-RPC + 白名单 env**，而非 in-process plugin

### 适配性判定

| 维度 | 评估 | 说明 |
|------|------|------|
| 运行时匹配 | 🟢 已解决 | 子进程隔离 → 不需要在 Python 进程内嵌 Node |
| 依赖风险 | 🟢 已规避 | pattern steal 而非依赖引入 |
| 成熟度 | 🟠 风险 | alpha.2 + 厂商明示破坏性变更；我们 pin 在 `47f943859bef` |
| 功能重叠 | 🟡 部分 | `app/agents/harness/` 与 Cordis 的 seam/invariant 模型仍有缺口 |
| 免费额度红线 | 🟢 通过 | 自定义 OpenAI 兼容 provider 可接免费池；**dsh 不提供新额度** |
| 安全姿态 | 🟠 需隔离 | dsh 沙箱**只管写**，读与网络不受限；默认开启 session-log 上传 |
| 许可 | 🟢 友好 | MIT，无 copyleft 传染 |
| 部署面 | 🟡 可控 | 无 Dockerfile/compose；我们自持部署路径 |

> **为什么不上生产（作为新增依赖）**：单台 VPS 已跑 13+ 容器；dsh 是 developer-preview 且厂商 SAFETY.md 自述 *"must not be treated as secure or production-ready"*、*"has not undergone a security audit"*，并建议 *"prefer a disposable VM/container"*。**现有做法（pattern + 隔离子进程 + 默认 INERT）已经吸收了它的价值，同时避开了依赖风险——这个判断是对的，应保持。**

---

## ⭐ 模式登记册（Pattern Register）

> 读法：`Payoff` 必须落在 Revenue / Compliance / Reliability 三者之一。排序 = Verdict（ADOPT → ADAPT → REJECT）→ Effort 升序。

| # | Pattern | dsh 来源路径 | 我们的现状（或 `none`） | Verdict | Effort | Payoff | 风险 | Evidence |
|---|---------|-------------|----------------------|---------|--------|--------|------|----------|
| 1 | Fail-closed durability checkpoint（model request / 外部副作用 / 下一步之前落盘；失败则不执行） | `packages/session/session-checkpoint-policy/README.md` | 部分：`app/tasks/dsh_jobs.py` 有 run_store claim/heartbeat；pending-blob rail 今日刚修 | **ADOPT** | M | Reliability: 崩溃不再丢 CRM 归属/状态推进 | 迁移期双写不一致 | CODE-PRESENT |
| 2 | Interrupted work → **unknown outcome，不自动重试** | `session-checkpoint-policy` README（"Do not retry blindly."） | `none` — 外呼/邮件是不可逆副作用，目前无此语义 | **ADOPT** | M | Reliability: 消除重复拨打/重复发送 | 需与幂等键对齐 | CODE-PRESENT |
| 3 | Package-owned runtime invariant registry（自检 + 归属包名 + allow/blocklist） | `packages/runtime-diagnostics/invariants/README.md` | 仅测试期：`app/platform/runtime_data_ratchet.py` | **ADAPT** | S–M | Compliance: 运行时自检，而非只在 CI | 误报会拖慢启动 | CODE-PRESENT |
| 4 | Guard-must-fail（人为注入回归，必须变红，再回退） | `docs/testing.md:40` | `tests/test_runtime_data_ratchet.py` 已有合成工厂 `_f(**over)` | **ADOPT** | S | Reliability: 让"守卫"不沦为装饰 | 无 | CODE-PRESENT |
| 5 | Effect-reversal-on-unload（卸载后副作用必须回卷） | `packages/session/session-checkpoint-policy/tests/*.spec.ts:231-249` | `none` — `skill_pack` 只有 1 处 cache-bust（写在 `author()` 内） | **ADOPT** | S | Compliance: 撤回的 skill 不再注入 prompt | 无 | CODE-PRESENT |
| 6 | Advisory loop-hygiene guard（3/5/8 次重复调用后 nudge，永不阻断） | `packages/guard/repeat-tool-reminder/README.md` | `none` | **ADAPT** | S | Reliability: 卡住的循环不再烧 token | 阈值调优 | CODE-PRESENT |
| 7 | Relationship-invariant 作为测试 oracle（断言事件间关系，而非返回值） | `packages/core/session/src/invariant.ts` | `none` — 现有单测只断言单模块返回值 | **ADAPT** | S–M | Compliance: 抓到单测结构上抓不到的日志不一致 | 需回放装置 | CODE-PRESENT |
| 8 | Dual-plane validate-then-apply（先校验后提交，回滚不留脏 trace） | `invariant.ts:237-245` | `none` | **ADAPT** | M | Reliability: 写失败不留内存/log 分歧 | 仅在采用 #3 后有意义 | CODE-PRESENT |
| 9 | 通用 plugin registry（`register`/`dispose` 全模块生命周期） | `packages/{skill,subagent,core}/` | `app/platform/skill_pack.py` + `app/agents/skills.py` | **REJECT** | L | — | 收益需要 54 个独立发包；我们只有一台机器 | CODE-PRESENT |
| 10 | Snapshot record/replay 测试装置 | `vitest.snapshot.config.ts` | 扁平 `tests/test_*.py`（约 950 文件） | **REJECT** | L | — | 扁平快测是我们的特性，不是缺陷 | CODE-PRESENT |
| 11 | 默认上传 session log 到厂商 API | `packages/session/session-log-deepseek/README.md`（`enabled: true`） | `none`（且绝不应有） | **REJECT** | — | — | **PII/密钥外泄** | CODE-PRESENT |
| 12 | 全量迁移到 dsh 作为运行时 | — | 已用 pattern + 子进程隔离替代 | **REJECT** | L | — | 第二运行时 + 13 容器 + 单机 = 运维爆炸 | CODE-PRESENT |

---

## 🔐 安全与供应链（Cody）

**Posture 结论**：凭证处理本身**做得好**（`$DSH_HOME/.credentials.yaml` 原子写、Web UI 真只写、`describe()` 返回值无关的 `CredentialInfo`、配置只存**引用**不存值、适配器按请求解析进 HTTP header 而非模型消息）。**"model-visible means logged" 不会持久化 provider key。**

### 🔴 CRITICAL
1. **沙箱只围"写"，读与网络不受限。** `SandboxMode` 只治理文件系统**效果**；`read-only` 只拒写；文档原话 *"Network and process visibility are outside this vocabulary."* → 在 owner 的机器上，agent 可读 `~/.ssh/id_rsa`、`~/.aws/*`、`.env`、TypeSafe key **并经网络外传**。*缓解*：只在**没有这些密钥**的环境运行（见结论）。

### 🟠 HIGH
2. **默认开启 session-log 上传 = 真实外泄通道。** `dsh-session-log-deepseek` 在出厂 profile 中 `enabled: true`，把**完整 canonical session log 后缀（含每个 `tool/result`、读过的文件内容、命令输出）随每次请求上传至官方 DeepSeek API**。叠加 #1，读 `.env` 即外传。另 `session-telemetry/record` **不附带任何脱敏规则**。*缓解*：`session-log-deepseek.enabled: false`；不挂 OTel 或先挂脱敏。
3. **`pnpm install` 会执行仓库内代码并写 git 配置。** 根 `postinstall: node scripts/install-lefthook.mjs` — 装 lefthook hooks + 注册 merge driver。*缓解*：只在隔离环境安装；优先 `npx` 发布包。
4. **运行时插件安装 = 任意代码面。** `plugin_manager` "Package installation can execute allowed build scripts"，仅由 danger-full-access/approval 把关。`sdk-minimal` 还 pin 了 `danger-full-access`。
5. **Windows 沙箱执行是 `partial`。** "the Windows ACL runner grants no explicit writable root and reports partial enforcement for its ambient ACL gaps" — 即便**写**约束在 Windows 11 上也不完整。

### 🟡 MEDIUM
6. **provider key 落盘是明文 YAML。** 无 keytar/DPAPI/safeStorage/keychain。按 `.env` 的等级对待。
7. **依赖面大且 native 重。** 561 包 / 72 直接；含 `node-pty`、`sharp`/libvips、`koffi`(FFI)、`@vscode/ripgrep`、自研 `node-addon-system`；SDK 面含 Anthropic、AWS Bedrock + 8 个 `@aws-sdk/credential-provider-*`、Google GenAI、MCP SDK、OTel、protobufjs、smithy、octokit。每个都是信任点。

### 🟢 LOW
8. Web UI 首登用 token-in-URL（本地工具常规做法），可经浏览器历史/referrer 泄漏；进程级生命周期限制了影响。保持 loopback。
9. `.gitignore` 覆盖 `.env`、`.sessions/`、`.storages/`、`node_modules/`；`$DSH_HOME` 默认在仓库外。（小坑：若有人把 `DSH_HOME` 设进仓库，`.credentials.yaml` 未被忽略。）

### ⚠️ 待确认（未验证）
- **`dsh web` 实际生效的默认 bundle posture。** 文档自相矛盾：sandbox-policy 默认 `read-only` vs 预设表出厂 `workspace-write`。bundle 组成不在 sparse clone 内。**在信任任何默认值前，先跑 `dsh --profile web --dump-config` 读 `sandbox/mode` + `approval/policy` + `permissionPresets.defaultPreset`。**

### 值得保留的好设计（不要丢）
凭证 seam（引用 vs 值、只写 UI、按操作解析）；approval **fail-closed 且单调**（守卫只能拒绝，不能强制放行）；子进程 env 自动擦除 `*KEY*/*SECRET*/*TOKEN*/*PASSWORD*` + 私有 `0700` 溢出目录（`'wx'`/`0o600`）；SSRF 加固的 `web_fetch`（拒绝非公网 IPv4/IPv6 含 DNS64/NAT64、钉住地址、每次重定向复检、拒 URL 凭证）；loopback 绑定 + Host/Origin + token 鉴权；静态服务 403 路径穿越；3 个透明哈希依赖补丁；仅宽松许可；生成且 CI 校验的第三方声明。

**Cody 结论**：**按现状，在 owner 的生产相邻工作站上不可接受**（developer preview、厂商自述无安全审计、只写沙箱 + 无限制读/网络、默认开启 session-log 上传，而该机器持有生产 SSH key）。**仅在**一次性 VM/容器、或移除生产密钥的专用非特权账户内可接受，且须：`session-log-deepseek.enabled: false`、不挂 OTel（或先挂脱敏）、approval 保持 `ask`、**永不** `danger-full-access`、工作区指向一次性 checkout（**绝不**是 LeadGen 仓库或 `$HOME`）、先用 `--dump-config` 确认默认姿态——**并轮换 agent 可能读过的任何凭证**。

---

## ⚙️ 可运维性 GO / NO-GO（Rex）

### 资源成本
- **源码构建路径**：Node `^22.19.0 || >=24`；`pnpm@11.7.0` pin；**仅 host typecheck 就要 4 GB 堆**（`node --max-old-space-size=4096 ... tsc -b tsconfig.host.json`）；另有 client tsc、两轮 tsdown、vite web build、native addon build。**实测本机：15.8 GB RAM 中仅 1.2 GB 空闲**，C: 316 GB 中 69 GB 可用。→ **本机源码构建当前不可行**（1.2 GB 空闲 vs 4 GB 堆需求）。
- **发布包路径（`npx @deepseek-ai/dsh web`）**：Node 22.19+ **已满足**（本机 v22.22.2）。估算运行时 RSS 空闲 250–500 MB；每活跃 session +300–800 MB；若动用 browser/computer-use **+1–2 GB**。安装足迹 **UNKNOWN（估算 500 MB–2 GB）**。
- **`$DSH_HOME`**（默认 `~/.dsh`）存 session JSONL（±zstd）、storage、凭证、profile。session **append-only 且应用永不裁剪** → 只增不减，需我们自建保留与备份策略。大小 UNKNOWN。
- **VPS 余量：UNKNOWN — 我未触碰生产。** 决策门槛：除非 PSI 内存压力低且新进程峰值后**确实仍有 ≥2 GB 空闲**，否则不往已跑 13 容器的机器上加 Node 进程。注意 VPS 上**可能根本没装 Node**。

### 新增故障面
1. 第二语言运行时（新 CVE 流、新补丁节奏、Node OOM / 事件循环停滞 / unhandled rejection）。
2. 第二包管理器 + 安装期代码执行（`allowBuilds` 跑 esbuild/node-pty/koffi/lefthook 脚本；3 个 patched deps；postinstall 改 git 配置）。
3. 新 HTTP 服务新端口（3080；webhook overlay 3081）。`dsh web` 绑定 loopback 且**拒绝 `--host 0.0.0.0`**；鉴权 = Host/Origin + 浏览器 session + 每进程新 token。暴露需前置 Caddy → 又一个鉴权边界。
4. **插件系统 = 来自分发渠道的任意代码。** `dsh plugin add <npm pkg|tarball>`；GitHub `dsh-plugin` topic 就是发现机制——正是 typosquatting / 供应链攻击惯用面。插件挂载进与 agent loop 同一进程，**第三方插件不被沙箱隔离**。
5. 其他代码加载通道：MCP server；会 shell out 到 `claude-code`/`codex` CLI 的 subagent provider；browser/computer-use driver；入站 webhook（`ctx.webhookRuntime` **无去重、无重试、无重放保护**，重复投递会创建重复 Session）。
6. **它执行模型生成的代码与命令。** SAFETY.md 原话：*"must not be treated as secure or production-ready"*、*"has not undergone a security audit"*、*"Prefer a disposable virtual machine, container, or dedicated environment."*
7. **沙箱范围比听上去窄**（同 Cody #1）：网络与进程可见性不在其词汇内。
8. **仓库内无 Dockerfile、无 docker-compose、无部署文档。** 容器与部署路径要我们自己拥有。
9. **升级节奏是刻意的**：`minimumReleaseAgeExclude` 显示项目对自身闭包**绕过**供应链 release-age 隔离（claude-agent-sdk、codex、pi-ai、libreoffice-kit、node-addon-*），且依赖 *"published from the upstream experimental tree"* 的 `@opentelemetry/sdk-logs`。一次 dsh bump 可把全新第三方代码拖过我们的正常 hold-back 窗口。

### 升级 / 回滚 — **最弱环节**
- 版本 `0.1.6-alpha.2`，README 明示破坏性变更，**无 LTS、无弃用窗口、无安全联系人、无 SLA**。
- **session log 只进不退**：存储的 session 选**数值最高**的 canonical generation 且 *"refuses a future version"*；格式已走 v0→v1→v2→v3，每步一个迁移包 → **降级后旧二进制读不了新二进制写的 session，无向下迁移路径**。
- **无数据回滚**：generation *"never renamed, replaced, or deleted"*，只能增长。
- **回滚 ≠ 换二进制**：profile / bundle 列表 / `dsh plugin add` 安装物都在 `$DSH_HOME`；composition 模型变更会使 `cordis.patch.yml` 层失效。
- **与"单一部署权威"的冲突**：今天 `scripts/deploy_vps.sh` 是唯一权威，且 `tests/test_no_app_container_drift.py` 专门钉住"`docker compose up -d app` 是假成功"。加 dsh 要么扩展该脚本（真实成本，且必须对 drift test 诚实），要么另起一条并行路径——**而那正是该测试要禁止的**。

### 仅开发用 — **隔离是干净的，但必须"建"，不能"假设"**
- 本机 Windows 沙箱后端是 ACL restricted-token runner，文档自述 `partial`；**非提权 + Home 版能否工作 UNKNOWN**，需冒烟测试。失败模式 fail-closed（安全）或操作者退回 `danger-full-access`（不安全）。
- **沙箱 = 只管文件效果**，无网络约束、无进程约束。
- **实测泄漏路径**：`~/.ssh` 持有 `lgvps`、`learningchain_deploy`、`gcloud_key`、`id_rsa`；`scripts/deploy_vps.sh`（生产部署权威）在本机 **≥4 处**（含 agent workspace）；`~/Documents/leadgenrationaivoiceagent/.env` 与 `.env.production.local` 等**真实生产密钥**同在。dsh 还自带 SSH provider family，**设计上**就可用操作者既有 SSH 身份挂载远端执行世界。
- 唯一闸门是 approval prompt（默认 `ask`，fail-closed，是真人注意力控制，**不是隔离边界**，且随操作者停止阅读而退化）。

### 可观测性 — **独立孤岛，且不是 metrics 源**
- 只有 `session-telemetry` seam + 一个 OTel **log** 后端。**无 metrics**（无 Prometheus/OpenMetrics、无 counter/gauge、seam 未接 trace exporter）。该 OTel 后端明确 *"captures no operational records"*。
- 默认 `FEEDBACK_ONLY`：无人提交反馈前**什么都不出进程**；`emit()` 在所有模式下是 no-op → **不能当通用可观测性探针**。
- **脱敏规则出厂为空**：无 listener 时，导出记录**携带消息内容、工具参数与结果、system prompt 与工具 schema、todo 文本、compaction 摘要、session cwd**。provider key 结构性缺失（构造参数，非事件）。**对 LeadGen 而言，未挂脱敏就指向共享 OTLP 端点 = PII 外泄脚枪。**
- 投递 best-effort：无持久 outbox、无投递水位、无重试；接收方须按 `(session.id, session.format_version, event.seq)` 去重。
- **集成结论**：**不会**接进 Prometheus/Grafana/Alertmanager。OTLP logs 可路由进 Loki（Loki 原生支持 OTLP ingest）→ session 事件日志可与应用日志同处搜索，但（a）受人工反馈闸门限制，不是可靠告警信号；（b）无 metrics 可告警；（c）须先有我们的脱敏层。

### 结论
- **(a) 生产运行时 — NO-GO**（优先级序）：① 厂商自述不可作安全边界 + 无安全审计 + 建议一次性 VM，而我们**只有一台机器且它就是全部生产**；② 回滚只进不退（alpha 破坏性变更 + session 格式拒读未来版本 + 全新传递闭包）；③ 制造**第二部署权威**，与 `test_no_app_container_drift.py` 冲突；④ 已在跑 13+ 容器的机器上新增托管负担；⑤ **类别错配**——agent harness 是开发者工具，生产数据面没有理由跑一个 LLM 驱动的 shell。
- **(b) 本地开发工具 — GO，有条件**：① 跑在 **WSL2 或容器**内，不带宿主 `~/.ssh`、不带生产仓库、不带 `.env`；② **绝不**用生产仓库副本作工作区；③ 不配置 SSH provider family，不为生产 VPS 加 `~/.ssh/config` 别名；④ telemetry `DISABLED`（或 `FEEDBACK_ONLY` **且挂上我们的脱敏规则**）；⑤ approval 保持 `ask`，`danger-full-access` 禁止；⑥ 不要照现状尝试源码构建（1.2 GB 空闲 vs 4 GB 堆）；⑦ 按 alpha 对待：pin 精确版本、预期配置漂移、**不要在上面建任何我们依赖的东西**。

**Rex 直白总结**：dsh 是一个**我们必须刻意缩小爆炸半径**的个人生产力 agent。它不是工程平台标准，也不是生产组件。

**Rex 未能确定**：VPS 余量（未触碰生产）；发布包精确安装足迹与运行时 RSS（未跑 `pnpm install`，文档无数字 → 均为 ESTIMATE）；Windows ACL 沙箱在非提权 Win11 Home 是否真的可用；npm 包是否把 claude-code/codex subagent 运行时与 browser-use driver 拉进默认 `dsh-base` 闭包（`packages/bundle/base` 不在 sparse clone 内，**这实质影响安装体积**）；真实升级节奏/支持流程；sparse clone 缺口（`apps/`、`packages/{bundle,host,sandbox,ssh,credentials,shell}` 缺失，这些区域仅凭文档阅读）。

---

## 🧪 测试采用计划（Tessa）

### ⚠️ 证据完整性前置声明（重要）
- `C:/tmp/dsh/pytest.ini` **只有 4 行**，仅 pin `testpaths = python/sdk/tests`。**dsh 的 Python 面只是薄 SDK；它自己的套件是 vitest。不要引用 dsh 作为 pytest 范本。**
- `packages/test-support/session-snapshot/` 被 `docs/testing.md:55` 引用，但**不在 sparse clone 内**，无法阅读。
- `scripts/` 在 clone 中为**空**，故 `verify-*` 闸门只读到名字（`package.json:106-145`），未读到实现。
- **`app/agents/skill_handlers.py` 在本仓库不存在**（与主理人独立核实一致）。真实路径是 `app/platform/skill_pack.py`（214 行）与 `app/agents/skills.py`（448 行）。

### 六项可迁移技术
| # | 技术 | dsh 路径 | 买到什么 | 我们的映射 | Effort |
|---|------|---------|---------|-----------|--------|
| T1 | **关系不变式作测试 oracle**（断言事件间关系，非返回值） | `packages/core/session/src/invariant.ts`（`validateEvent(trace,event,fail)` + 暂存 apply），由 `contract-regressions.spec.ts:16` 挂载 | 抓到单测**结构上抓不到**的日志/流不一致（如 `seq` 非严格递增、`tool/result` 无前置 `tool/call`） | `app/platform/interaction_log.py` 已是 append-only JSONL；加 `tests/invariants/test_interaction_log_invariants.py`，纯函数校验 + 回放装置 | S–M |
| T2 | **Guard-must-fail（变异自测）** | `docs/testing.md:40` | 让"守卫"不沦为装饰 | `tests/test_runtime_data_ratchet.py` 已有合成工厂 `_f(**over)`；补 `test_ratchet_rejects_synthetic_new_unresolved` | S |
| T3 | **Effect-reversal-on-unload** | `session-checkpoint-policy.spec.ts:231-249`（跑一次 assert `flushes===1`；`dispose()`；再跑 assert **仍是 1**） | 证明副作用真的回卷 | `app/platform/skill_pack.py` 模块级 `_cache`（L39）+ `_load_all` TTL memo（L85） | S |
| T4 | **Crash/failpoint 恢复，断言 unknown-outcome** | `crash-recovery.e2e.ts`（marker 文件 + `SIGKILL` + 重开日志断言 `ToolOutcomeUnknownError` / "Do not retry blindly."） | 证明不可逆副作用不会重复 | 外呼/邮件不可逆；`tests/_runtime_data_scan_subprocess.py` 已有子进程 + 原子发布模式可复用；幂等键来自 `app/platform/agent_runtime_idempotency.py` | M |
| T5 | **对"检查本身"的机械接线闸门** | `verify-package-invariants`（`invariants/README.md:107`：拒绝空 installer、忽略 reporter、注册名错误、接线不完整、接线过期） | 静默失效的检查无法冒充保证 | 与我们 ratchet 同构；静态扫 `tests/invariants/*`，断言每个注册的不变式有非空体、具名 owner、未被 blocklist 静默禁用 | S–M |
| T6 | **双平面 validate-then-apply** | `invariant.ts:237-245` | 回滚的写不留下领先于日志的内存 trace | 仅在采用 T1/§4 后有意义；用故意失败的写来测 | M |

### 可逆效果：技能/agent 注册的现状（**本次评估发现的真实生产缺陷**）

**"可逆效果"在这里的具体含义**：一次 skill 注册目前有**四个**副作用、**零个**卸载路径：
1. `skill_pack._cache` — 模块级 memo，TTL 300s（`skill_pack.py:39,85`）
2. `data/skills_extra/*.md` — `author()` 写入（`:171-190`），并经 `_cache["at"] = 0.0`（`:186`）bust cache
3. Qdrant namespace `"skills"` — `ingest_to_kb()`（`:193-211`）追加；**无任何移除**
4. `SkillRegistry.skills` dict + `data/skill_registry.json` — `register_skill`/`unregister_skill` 都 `_save_registry()`（`skills.py:263-281`）；模块单例 `_skill_registry`（`:421`）

**生产回归风险（按风险排序）**：
- **R1（HIGH，合规）** — `skill_pack` **没有任何 `unload`/`remove`/`delete` 函数**（grep = 0）；唯一的 cache-bust 在 `author()` 内，**只在写入时触发**。技能文件被删除后 cache 不失效，`snippet_for()` 仍会把它注入 prompt。**主理人独立核实：`_load_all()` L85 的 TTL 判断把窗口上界限定为 `_CACHE_TTL_S = 300` 秒——Tessa 原文的 "indefinitely" 是过度声称，实际 ≤300s。**
- **R1b（主理人补充发现）** — `_load_all()` 的 L111-112（`_cache["skills"] = out; _cache["at"] = now`）**在 except 之后仍无条件执行**。扫描抛异常时（L108-109 捕获），**部分/空列表会被缓存 300 秒** → 一次瞬时文件系统错误可让技能注入空窗 5 分钟。
- **R2（HIGH）** — `register_skill` **静默覆盖**同名技能（`skills.py:263-271`）：无错误、无审计、`return True`。dsh 的注册表会**抛** `already registered`。→ 一个 tenant 的 skill 可静默替换另一个的。
- **R3** — `_save_registry` 吞掉所有异常（`skills.py:132-143`），而 `register_skill` 已经改了 `self.skills` → 内存与磁盘静默分歧，调用方仍得到 `True`。
- **R4** — `ingest_to_kb()` 只追加；已卸载技能仍可被语义召回。
- **R5** — 模块级 `_skill_registry` 跨测试泄漏状态 → 我们本就在对抗的 flaky 类别。

**主理人独立核实**：`grep -rln "register_skill" tests/` = **0 hits**；无 effect-reversal/unload 测试。→ **R1/R2 既真实又零覆盖。**

### 采用计划
**先做（价值最高 / 成本最低）**：① T3 effect-reversal（S）——唯一**今天就可能有生产回归**的项（R1：被撤回的技能仍在注入）；② T2 guard-must-fail（S）——强化我们最成熟的资产。
**然后**：③ T4 crash-recovery unknown-outcome（M）——外呼不可逆，R1 之后残余风险最高；子进程基建已存在；④ T1 关系不变式（M）。
**最小证明**：一个纯校验器 + 一个在回放的持久日志上挂载它的测试 + **一个故意造坏的合成事件必须让它失败**。**如果造不出让它失败的合成坏事件，它就是装饰品**（dsh 自己的规矩，`docs/testing.md:40`）。

**我们阶段不值得测的**：❌ 通用 plugin 生命周期 registry（L 成本，收益需要 54 个独立发包）；❌ snapshot record/replay 装置（扁平 `tests/test_*.py` 是**特性**）；❌ 逐文件 100% 覆盖率闸门；❌ 40 个 `verify-*` 家族（取**思想**，不取家族）；❌ HMR/重注册测试；❌ 每 PR 真 API e2e。

**Effort 汇总**：T2 S · T3 S · T5 S–M · T1 S–M · T4 M · T6 M。T2+T3+T1+T5 ≈ 2–3 个专注日；T4 是唯一需要新装置工作的。
**不迁移声明**：以上**都不需要**离开 pytest 或扁平布局。

### "Model-visible means logged" 作为合规资产
依据 `docs/architecture.md:125`：*"Anything that reaches a model request must be reconstructable from the log, and a runtime invariant asserts it."* 由 `dsh-agent-loop` companion 强制（"loop-built request reconstruction"，`invariants/README.md:60`）。

**为什么对我们是合规资产**：我们的义务是 DND/TRAI（拨号前遵守 scrub、留存同意与 scrub 证据）与 DPDP（数据主体访问/删除、目的限制、保留期）。两者都是**关于"什么数据到达了什么决策"的问题**。日志可重建性不变式把 *"我们相信遵守了 DND"* 变成 *"这是 append-only 记录，可从中逐字节重建确切 prompt，含 DND 检查结果与被注入的技能文本"*。

**证明它的测试** — `tests/test_prompt_log_reconstructability.py`：① `reconstruct_requests(log_events)` = 对 append-only 日志的**纯 fold**；② `assert_model_visible_subset(requests, logged_events)` = 每个到达模型的块必须可归属到某条已记录事件；③ 用**录制型 fake LLM adapter** 跑一个外呼/语音 turn 抓取确切请求，然后 fold 日志断言 `reconstructed == captured` 逐字节相等，且请求中每个 PII 字段都出现在日志里。

**接入方式**：**闸门形状**（而非检查本身）就是 ratchet。镜像 `runtime_data_ratchet.evaluate()`：已知未记录项的 allowlist（带 owner + review condition）+ 冻结基线 + 单调闸门（`new_unlogged == 0`，回归按**身份**而非计数检测）。

**诚实边界**：dsh 自己文档写明重建 *"covers loop-built requests only"*，*"direct one-shot LLM calls remain outside that contract"*（`invariants/README.md:154`）。我们有大量 one-shot 调用点（`auto_outreach.py`、`wa_conversation.py`、`squad_voice_calling.py`）。**硬性 day-one 闸门会标出大量清单——所以必须是 allowlist + 基线 ratchet，绝不在首次落地时硬失败。**

---

## 💰 免费额度红线与成本影响

**结论：不违反。** 模型适配器挂在 `ctx.llm` seam 上；除内置目录（`anthropic`/`openai`/`moonshotai`/`zai` + DeepSeek 自有路由）外，**"Add a custom provider"** 接受任意 `baseURL` + 三选一协议（`openai-completions` / `openai-responses` / `anthropic-messages`）→ Groq / Cerebras / Mistral / OpenRouter / 本地 vLLM 全部可接。`CODE-PRESENT`

**但必须说清楚**：**dsh 不提供任何新额度。** 它只提供编排能力，额度仍来自我们自己的免费池（`app/voice_agent/free_ai.py`，含 429 熔断）。**OAuth-only provider（如 Codex）目前不支持。**

---

## ✅ 行动清单

| # | 行动 | 负责角色 | 紧急度 | 预期完成 | 证据标签 |
|---|------|---------|--------|---------|---------|
| 1 | **写下 ADR：不将 dsh 作为新增生产依赖引入**（现有 pattern + 子进程集成保留）。REJECT 不落 ADR 会在 3 个月后被重新翻案 | Docu / 业主 | P0 | 本轮 | — |
| 2 | **修 `register_skill` 静默覆盖**（`app/agents/skills.py:263-271`）：要么抛错要么留审计记录；并补 `tests/test_skill_effect_reversal.py` | 待指派 | P0 | 1 日 | CODE-PRESENT |
| 3 | **修 `skill_pack` 无卸载路径**（R1/R1b）：加显式 unload 并 bust cache；修 `_load_all` 异常路径的 300s 空缓存 | 待指派 | P0 | 1 日 | CODE-PRESENT |
| 4 | **补 fail-closed durability + unknown-outcome**（模式 #1/#2）到外呼与邮件路径 | 待指派 | P1 | 3–5 日 | CODE-PRESENT |
| 5 | **定义 dsh 版本 pin 的 upgrade 触发条件**（当前 `47f943859bef` vs upstream `ddefc45f`）；先用 `dsh --profile web --dump-config` 确认默认姿态 | Rex / 业主 | P1 | 待批 | CODE-PRESENT |
| 6 | **若要在本机试跑 dsh**：WSL2/容器 + 无宿主 `~/.ssh` + 无 `.env` + 无生产仓库 + telemetry `DISABLED`；事后轮换可能被读到的凭证 | Rex / 业主 | P2 | 待批 | — |

---

## ⚠️ 待完善 / 已知局限

- **架构深度评估（Archi）在本报告定稿时未完成**，其产出已单独索取；本报告的架构章节基于**主理人本人的文件核实**，未包含 Archi 的独立专业结论。**该章节不得视为架构师已签字。**
- **未实跑 dsh**：所有 dsh 侧结论均为 `CODE-PRESENT`（读代码/文档），无一为 `PRODUCTION-PROVEN`。
- **未触碰生产 VPS**：VPS 余量、dsh 是否已在实际运行、`dsh` 队列是否有 worker——全部 `UNKNOWN`。现有集成的标签是 `GATED-INERT`，来自代码注释与 flag 默认值，**非生产观测**。
- **sparse clone 缺口**：`apps/`、`packages/{bundle,host,sandbox,ssh,credentials,shell,fs}` 缺失；这些区域仅凭文档阅读，若决策依赖精确 CLI flag 或 bundle 组成，需更完整 checkout。
- **未做**：源码级逐包安全审计、性能基准、`THIRD_PARTY_NOTICES.md` 逐包许可核查。
- **Star 数异常**（229,721）且 `open_issues_count = 0`，与"5 周新仓库"组合不寻常；**未验证**其统计口径，**不应把 star 数当质量证据**。
- 本报告写于 2026-09-19；dsh 处于 alpha 且高频迭代，**任何 dsh 侧事实超过一周即应视为 `STALE`**。

---

## 📚 数据来源 & 成员产出索引

| 来源 | 提供了什么 |
|------|-----------|
| GitHub REST API（repo + tree） | 许可、star、fork、时间线、体积、13,854 路径、54 包 |
| `git ls-remote` | 默认分支 `master`、HEAD `ddefc45f` |
| `README.md` / `docs/architecture.md` / `docs/capability-seams.md` / `docs/user/guide/providers.md` | 定位、Cordis 模型、seam 表、provider 配置 |
| `C:/tmp/dsh` sparse clone（59 MB） | `packages/*` 与 `docs/*` 的一手阅读 |
| **Cody（安全审查师）** | 凭证 seam 评估、🔴 沙箱只写、🟠 默认 session-log 上传、供应链与依赖面、Windows 沙箱 partial |
| **Rex（SRE）** | 资源成本、新增故障面、回滚只进不退、开发隔离条件、可观测性孤岛、prod NO-GO / dev conditional GO |
| **Tessa（测试专家）** | 证据完整性声明、6 项可迁移技术、R1–R5 缺陷、合规不变式设计、采用计划与"不值得测"清单 |
| **Docu（技术文档师）** | 报告骨架、register 列集与理由、证据标签约定、语言判定、可读性风险与缓解 |
| **主理人（Zhen）本人核实** | 事实核查表、既有 dsh 集成发现（`dsh_jobs.py` / `dsh_internal.py` / `harness/`）、ADR-180 状态、R1 上界更正 + R1b 新发现、R2 与零测试覆盖确认、两处记忆路径纠错 |

---

> 本报告由工程保障团队 AI 协作生成，关键决策请由人类工程负责人复核。
