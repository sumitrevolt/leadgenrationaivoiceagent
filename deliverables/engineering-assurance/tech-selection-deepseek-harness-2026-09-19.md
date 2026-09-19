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
- **严重度分布**：🔴严重 2 / 🟠高 2 / 🟡中 2 / 🟢低 2 · 阻塞项 2（其一为代码可解但**必须原子部署**，见行动清单 #1）

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| 整体评级 | 🟡 **有条件通过**（选型结论）— 现有集成保留并加固；不新增生产依赖。**但本次评估附带暴露一个 🔴 P0 自有缺陷（两平面 allowlist 分裂），须先修** |
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

## 🔴 P0 专章：两平面 allowlist 分裂（本次评估最大的实质风险）

> 这一节**不是**关于 dsh 上游的。它是我们**自己代码**里的缺陷，由本次评估暴露。主理人独立核实代码与 compose，Cody（代码审查师）独立裁定严重度 —— 结论：**Request Changes**。

### 事实：两个平面、两个变量名、相反的失败方向

该 runtime 的身份闸门被实现在**两个互不相通的平面**上：

| | 平面 1 — 治理 / 调度 | 平面 2 — 执行 / 强制 |
|---|---|---|
| 文件 | `app/platform/workforce_runtime/dispatch.py` | `app/integrations/dsh.py` |
| 环境变量 | **`DSH_AGENT_ALLOWLIST`**（`:19`） | **`DSH_ALLOWLIST_CSV`**（`:41`） |
| 空值行为 | **fail-CLOSED** — `provider_for()`（`:45-53`）返回 `"direct"`，agent 根本不会被路由到 dsh | **fail-OPEN** — `:68-70` `if not allowlist: return True` |
| `*` 语义 | 视为 DENY（`:35`） | **无任何处理**（`*` 被当普通名字，永不匹配） |
| 唯一调用点 | `dispatch()`（`:281`） | `_run_jsonrpc()` — `app/tasks/dsh_jobs.py:170` |

### 为什么这是缺陷，而不是"两种合法设计"

**三份独立来源声明「空值 = 拒绝」，两份实现「空值 = 放行」。**

| 来源 | 原文 | 主张 |
|------|------|------|
| `app/tasks/dsh_jobs.py:167` | `# Allowlist check (fail-closed).` | 拒绝 |
| `app/platform/automation_flag_manifest.py:532` | `empty means no DSH authority or shadow` | 拒绝 |
| `app/api/automation_flags.py:241` | `empty = none` | 拒绝 |
| `app/integrations/dsh.py:69-70` | `return True  # No allowlist = allow all` | **放行** |
| `tests/test_dsh_integration.py:109-113` | `test_empty_allowlist_allows_all` 断言 `is_dsh_allowed(agent_id="any_agent") is True` | **放行** |

调用点自己的注释写着 fail-closed，而它调用的函数是 fail-open；声明契约的 manifest 写着 `empty = none`，而实现放行一切。**这不是"意图不明"，是文档契约被自己的实现和一个被 pin 住的测试推翻。** 该测试的存在意味着这个行为是**被固化**的，不是疏漏 —— 修它必须同时改测试。

### 生产影响：闸门是死的（`CODE-PRESENT`）

主理人独立核实（直接读 compose，非推断）：

- `_run_jsonrpc()` 运行在 **`leadgen_dsh_worker`** 容器内 — `app/dsh_worker.py:24` `include=["app.tasks.dsh_jobs"]`，`:32` 把 `run_dsh_workforce` 路由到 `dsh` 队列。
- 该服务的 env 块（`docker-compose.vps.yml:878-887`）为：`APP_VERSION, REDIS_URL, DSH_RUNTIME_ENABLED, DSH_SHADOW_ENABLED, DSH_MCP_URL, DSH_LLM_BASE_URL, DSH_TOKEN_BACKEND, DSH_RUN_STORE_BACKEND, HOME`。**`DSH_ALLOWLIST_CSV` 与 `DSH_AGENT_ALLOWLIST` 都不在其中。**
- 更进一步：**`DSH_ALLOWLIST_CSV` 在整个 `docker-compose.vps.yml` 中一次都没出现。** `DSH_AGENT_ALLOWLIST` 有（`:77`、`:149`），但那是 **`app` 服务**，不是 `dsh-worker`。前者只存在于一个陈旧的 `docs/openclaw/vps.yml`。
- ⇒ 在执行该检查的容器里 `get_dsh_allowlist()` 恒为空 ⇒ **`is_dsh_allowed()` 对任何 agent、任何 tool 恒返回 `True`。**

