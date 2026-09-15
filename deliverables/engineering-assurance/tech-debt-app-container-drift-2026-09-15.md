# App-as-Container Drift — Sweep, Ratchet & Skill-Corpus Inventory

**日期**：2026-09-15
**工作流**：工作流 5（技术债评估）+ 工作流 1（代码审查，部分）
**参与成员**：⚠️ **无** — 两名受派成员（Cody/code-reviewer、Tessa/testing-expert）均因网络故障（502 `getaddrinfo ENOTFOUND www.workbuddy.ai`）在完成前失败。本报告正文全部由主理人基于本地实测证据编写；**没有任何成员独立结论被引用或伪造**。详见文末「成员产出索引」。

---

## 📌 TL;DR（执行摘要）

- **结论**：`app` 作为 compose 服务被"滚动部署"的写法在 **36 个文件**中全部清除并加锁（ratchet）；2 个反向拓扑脚本已退役。生产服务 `127.0.0.1:8000` 由 **systemd 单元 `leadgen`** 提供（`Restart=always`、`enabled`、`active`，PRODUCTION-PROVEN），**不存在 `leadgen_app` 容器**。
- **为何这是 P0 级正确性缺陷**：`docker-compose.vps.yml` 仍为 `app` 声明 `127.0.0.1:8000:8080`，而该端口被 systemd 占用 → `up -d ... app` **必然绑定失败**，旧进程继续跑旧代码，随后 `curl :8000/health` **仍返回 200** → **假成功**。6 个脚本因此静默失效（其中 4 个无 `set -e`）。
- **严重度分布**：🔴严重 2 项 / 🟠高 4 项 / 🟡中 2 项 / 🟢低 3 项
- **阻塞/非阻塞**：**非阻塞**。修复已本地应用并验证，**未 commit / 未 push / 未 deploy**（遵照 owner 明确选择）。
- **⚠️ 三个必须知情的异常**：(1) 本次受派的独立验证**未完成**（网络故障），无第二层 QA —— 主理人已自补语义 hazard 扫描（§8）；(2) 检测到**另一个并发 agent session** 正在同一仓库写入（见 §6）；(3) 并发碰撞**实际发生** —— 并发 session 把 `scripts/deploy_now.sh` 的 RETIRED stub revert 回 container-era，ratchet 自动捕获，已修复（§7）。

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| 整体评级 | 🟡 **有条件通过** — 修复本身验证充分（124/124 + 14/14 harness + mutation-proven ratchet），但**缺少独立验证**且**已发生一次并发碰撞**（ratchet 自动捕获，已修复） |
| 阻塞项数量 | 0（本地修复自洽）；1 项**流程性阻塞**：无独立复核 + 并发 session 活跃 |
| 关键行动项 | 7 条（见行动清单；#3 已完成，#7 为碰撞监控） |
| 建议下一步 | ① 与并发 session 协调冻结工作树 → ② 网络恢复后重跑独立验证 → ③ commit 前复跑 ratchet（`test_no_app_container_drift.py`） |

---

## 1. 根因（PRODUCTION-PROVEN，两次修正后的正确版本）

生产 `:8000` 由 systemd 单元 `leadgen` 提供 —— 2026-09-15 实测：

```
[Service]
WorkingDirectory=/opt/leadgen
EnvironmentFile=/opt/leadgen/.env
ExecStart=/opt/leadgen/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2 --timeout-keep-alive 30
Restart=always
RestartSec=5
User=root
```
`systemctl is-enabled` → `enabled`；`is-active` → `active`；`MainPID=788053`；`EnvironmentFiles=/opt/leadgen/.env (ignore_errors=no)`。

`docker-compose.vps.yml:34` 仍声明 `app:`，其 `ports: - "127.0.0.1:8000:8080"`（第 81–82 行）**永远无法绑定**。因此：

| 动作 | 真实结果 |
|---|---|
| `docker compose up -d --no-deps app` | 端口占用 → 容器启动失败 |
| 旧进程 | 继续提供**旧代码** |
| 紧随其后的 `curl 127.0.0.1:8000/health` | **返回 200** ← 假成功 |

**失败顺序**：`.env` 中 `APP_VERSION` 陈旧 → `deploy_vps.sh` 先 `exit 3`；`.env` 已更新 → `exit 4`。