> 转 `LIVE-VERIFIED` 只差一条命令：`docker exec leadgen_app printenv DSH_ALLOWLIST_CSV DSH_AGENT_ALLOWLIST`（在 `dsh-worker` 容器上同样跑一次）。

### 实测证据（`TEST-PROVEN`）

在受控环境变量下直接调用两个平面的公开函数（`.venv` Python 3.11.14，每个实验一个独立进程；探针脚本写在 `%TEMP%`，**未改动仓库任何文件**）：

| 实验 | `DSH_ALLOWLIST_CSV` | `DSH_AGENT_ALLOWLIST` | `DSH_RUNTIME_ENABLED` | 平面 2 `is_dsh_allowed("unlisted")` | 平面 1 `provider_for` |
|------|--------------------|----------------------|----------------------|-----------------------------------|----------------------|
| **E1** | UNSET | UNSET | UNSET | **`True`** ⚠️ | 全部 `direct` |
| **E2** | `""` | UNSET | UNSET | **`True`** ⚠️ | 全部 `direct` |
| **E3** | `jiya_makeover` | UNSET | UNSET | `False` ✅ | 全部 `direct` |
| **E5b** | UNSET | `kavya` | `1` | **`True`** ⚠️ | `kavya`→**`dsh`**；其余 `direct` |
| **E6b** | UNSET | `*` | `1` | **`True`** ⚠️ | **全部 `direct`**（`*` = DENY） |
| **E7b** | `kavya` | `kavya` | `1` | `False` ✅ | `kavya`→`dsh`；其余 `direct` |

**五条硬结论：**

1. **E1 / E2 —— 平面 2 在变量缺失**或**为空时放行一切。** `is_dsh_allowed()` 对未列出的 agent 返回 `True`。fail-open 已实证（不是推断）。
2. **E3 —— 平面 2 不认识 `*`。** allowlist 非空时 `is_dsh_allowed(agent_id="*")` 返回 `False` —— `*` 被当成普通名字。**与平面 1 相反**（平面 1 把 `*` 解读为"清空 allowlist → 全部 `direct`"）。
3. **E5b —— 两个变量名的分裂是真的，而且正好裂在危险的那一半。** 只设 `DSH_AGENT_ALLOWLIST=kavya` 时：平面 1 正确地把 `kavya` 送进 `dsh`，而平面 2 的 allowlist **仍是 `[]`** → 对任何人都放行。**满足一个闸门完全不满足另一个。**
4. **E6b —— 平面 1 的 `*` = DENY 得到实证**，与 ADR-183 原文 *"`DSH_AGENT_ALLOWLIST=*` remains forbidden（empty-set semantics → all direct）"* 一致。
5. **E7b —— 这就是修复的目标状态。** 两个变量设成同一份 CSV 时，两个平面一致：allowlist `["kavya"]`、未列出者 `False`、`kavya`→`dsh`。

> 「环境变量缺失/为空时**两个平面朝相反方向失败**」这一条，已从"读代码推断"升级为**实测**。本报告该结论的标签由 `CODE-PRESENT` 升为 **`TEST-PROVEN`**；compose 层的事实（`DSH_ALLOWLIST_CSV` 不在 `docker-compose.vps.yml`）仍为 `CODE-PRESENT`，待 `printenv` 升 `LIVE-VERIFIED`。

> **两次独立执行、结论一致。** 上表由主理人执行；Tessa 用独立探针（`%TEMP%\dsh_probe.py`）在独立进程中重跑，六项结果**逐项一致**，无一项相左。

### guard-must-fail：修复会打红哪个测试（`TEST-PROVEN`）

按 dsh 自己的规矩（`docs/testing.md:40`），一个"守卫"必须在注入回归后**变红**，否则它只是装饰品。对 `dsh.py:69-70` 反转成 fail-closed 做了变异自测（monkeypatch 注入 + **执行真实测试文件**，不是纸面推演）：

| | 结果 |
|---|---|
| **现状（fail-open）** | `test_dsh_integration.py` = **20 passed / 0 failed / 0 skipped**；`test_dsh_workforce_runtime.py` = **28 passed / 0 failed / 0 skipped** |
| **注入 fail-closed 后** | **1 failed / 19 passed** |
| **唯一变红的测试** | `tests/test_dsh_integration.py::TestDSHAllowlistCheck::test_empty_allowlist_allows_all` |