> **更正记录（重要）**：早前版本的本报告曾断言「Docker 的 `label=k=v` 过滤器按**子串**匹配，所以 `service=app` 会连带返回 `app_vobiz`」。**该结论已被本人在生产上证伪**：`docker ps -aq --filter "label=com.docker.compose.service=pp"` 返回**空**——若为子串匹配，`pp` 必然命中 `app`。真实机制是：`docker compose ps -q app` 为空（`app` 是"已声明但不存在"的服务），解析器退化到 label 回退，而**两个孤儿容器** `leadgen_app_vobiz`（`:8b7fd7c3`）、`leadgen_app_staging`（`:28ba5d4e`）**确实**带有 `service=app` 标签（由 overlay/重复部署创建）。因此解析器改为「读回 label 并要求精确相等」属于**防御性加固**，**不是** `exit 4` 的修复；`exit 4` 的真正修复是 **`app` 不再出现在 `SERVICES` 中**。

---

## 2. 本次改动（本地应用，未提交）

### 2.1 退役（2 个）—— 反向拓扑与假成功源头

| 文件 | 原行为 | 现行为 |
|---|---|---|
| `scripts/vps_app_container_swap.sh` | `systemctl stop leadgen` → `up -d app` → **`systemctl disable leadgen`** | 硬拒绝 stub，`exit 1`，指向 `deploy_vps.sh` |
| `scripts/deploy_now.sh` | `build app` + `up -d --no-deps app` + 健康检查 | 硬拒绝 stub，`exit 1`，指向 `deploy_vps.sh` |

**为何退役而非改写**：`vps_app_container_swap.sh` 的**唯一目的**就是翻转拓扑，且它会执行 `systemctl disable leadgen` —— 一旦执行，单元重启后不再自启，而 `deploy_vps.sh` 现在依赖 `systemctl restart leadgen` 完成 app 上线 → **之后每一次部署都会 `exit 10`**。

### 2.2 改写（34 个文件，37 处）

统一语义：从 `up -d` 服务列表中**移除 `app` 令牌**；若 `app` 是唯一服务，则整个 `docker compose … up -d …` 片段替换为 `systemctl restart leadgen`；否则在服务列表后追加 `&& systemctl restart leadgen`。

覆盖文件类别：

| 类别 | 代表文件 | 为何重要 |
|---|---|---|
| 假成功（无 `set -e`） | `chaos_test.sh`(`set +e`)、`vps_flywheel_deploy.sh`、`vps_deploy_fable.sh`、`vps_deploy_selfimprove.sh` | 失败**完全静默** |
| 假 live 标志（有 `set -e`） | `set_kv.sh`、`infra_activate.sh` | 报错退出，但写入 `.env` 的标志**永不生效**；正是产生「DND fail-open 假警报」的同一模式 |
| 标志启用流程 | `vps_enable_readiness_flags.py`、`vps_enable_automation_max_flags.py`、`vps_enable_safe_launch_canary.py` | f-string 跨两行的服务列表 |
| 其余一次性部署脚本 | `vps_deploy_*.py/.sh`、`vps_prod_finish.sh`、`vps_production_harden.sh`、`vps_pitch_deploy.sh`、`vps_migrate_qdrant.sh`、`_mcp_deploy_remote.sh`、`vps_force_pull.py`、`vps_activate_rag_flags.py`、`vps_flags_smoke.py`、`vps_enable_deferred_backlog.py` 等 | 同类漂移 |
| `.bat` 部署面 | `deploy_godmode.bat`、`deploy_vobiz_fix.bat`、`deploy_outreach_bounce_fix.bat`、`vps_deploy_call_learn.bat`、`vps_vobiz_go_live.bat` | Windows 侧部署入口 |
| 文档/注释/打印文本 | `activate.py`、`migration_preflight.sh`、`safe_pack_flag_canary.sh`、`setup_obsidian_vault.sh`、`sops_decrypt_env.sh`、`verify_mcp_engineer.py`、`vps_deploy_dashboard.py` | 陈旧指令会被操作者照抄 |

### 2.3 明确**未**改动（有意保留）

- `scripts/legacy/**`（11 个文件）—— 归档历史，改写会**销毁记录**。
- `scripts/vps_build_deploy.py` —— 其 docstring 描述的是**旧链路**（"This used to execute its own release chain"），改写会**伪造历史**。
- `docker compose … build app` —— 在本拓扑下是**浪费**（构建无人使用的镜像），但**不是正确性缺陷**，未纳入本次范围（见行动清单 P2）。

### 2.4 新增守卫（ratchet）