**三条可执行结论：**

1. **修复的测试面极小 —— 只有一个测试需要翻转。** 另外三个 `is_dsh_allowed` 断言用的是**非空** allowlist，不受影响。行动 #1 的成本因此从"可能牵动一大片"降到"确定只动一处"。
2. **守卫确实会失败** —— 该测试是真的在保护当前行为，不是空转。**只是它保护的是错的那一侧。**
3. **验收标准可验证**：修复后 `test_dsh_integration.py` 与 `test_dsh_workforce_runtime.py` 应仍全绿（20 + 28），且断言方向相反。

> 两个测试文件当前**全绿**，这本身就是本次缺陷的注脚：**48 个测试通过，没有一个是关于"闸门到底朝哪边失败"的。** 缺的不是测试数量，是测试的**问题**。

### 严重度裁定（Cody）：🟠 HIGH — 是"身份检查缺失"，不是"权限提升"

**不要夸大。** 平面 1 仍然有效：非 allowlist 的 agent 不会被 `dispatch()` 路由到 dsh。且即便有人绕过路由，**能力仍被 token 限制**：`tokens.issue()`（`dsh_jobs.py:180-188`）把 `agent_id` + `allowed_tools=_allowed_tools(run)` + `deadline` 绑进 token，而 `_allowed_tools()`（`:66`）为一次 run 只开放 `dsh_capability_submit:<run['action']>` —— 即该 run 自己声明的那个能力。

> **allowlist 是 WHO 闸门，token 是 WHAT 闸门。WHAT 仍然成立，WHO 是死的。** 这是缺失的身份检查，不是权限提升。

**但两条残余风险是真的：**

1. **直连入队路径绕过一切。** 任何能 `run_dsh_workforce.apply_async()` 或直接写 `run_store` 行的路径，既绕过 `provider_for`（连带绕过 `FROZEN_AGENTS` 对 `swara`/`ananya` 的保护），也绕过 `_dsh_preflight()` —— 而 `_run_jsonrpc()` 不会重跑 preflight。平面 2 本应是这条路径的最后一道闸门，而它是开着的。
2. **`FROZEN_AGENTS` 只在平面 1 强制。** `frozenset({"swara","ananya"})` 是"永不进 dsh"的硬承诺（ADR-181 原文），但执行点在 `dispatch.provider_for()`，不在执行平面。

### ⚠️ 修复必须原子 —— 天真修复会直接造成生产中断

**这是本节最关键的运维结论。** 因为 `dsh-worker` 容器里**两个 allowlist 变量都不存在**：

> **当前的 fail-open 是已 ARM 的 `jiya_makeover` lane 的承重结构。**

只做「改读 `DSH_AGENT_ALLOWLIST` + 反转 `:69-70`」会让 `dsh_allowlist_denied` 在**每一次** run 上抛出 —— 包括合法的 `jiya_makeover`。**一个安全修复会变成一次生产中断。** 三件必须一起做，缺一不可：

1. **`app/integrations/dsh.py`** — `:41` 改读 `DSH_AGENT_ALLOWLIST`（与平面 1 及 manifest 对齐）；`:69-70` 反转为 fail-closed；补 `*` = DENY 以匹配平面 1 语义。
2. **`docker-compose.vps.yml`** — `dsh-worker` 服务 env（`:887` 附近）**新增** `DSH_AGENT_ALLOWLIST: ${DSH_AGENT_ALLOWLIST:-}`。该服务刻意保持最小 env，但这是 CSV、不是密钥，与"不接收 provider 凭证"的姿态不冲突。
3. **`tests/test_dsh_integration.py`** — `:109-113` 的 `test_empty_allowlist_allows_all` 反转为 `test_empty_allowlist_denies_all`（**guard-must-fail**：改之前必须变红，改之后变绿）；若变量改名，`:74-156` 所有 `patch.dict` 键名同步更新。

### 顺带发现（同一批核查）

- **`/health` 发布的是错的 allowlist。** `app/integrations/dsh.py:54` 返回 `"dsh_allowlist": list(get_dsh_allowlist())` —— 即那个死掉的 `DSH_ALLOWLIST_CSV`；而 `dispatch.runtime_status()`（`:356`）返回 `"dsh_agent_allowlist"`，来自真正生效的变量。**两个端点，两套互相矛盾的 allowlist 真相。** 运维看一眼 `/health` 会得到错误的安心 —— 这直接违反本报告的证据可核查原则。
- **`dsh_jobs.py:169` 硬编码 `tool_token = None`**，使 `is_dsh_allowed()` 的 `tool_token` 分支成为**不可达死代码**。
- **`RUNTIME_VERSION` 字面量重复四处** —— `dsh_jobs.py:29`（常量）+ `dispatch.py:217`、`:238`、`:358`（硬编码字面量）。改 pin 时漏改任一处会静默产生错误的版本记录。

---

## 🧾 记录与代码的对账（Archi 产出 + 主理人核实）

### A1. ADR-179 vs ADR-181/183/94 —— "拒绝运行时"与"已部署运行时"并存

| ADR | 主张 | 与代码的关系 |
|-----|------|-------------|
| **ADR-179** (2026-08-14) | **REJECT** dsh 作为 runtime/dep；DeepSeek 只作 model | 对**依赖引入**仍有效：无 submodule、无 `pnpm install`、无 vendored `dsh` |
| **ADR-180** (2026-08-14) | 只偷 pattern（SessionEvent + hash-chain） | 一致：`app/agents/harness/session.py`，flag 默认 OFF |
| **ADR-181** (2026-08-14) | 仅允许 hardened source-built Linux path | 一致：`dsh_jobs.py` 子进程 + JSON-RPC + 白名单 env |
| **ADR-183** (2026-08-14) | owner override，授权 arm | **记录与观察不符** — 见 A2 |
| **ADR-94** (2026-09-10) | `DSH_RUNTIME_ENABLED=1`（runtime + shadow ON），allowlist `["jiya_makeover"]` | **与 2026-09-14 探针一致** |

**结论：不是矛盾，是编号非单调。** ADR-179 的 REJECT 从未被推翻 —— 它拒绝的是**把 dsh 作为依赖引入**；ADR-181/183/94 走的是**不引入依赖、隔离在子进程**的路径。两者可以同时成立，本报告的架构章节与两者都不冲突。

**真正需要修的是文档，不是决策**：`app/agents/harness/session.py:1` 的 docstring 写着 `dsh pattern steal`，容易被读成"我们没跑 dsh"。建议改为：*"pattern harvested into the Python harness; the TS runtime is separately deployed as a governed child process"*。

### A2. ⚠️ 两本 ADR 账本已经分叉 —— Archi 的镜像方向判断，主理人核实后**推翻**

Archi 建议"以 consolidated 文本为准、把根镜像标为 stale"。**核实后方向反了**，证据如下：

| | `memory/decisions.md`（根） | `_work/consol/memory/decisions.md` |
|---|---|---|
| 大小 / mtime | 67,036 B / **2026-09-19 17:47** | 495,534 B / 2026-09-19 10:07 |
| 最高 ADR | 192（**+ ADR-94**） | 194 |
| ADR-183 文本 | `LIVE-INERT` … **"shadow mode only（legacy executor still primary）"** | "full authority arm … `DSH_SHADOW_ENABLED=0`，29 个 agent 的 allowlist" |
| 与 2026-09-14 探针（`SHADOW=1`, `["jiya_makeover"]`） | **一致** | **矛盾** |
| 被代码读取 | **是** — `scripts/project_context.py:212` 注册为 `ArchitectureDecision` 来源（weight 50）；另见 `app/voice_agent/telecaller_brain.py:754,3569`、`app/tasks/kb_niche_refresh.py:7`、`tests/test_delivery_ledger_wiring.py:10` | 未发现代码引用 |

**判定：以根账本为准，`_work/consol/` 的副本是分叉的过期镜像。** 三条理由：① 只有根账本**被代码接线**（`project_context.py` 是 ADR 检索入口）；② 只有根账本**含 ADR-94**，而 ADR-94 恰是那条"从 live `/health` 更正"的记录；③ 根账本的 ADR-183 文本**与生产探针一致**，consolidated 版本与探针矛盾。

> **"编号更高 = 更新"在这里不成立。** 两本账本是不同谱系，各自持有对方没有的高号段（根：190–192 + ADR-94；consolidated：193–194），**互不为超集**。这本身是一个值得单独立项的记录治理问题。

**行动**：把 `_work/consol/memory/decisions.md` 的 DSH 段（ADR-179…183）标为 `STALE` 或删除该镜像；在根账本补一条 ADR 记录"账本已分叉，根为权威"。