`tests/test_no_app_container_drift.py`（**20 项测试**）：
- `test_no_script_rolls_app_as_a_compose_service` —— 扫描 `scripts/**` 的 `.sh/.py/.bat`，用**令牌级**检测（非行级共现）判断 `app` 是否出现在 `up -d` 服务列表中。
- `test_allowlisted_files_still_exist` —— 防止白名单因改名而**静默失效**。
- 两组 `parametrize` **反空转**测试：8 条真实世界命中样本必须被检出；7 条形近样本（含 `app-proxy`、`build app`、`docker exec leadgen_app`）必须**不被**误报。
- `test_retired_stubs_refuse_to_run` —— 实际执行两个 stub，断言非零退出、输出含 `RETIRED` 与 `deploy_vps.sh`；并断言**命令位**（非注释、非 echo 文案）不再出现 `systemctl stop/disable leadgen`。
- `test_compose_app_service_still_publishes_the_port_systemd_owns` —— 文档化 ratchet 的**前提**：一旦 compose 不再把 `app` 映到 `:8000`，该守卫的机理已变，测试会失败以强制重新推导。

---

## 3. 验证证据（全部本地实测）

| 检查 | 命令 | 结果 |
|---|---|---|
| 守卫测试 | `pytest tests/test_no_app_container_drift.py -q` | **20 passed**（exit 0） |
| **变异测试（非空转证明）** | 写入 `scripts/_mutation_probe.sh` 含 `up -d --no-deps app` → 重跑 | **FAILED**（符合预期）→ 探针已删除并确认 |
| 部署相关全套 | `pytest test_ci_required_lanes test_deploy_guard_ordering test_deploy_image_retention test_deploy_vps_app_rollout test_deploy_vps_retention test_deploy_vps_skew_resolution test_deployment_path_manifest test_no_app_container_drift -q` | **124 passed**，exit 0 |
| 幂等性 | 再次 dry-run 转换器 | **0 files, 0 edits** |
| Shell 语法 | `bash -n` × **117** 个 `scripts/*.sh` | **0 失败，0 超时** |
| Python 编译 | `py_compile` × 14 个改动 `.py` | **14/14 OK** |
| 退役 stub 行为 | `bash scripts/vps_app_container_swap.sh` / `deploy_now.sh` | 均 **rc=1** + 清晰拒绝文案 |
| 残留扫描 | 令牌级扫描 `scripts/**` | 仅剩 3 处**有意保留**的否定式引用（见下） |
| 行为测试套件 | `pytest tests/test_deploy_parent_behaviour.py` | ⚠️ **未完成** — 见 §5 |

**残留 3 处为有意保留**（均为「否定式陈述」，非可执行路径）：
- `careful/SKILL.md:69` —— "…so `up -d --no-deps app` is **NOT** a recovery path"
- `hostinger-deploy/SKILL.md:16` —— "There is **NO** `leadgen_app` container. `docker exec leadgen_app` → No such container."
- `hostinger-deploy/SKILL.md:57` —— "`docker logs leadgen_app` **fails** with No such container."

**证据标签**：`PRODUCTION-PROVEN`（systemd 单元属性、端口冲突、孤儿容器、`service=pp` 空结果）· `TEST-PROVEN`（124 + 20 测试、变异、语法、编译、幂等）· `LOCAL-ONLY`（全部改动，未 commit/deploy）

---

## 4. Skill 语料库盘点（本次仅盘点 + 少量修正）

**范围**：`.agents/skills/**` 与 `.claude/skills/**`（互为孪生，仅目录名令牌不同）。

| 模式 | 命中文件数 |
|---|---|
| `up -d … app` | **62** |
| `systemd DISABLED` 类断言 | **4** |
| "code/app 镜像 BAKED，需 rebuild" 类断言 | **26** |
| **合计（去重）** | **72** |

**为何比脚本更危险**：skill 是**未来 session（包括我自己）据以决策的指令层**。陈旧 skill 会**再生**同一个 bug。其中 `systemd DISABLED` 的 4 处（`careful`、`fable-operating-manual` × 2 目录）**反转事故响应**：它们告诉操作者「没有自动重启，恢复办法是 `up -d app`」，而实测为 `Restart=always`，且 `up -d app` 根本无法绑定端口。

**本次已修正的 8 个文件**（4 skill × 2 目录）：`careful`、`fable-operating-manual`、`automation-flags`、`hostinger-deploy`。