### A3. Cordis 缺口登记册（只列映射到收益的缺口）

| 缺口 | dsh 怎么做 | 我们现状 | 补的收益 | 判定 |
|------|-----------|---------|---------|------|
| **能力 seam 的显式三段式**（Service Definition / Provider / Consumer） | `ctx.llm` / `ctx.tools` 等 seam 各含 definition + provider + consumer 三层，provider 可热替换 | `app/agents/harness/` 有 registry/enforce/sandbox/loop，但能力边界靠 import 约定隐式表达 | Reliability：换 provider 不必改 consumer | **ADAPT**（低优先） |
| **runtime invariant registry**（包自持活体自检 + 失败归因到 owning package） | `packages/runtime-diagnostics/invariants`，失败抛 `InvariantError` 并标注归属包 | 仅测试期：`app/platform/runtime_data_ratchet.py` | Compliance：运行时自检而非只在 CI | **ADAPT**（= 模式 #3） |
| **fail-closed durability checkpoint** | `session-checkpoint-policy`：副作用前落盘，失败即不执行 | `dsh_jobs.py` 有 run_store claim/heartbeat；外呼/邮件路径**无** | Reliability：崩溃不丢 CRM 归属 | **ADOPT**（= 模式 #1） |
| **unknown-outcome 语义** | 中断的工作 = unknown，**不自动重试** | `none` | Reliability：不重复拨打/重复发信 | **ADOPT**（= 模式 #2） |
| **插件全生命周期 `register`/`dispose`** | `ctx.plugin` 管挂载与卸载 | `skill_pack` 只有单向加载（见 R1） | — | **REJECT**（收益需要 54 个独立发包） |

### A4. 版本 pin 分析

我们 pin `RUNTIME_VERSION = "47f943859bef"`（`app/tasks/dsh_jobs.py:29`），并把同一字面量**硬编码在另外三处**：`dispatch.py:217`、`:238`、`:358`。upstream HEAD 已是 `ddefc45f`。`CODE-PRESENT`

**四个 pin 点的风险**：只改常量就 re-pin，会**静默**产生错误的版本记录 —— run_store 写一个版本、`/health` 报另一个、`runtime_status()` 报第三个。**re-pin 前先把三处字面量收敛到单一常量。**

**建议的 upgrade 触发条件（按事件，不按日历）：**
1. **安全事件** —— upstream 发布 CVE 修复或供应链事件（Cody 章节已列出 561 包 / 72 直接依赖 / native 重依赖的信任面）；
2. **我们依赖的行为变更** —— 具体是 JSON-RPC 协议面、`cordis.yml` composition 语义，或 session 格式 generation（upstream 已走 v0→v1→v2→v3，**且"拒读未来版本"**）；
3. **既有集成缺陷而修复在 upstream** —— 例如模式 #1/#2 若选择直接取用 upstream 实现而非自写。

**永不 re-pin 会怎样**：风险不是"变旧"，而是**安全补丁永远拿不到**，且我们与 upstream 的 session 格式差异会**单向增大**（格式只进不退、无向下迁移路径）。`CODE-PRESENT`

**前置条件**：re-pin 前必须先用 `dsh --profile web --dump-config` 确认默认姿态（见安全章节"待确认"项）—— 否则无法判断一次 pin 变更是否同时改变了沙箱/approval 默认值。

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

### 🔴 P0 补充行动项（**优先于上表**，由本次评估新增）

上表为初稿清单。以下是本次评估**新增**的三条 P0，应排在上表全部条目之前执行：

| # | 行动 | 负责角色 | 紧急度 | 预期完成 | 证据标签 |
|---|------|---------|--------|---------|---------|
| **N1** | **原子修复两平面 allowlist 分裂**：(a) `app/integrations/dsh.py:41` 改读 `DSH_AGENT_ALLOWLIST` + `:69-70` 反转为 fail-closed + 补 `*`=DENY；(b) `docker-compose.vps.yml` 的 `dsh-worker` env 新增 `DSH_AGENT_ALLOWLIST: ${DSH_AGENT_ALLOWLIST:-}`；(c) 翻转 `tests/test_dsh_integration.py::TestDSHAllowlistCheck::test_empty_allowlist_allows_all`。**三件必须同一批** —— 只做 (a) 会中断已 ARM 的 `jiya_makeover` lane。**验收**：`test_dsh_integration.py` 20/20 + `test_dsh_workforce_runtime.py` 28/28 仍全绿且断言方向相反 | 待指派 | **P0** | 1 日 | TEST-PROVEN |
| **N2** | **修 `/health` 发布错误 allowlist**（`dsh.py:54` 指向死变量 `DSH_ALLOWLIST_CSV`，与 `dispatch.py:356` 矛盾）；顺带把 `RUNTIME_VERSION` 的 4 处字面量收敛为单一常量 | 待指派 | **P0** | 半日 | CODE-PRESENT |
| **N3** | **ADR 账本对账**：`_work/consol/memory/decisions.md` 的 DSH 段标 `STALE`/删除；根账本补一条"账本已分叉、根为权威"；改 `session.py:1` docstring 为"pattern harvested + TS runtime separately deployed" | Docu / 业主 | **P0** | 半日 | CODE-PRESENT |

> **为什么 N1 排第一**：它是本次评估唯一一个**已知会让生产闸门失效、且修复窗口与部署顺序强耦合**的缺陷。其余条目是加固，N1 是止损。

---

## ⚠️ 待完善 / 已知局限

- **架构深度评估（Archi）已并入本报告** —— 见「🔴 P0 专章」（主理人核实 + Cody 裁定）与「🧾 记录与代码的对账（Archi）」。**其中 A2（账本分叉的镜像方向）主理人核实后推翻了 Archi 的原始判断**：报告采纳的是核实后的版本（根账本为准），不是 Archi 原稿。A1/A3/A4 为 Archi 原产出，主理人已将其非标准证据标签统一为本报告的标准标签集。
- **未实跑 dsh**：所有 dsh 侧结论均为 `CODE-PRESENT`（读代码/文档），无一为 `PRODUCTION-PROVEN`。
- **未触碰生产 VPS**：VPS 余量、`dsh` 队列是否有 worker、以及**容器内两个 allowlist 变量的实际取值** —— 全部 `UNKNOWN`。P0 专章的**行为结论已是 `TEST-PROVEN`**（六项受控实验，两次独立执行结果逐项一致）；**compose 层事实**（`DSH_ALLOWLIST_CSV` 不在 `docker-compose.vps.yml`、`dsh-worker` env 无任何 allowlist 变量）仍是 `CODE-PRESENT`，**转 `LIVE-VERIFIED` 只差一条命令**：`docker exec leadgen_app printenv DSH_ALLOWLIST_CSV DSH_AGENT_ALLOWLIST`（在 `dsh-worker` 容器上同样跑一次）。"已 ARM"的状态来自 `AGENTS.md:136` 的 2026-09-14 探针与 `memory/decisions.md` ADR-94，**非本次观测**。
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
| **Cody（安全审查师）** | 凭证 seam 评估、🔴 沙箱只写、🟠 默认 session-log 上传、供应链与依赖面、Windows 沙箱 partial；**两平面 allowlist 分裂的独立严重度裁定（🟠 HIGH，结论 Request Changes；blast radius 由 token 界定，故不升 Critical）** |
| **Archi（架构师）** | ADR-179/181/183/94 对账与 `session.py` docstring 修正建议（A1）、Cordis 缺口登记册（A3）、版本 pin 分析（A4）；其"consolidated 为权威"的镜像方向判断**经主理人核实后推翻**（A2） |
| **Rex（SRE）** | 资源成本、新增故障面、回滚只进不退、开发隔离条件、可观测性孤岛、prod NO-GO / dev conditional GO |
| **Tessa（测试专家）** | 证据完整性声明、6 项可迁移技术、R1–R5 缺陷、合规不变式设计、采用计划与"不值得测"清单 |
| **Docu（技术文档师）** | 报告骨架、register 列集与理由、证据标签约定、语言判定、可读性风险与缓解 |
| **主理人（Zhen）本人核实** | 事实核查表、既有 dsh 集成发现（`dsh_jobs.py` / `dsh_internal.py` / `harness/`）、ADR-180 状态、R1 上界更正 + R1b 新发现、R2 与零测试覆盖确认、两处记忆路径纠错；**P0 专章的全部 compose 证据**（`DSH_ALLOWLIST_CSV` 不在 `docker-compose.vps.yml`；`dsh-worker` env `:878-887` 无任何 allowlist 变量；`dsh_worker.py:24,32` 路由确认）、契约 3-vs-2 矛盾、`/health` 错报 allowlist、`tool_token` 死分支、`RUNTIME_VERSION` 四处字面量、账本分叉方向判定 |