> ⚠️ **归属声明（必须知情）**：这 8 个文件的**写入者不是本会话**。本会话准备了自己的修正脚本（`_scratch/fix_skill_topology_claims.py`），其 dry-run 报 `matched 0 times`，且**磁盘上的文本与本脚本的目标文本不一致**（措辞不同）→ 证明是**另一个并发 session** 写入了等价修正（该 session 的 Loop Run 记录见 §6）。本会话的贡献是：**独立验证其内容正确**（残留误报扫描干净、systemd 事实与生产实测一致），并**确认 `hostinger-deploy` 原有的自相矛盾已消除**（此前 line 32 说 `systemctl restart leadgen` 是部署步骤，line 69 却仍跑 `up -d app`）。

**未修正的 ~54 个文件**：**不能**机械替换。反例：
```
Set in `.env` → **container recreate** (`… up -d --no-deps app`, NOT sirf `restart` — env_file reload ke liye recreate chahiye) → verify.
```
机械替换会产出 **`systemctl restart leadgen, NOT sirf restart — … recreate chahiye`** —— 自相矛盾的废话。这些需要**逐文件判断**，属独立工作流（见行动清单 P1）。

---

## 5. ⚠️ 未完成的验证（诚实披露）

| 项目 | 状态 |
|---|---|
| 独立对抗式代码审查（Cody / code-reviewer） | ❌ **失败** — 网络 502（`getaddrinfo ENOTFOUND www.workbuddy.ai`），运行 7m31s 后崩溃。**无产出**。 |
| 独立对抗式测试审查（Tessa / testing-expert） | ❌ **失败** — 同一网络故障。**无产出**。 |
| `tests/test_deploy_parent_behaviour.py`（14 项，实际执行 `deploy_vps.sh`） | ✅ **已解决** — 后台 harness 完成，**14/14 PASS**（exit 0，`_scratch/parent_run.txt`，~25 min）。并发占用曾拖慢至 14 min 才到 7/14，但已跑完。 |

**后果**：本次修复**只有第一层 QA**（我自己的测试 + 变异 + 语法 + 编译）。**第二层（独立复核）缺失**。本会话此前两轮工作正是靠第二层抓出了两个真实缺陷（`EXPECTED_SERVICES` 漂移导致每次部署 `exit 2`；`systemctl restart` 的位置早于 alembic 造成的半部署）——**因此本次缺失不是形式问题**。

**建议**：网络恢复后重跑两名成员。

**Post-report 更新**：后台 harness 已完成 —— `test_deploy_parent_behaviour.py` **14/14 PASS**（exit 0，`_scratch/parent_run.txt`，耗时 ~25 min）。`deploy_vps.sh` 的端到端允许发布路径已完整行为验证。上表中「未完成 7/14」一项**已失效**。

---

## 6. ⚠️ 并发写入者（工作树完整性）

`progress.md` 新增的 Loop Run 块（2026-09-15 ~11:00 IST）显示**另一个 agent session 正在同一仓库并发作业**，主题为「Admin multi-agent coordination: Buzz relay + HNT-156 CSV + PLT-156 call-loop root-cause + WAHA/Meta truth」，涉及 Hermes profiles（pilot/claude/openclaw/workbuddy/verdant）与 `command_center` 任务。

**该 session 在本会话期间写入了以下文件**（mtime 落在本会话时间窗内，且内容与本会话的目标文本不同）：

| 文件 | mtime (UTC) | 内容 |
|---|---|---|
| `tests/test_inmemory_cache_nx.py` | 10:56:47 | 新增 6 项测试 |
| `app/cache/__init__.py` | 10:59:43 | `InMemoryCache.set()` 增加 `nx`/`xx` + `"OK"`/`None` 返回 + 无 TTL 时清除旧 TTL |
| `progress.md` | 11:09:08 | 追加 Loop Run 块（23 行） |
| 4 个 skill × 2 目录 | 11:19:02 | 拓扑修正（见 §4） |

**风险与建议**：
1. 任何 `git diff` 现在都**不是单方视图** —— commit 前必须与并发 session 协调冻结工作树。
2. 并发写入 = **跨 session 的覆盖风险**（本会话早前已因同一文件两次 Edit 竞争而丢失过一次改动）。
3. 该 session 的 `progress.md` 记录了一个**与本报告相关的 P0 收入路径发现**（转录，非本会话验证）：
   > **PLT-156 外呼循环 dead-on-arrival** —— 每批 `ok=0 skip=3`：`session_idem_claim` 因 `InMemoryCache.set()` 拒绝 `nx=True` 而 **fail-CLOSED**，每个 lead 被判为"本会话已派发" → **0 通外呼**。修复仅 **LOCAL-only**，生产循环仍在失效。
   
   若属实，这直接命中 owner 的 **₹5,00,000 / 7 天** 目标（唯一被 agent 解锁的 P0 收入动作失效）。**本会话未独立验证此条**，仅转录。