---

## 🛠️ 修复已实施（2026-09-19 · 本地 · 未部署）

**N1 已在本地完成并验证 —— `READY-TO-DEPLOY`（未 commit、未部署）。**

| 变更 | 文件 | 内容 |
|------|------|------|
| **(a) 代码** | `app/integrations/dsh.py` | 改读单一权威变量 `DSH_AGENT_ALLOWLIST`（新增模块常量 `ALLOWLIST_ENV`）；空值反转为 **fail-closed**；新增 `*` → 空集（= DENY，与平面 1 一致）；`/health` 改为上报**enforcement 实际所读的同一个**变量（消除两套矛盾真相）；移除未使用的 `typing` 导入 |
| **(b) 部署清单** | `docker-compose.vps.yml:888` | `dsh-worker` 服务 env 新增 `DSH_AGENT_ALLOWLIST: ${DSH_AGENT_ALLOWLIST:-}`，附注释说明"缺失即全员被拒" |
| **(c) 测试** | `tests/test_dsh_integration.py` | 重写：全部断言改用权威变量；新增 `TestDSHAllowlistFailClosed`（5 个 pin，含 `test_legacy_var_name_is_ignored` 回归 pin，以及 `test_canonical_allowlist_var_matches_dispatch_plane` 单一来源 pin —— 后者直接断言 `dsh.ALLOWLIST_ENV == dispatch.DSH_ALLOWLIST_FLAG`） |

### 验证证据（`TEST-PROVEN`）

- `tests/test_dsh_integration.py` → **29 passed / 0 failed**
- `tests/test_dsh_workforce_runtime.py`（平面 1，确认无连带损伤）→ **28 passed / 0 failed**
- `ruff check` 两个改动文件 → **All checks passed**
- **guard-must-fail：PASS** —— 把新断言跑在**修复前**的实现上（逐字重建旧逻辑）：

| case | expected | OLD（修复前） | NEW（已实施） |
|------|----------|--------------|--------------|
| 空 allowlist | False | **True** ❌ | False ✅ |
| 未设 allowlist | False | **True** ❌ | False ✅ |
| `*` | False | **True** ❌ | False ✅ |
| 只设 legacy 变量 | False | **True** ❌ | False ✅ |
| **有界 allowlist + 未列出者** | False | **True** ❌ | False ✅ |
| 有界 allowlist + 已列出者 | True | True ✅ | True ✅ |

**旧逻辑 6 条只满足 1 条；新逻辑 6/6。守卫确实会失败 —— 它不是装饰品。**

> **⚠️ 比本报告原判断更严重的一点（修复过程中实证）**：注意表中倒数第二行「有界 allowlist + 未列出者」—— **旧代码在权威 allowlist 已正确配置为 `["jiya_makeover"]` 时，仍然对 `attacker` 返回 `True`。** 原因是旧代码读的是**另一个**变量，所以**权威 allowlist 被整个忽略**。这比"空 allowlist 放行一切"更严重：**即使运维把 allowlist 配对了，闸门依然形同虚设。** 这也解释了为什么这个缺陷能长期不被发现 —— 它不会在 allowlist 被设置时暴露任何异常。

**未做（遵守 owner 规则）**：**未 commit、未 push、未部署、未触碰 VPS。** 修复生效需 owner 批准后走 `scripts/deploy_vps.sh`。由于 (a)(b)(c) 是同一批变更，部署即原子生效，**不会出现"代码已改而 worker env 未改"的中断窗口**。

---

## 🔁 后续技术债修复（N2 / N3，2026-09-19，Loop Engineer 模式执行）

P0 修复（fail-closed allowlist gate）已落地并验证后，按 "DO NOT STOP AT THE AUDIT" 继续收口
剩余两项技术债。本段全部为 **LOCAL-ONLY / READY-TO-DEPLOY**，未 commit/push/deploy。

### N2 — RUNTIME_VERSION 单源收敛（修复前：4 处散落）

**问题**：harness 版本钉（`47f943859bef`，上游 SHA 前缀）在 4 处出现：
`app/tasks/dsh_jobs.py:29`（常量）+ `app/platform/workforce_runtime/dispatch.py:217/238/358`（3 处硬编码副本）。
任一处单独 bump 都会造成版本漂移，且 `dispatch.py` 的三处默认值与 dsh_jobs 的常量可能不一致。

**修复**：在 `app/integrations/dsh.py:41` 设唯一常量 `DSH_RUNTIME_VERSION`；`dsh_jobs.py`
改为 `from app.integrations.dsh import DSH_RUNTIME_VERSION as RUNTIME_VERSION`（保持原引用名，
零行为变更）；`dispatch.py` 顶部 `from app.integrations.dsh import DSH_RUNTIME_VERSION` 并替换
3 处字面量。**零循环依赖**（dsh.py 仅 `import os`，是 leaf 模块）。

**证据**：`grep` 确认 `app/` 内字面量仅剩 `dsh.py:41` 一处；import 冒烟测试断言
`dispatch.DSH_RUNTIME_VERSION == dsh.DSH_RUNTIME_VERSION == dsh_jobs.RUNTIME_VERSION == "47f943859bef"` 通过。
**证据标签：TEST-PROVEN。**

### 运行时闸门二次确认（加固 P0 论断）

`app/tasks/dsh_jobs.py:162 _run_jsonrpc` 在 **`leadgen_dsh_worker` 容器**内执行，且**在启动 child
进程前重新校验 allowlist**（L170-174：`if not dsh_integration.is_dsh_allowed(...) -> raise
RuntimeError("dsh_allowlist_denied")`）。即 P0 fail-closed gate 在 **enqueue（Plane 1）与 worker
运行时（Plane 2）两层都被强制执行**——此前"直接 enqueue 会跳过策略评估"的担忧已被证伪：
`_run_jsonrpc` 不调用 `_dsh_preflight`，但**直接调用 `is_dsh_allowed`**。
L172 `tool_token = None` 仅为惰性的 *WHAT* 子闸门（per-tool 细化），*WHO*（身份）闸门是活的、
fail-closed 的。该 dead branch 本轮回填为已知 GATED-INERT，未改动（改则行为风险，且无测试覆盖）。

### N3 — ADR ledger 去分叉（single-source-of-truth）

**问题**：两份 `decisions.md` 已漂移——`_work/consol/memory/decisions.md`（consolidated mirror）
**缺 ADR-94** 且其 **ADR-183 与 2026-09-14 prod probe 矛盾**（`DSH_SHADOW_ENABLED` 状态）。
`scripts/project_context.py` 将 `memory/decisions.md` 接线为 `ArchitectureDecision`（权重 50），
无代码引用 mirror。ADR 编号在分叉谱系间**不**具"越大越新"含义。

**修复**：
1. 根 ledger `memory/decisions.md` 顶部新增 **ADR-193**（single-source-of-truth）：
   `memory/decisions.md` 为唯一权威；mirror 为 STALE、非权威，其 DSH ADR 视为被根覆盖。
2. mirror 顶部加 **STALE MIRROR** 横幅，禁止作为 truth source 引用。
3. `app/agents/harness/session.py:3` docstring 对齐为「NOT the live TypeScript runtime;
   the TS runtime is deployed separately as a governed child process」（原已正确，仅补一句明确部署形态）。

**证据**：两份文件锚点插入成功（python 原子写 + assert 校验）。**证据标签：LOCAL-ONLY。**

### 本轮验证证据

| 检查 | 结果 |
|------|------|
| `ruff check app/integrations/dsh.py app/tasks/dsh_jobs.py app/platform/workforce_runtime/dispatch.py` | All checks passed! |
| `pytest tests/test_dsh_integration.py tests/test_dsh_workforce_runtime.py -q` | **57 passed (100%)** |
| import 冒烟测试（dispatch/dsh_jobs 经 importlib，规避 `dispatch` 命名遮蔽坑） | IMPORT OK |
| `grep "47f943859bef" app` | 仅 `dsh.py:41` 一处（单源达成） |

### 行动清单补充（按优先级）

| # | 行动 | 负责角色 | 紧急度 | 预期完成 |
|---|------|---------|--------|---------|
| N1 | owner 批准后 `scripts/deploy_vps.sh` 原子部署 P0+N2（compose env 含 `DSH_AGENT_ALLOWLIST`） | Boss | P0（owner-gated） | 批准后 |
| N2 | 已就地收敛；后续 harness 升级只 bump `dsh.py:41` 一处 | Cody | P3 | 已闭环 |
| N3 | 已就地去分叉；未来任何 fork 必须合回根并删 mirror | Archi | P3 | 已闭环 |

---

> 本报告由工程保障团队 AI 协作生成，关键决策请由人类工程负责人复核。