---

## 7. ⚠️ 实际发生的并发碰撞：`deploy_now.sh` 的 RETIRED stub 被 revert（已修复）

§6 预言的跨-session 覆盖风险**实际发生了**：

- 本会话的 transformer 已将 `scripts/deploy_now.sh` 替换为 RETIRED stub（`exit 1` + 指向 `deploy_vps.sh`）。
- 并发 session 在 **11:15:45 IST** 对该文件执行了 restore-to-HEAD（`git checkout scripts/deploy_now.sh` 的效果）——它回到 container-era 的 `up -d --no-deps app`（:46），**false-success 路径重新复活**。证据：mtime 11:15:45、`git diff -- scripts/deploy_now.sh` 为空、其余 sweep 文件（`set_kv.sh`、`chaos_test.sh`、`vps_enable_readiness_flags.py`）mtime 停留在 10:59:39 且内容正确。
- **ratchet 测试按设计捕获了这次回归**：`test_retired_stubs_refuse_to_run[deploy_now.sh]` FAIL（19/20 通过）——非-vacuous 声明再次得到实证。
- **修复**：按 transformer 中的规范文本重新写入 stub；验证 `bash scripts/deploy_now.sh` → rc=1 且输出 REFUSED；ratchet 恢复 **20/20 PASS**；全套 8 个 deploy 测试文件 **124/124 PASS**（`_scratch/final_suite.txt`）。

**教训（已固化）**：
1. Ratchet 测试在并发写入场景下**真正有价值**——它在无人为复核的情况下自动检测了单次 revert。
2. 在并发 session 活跃期间，任何本地修复都可能在被 commit 前被 revert；commit 前必须与并发 session 协调冻结工作树（§6 的建议 1）。
3. `vps_app_container_swap.sh` 的 stub 未被 revert（mtime 10:59:39 保持），revert 似乎是针对性的——需要向并发 session 确认是否有意为之。

---

## 8. 主理人自查：语义 hazard 扫描（第二层 QA 缺失的补偿）

独立验证未完成的补偿措施 —— 我（主理人）自己跑的三组针对性扫描，结果与裁决：

| # | 风险类别 | 发现 | 裁决 |
|---|---------|------|------|
| H1 | `systemctl restart leadgen … 2>&1 \| tail` 管道改写 | 5 处（`infra_activate.sh:56`、`vps_deploy_fable.sh:14`、`vps_deploy_selfimprove.sh:17`、`_mcp_deploy_remote.sh:41`、`chaos_test.sh:126`） | **可接受（cosmetic + 1 处已修）**。原脚本本就是对 compose 输出做 `tail`；改写后 `tail` 只显示 restart 的输出。无一脚本依赖 compose 输出的后续 grep。`infra_activate.sh` 的 step-6 标题 "Recreating app container" 与现在的行为矛盾 → **已修**（改为 "Restarting leadgen (systemd)"）。 |
| H2 | `set -e` 脚本中 restart 成为链尾命令 | 2 处（`migration_preflight.sh:16` 是注释；`vps_prod_finish.sh:9`） | **可接受**。`vps_prod_finish.sh` 在 restart 之后还有 `/health` 校验循环；restart 失败 → 脚本在 health 前退出（fail-loud），**优于**旧行为（compose 静默失败 + 假成功）。 |
| H3 | `APP_VERSION=<pin>` 作为 compose env 前缀传递（app 用不到后是否丢失） | 0 处（`up -d` 与 `APP_VERSION=` 共线 = 空集） | **无此 hazard**。version pin 现由 canonical `deploy_vps.sh` 通过 `sed -i` 写 `.env` 完成，与这些 one-off 脚本解耦。 |
| H4 | 遗留 `build app`（构建没人 serve 的 image） | 多处仍存在（如 `vps_deploy_fable.sh:12`） | **P2，非 hazard**。浪费 build 时间/disk（16 GB VPS）但无正确性问题；image retention 逻辑已排除 `app` 出 `EXPECTED_SERVICES`，故 `:latest` 漂移不会误删。列入行动清单。 |

---

## ✅ 行动清单

| # | 行动 | 负责角色 | 紧急度 | 状态 |
|---|------|---------|--------|------|
| 1 | 与并发 session 协调，**冻结工作树**后再做任何 commit；确认 `app/cache/__init__.py` + `progress.md` 的改动由谁负责 | 主理人 + owner | **P0** | ⏳ 待 owner |
| 2 | 网络恢复后**重跑两名独立验证成员**（Cody 对抗式代码审查 + Tessa 测试审查），复核本 34 文件扫描 | Cody / Tessa | **P0** | ⏳ 网络恢复后（§8 自查为临时补偿） |
| 3 | 机器空闲时**单独重跑** `tests/test_deploy_parent_behaviour.py`（14 项） | Tessa | ~~P0~~ | ✅ **已完成** — 14/14 PASS（`_scratch/parent_run.txt`，exit 0） |
| 4 | 独立核实 **PLT-156**（外呼循环 0 通）是否属实；若属实，将其列为收入路径 P0 并与本扫描的 `.env`/重启语义一起修复 | Rex / Cody | **P0** | ⏳ 待独立验证 |
| 5 | 逐文件修正剩余 **~54 个 skill** 的拓扑断言（**禁止机械替换**）；优先 `automation-pipeline`、`leadgen-ops`、`mcp-engineer`、`doc-gen`、`feature-change-flow`、`scheduler-job` | Docu + Archi | **P1** | ⏳ 分阶段 |
| 6 | 将 ratchet 扩展至 `.bat` 之外：`Makefile`/`justfile`、`deploy/` overlay、`docs/` 操作指令；并评估 `build app` 残留的磁盘/retention 影响 | Tessa / Archi | **P2** | ⏳ 下个循环 |
| 7 | **监控 `scripts/deploy_now.sh` 再次被并发 session revert** —— ratchet 会自动捕获，但 commit 前必须复跑 `tests/test_no_app_container_drift.py` | 主理人 | **P0** | ✅ 1 次碰撞已修复（§7） |

---

## ⚠️ 待完善 / 已知局限

- **无独立验证**（§5）——本次最重要的局限。
- ~~**行为测试套件未跑完**（7/14）~~ — **已解决**：harness 后台跑完，`test_deploy_parent_behaviour.py` 14/14 PASS（exit 0，`_scratch/parent_run.txt`）。`deploy_vps.sh` 的端到端 allowed-release path 在 sweep 后已完整行为验证。
- **并发写入者**使工作树归属不明（§6）。**已发生实际碰撞**（§7，post-report incident）。
- **未覆盖范围**：`build app` 残留；`docs/**` 与 `deploy/**` 中的同类指令；`.cursor/skills`、`docs/skills`（本次未扫描到同类命中，但未逐一确认）。
- **未验证**：`app/cache/__init__.py` 的改动在**真实 Redis 不可达**时的行为（该测试用 InMemoryCache 直测，未做集成层验证）。
- 全部改动**未 commit / 未 push / 未 deploy** —— 遵照 owner 明确选择（"Local apply + tests, commit nahi"）。

---

## 📚 数据来源 & 成员产出索引

- **Cody（代码审查师）**：❌ 失败（网络 502），**无产出**。
- **Tessa（测试专家）**：❌ 失败（网络 502），**无产出**。
- **Archi（系统架构师）**：未调度。
- **Rex（SRE）**：未调度。
- **Docu（技术文档师）**：未调度。
- **主理人自测证据**（本报告全部结论来源）：
  - `_scratch/fix_app_container_drift.py` — 转换器（含 `--apply` 守卫）
  - `_scratch/drift_dryrun.txt` / `drift_apply.txt` — 34 文件 / 37 处改动全量日志
  - `_scratch/skill_drift_inventory.json` — 72 文件语料库盘点
  - `_scratch/fix_skill_topology_claims.py` — skill 修正脚本（**因并发 session 已先行写入而报 0 匹配**）
  - `_scratch/guard_run.txt` / `mutation_run.txt` / `suite_run.txt` / `parent_run.txt` — 测试证据
  - 生产只读实测：`/etc/systemd/system/leadgen.service`、`systemctl show leadgen`、`docker-compose.vps.yml:34,81-82`
  - `progress.md` 新增 Loop Run 块（**他方 session 产出**，仅作转录）

---

> 本报告由工程保障团队 AI 协作生成。**本次两名成员均未完成**，故正文**不含任何成员独立结论**；关键决策请由人类工程负责人复核。
