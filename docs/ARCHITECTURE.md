# AI 测试 SaaS 平台架构（ai-tp v0.8）

平台按七层落地，业务侧以 **需求 Agent / UI Agent / 接口 Agent / 性能 Agent / 安全 Agent** 作为生成与执行门面；HTTP 路由只做校验与编排，不直接调用引擎。

## 七层结构

| 层级 | 职责 | 当前实现 |
|------|------|----------|
| 接入层 | API、前端页面、CI | FastAPI `/api`、Vue3 智能流水、`POST /integrations/ci/{id}/webhook` |
| 业务服务层 | 用例 / 任务 / 智能回归 / AI 生成 / 失败分析 | `backend/services/` + 五个 Agent（`backend/services/agents/`） |
| AI 网关层 | LLM 统一入口、调用统计、失败计数 | `backend/services/ai/gateway.py`（`complete` → `llm_client`；不缓存生成结果） |
| 调度层 | 任务队列、分布式压测、资源分配 | `job_queue` / `ai_job_queue` / `k6_scheduler`（`JOB_QUEUE_BACKEND`） |
| 执行引擎层 | Playwright GUI Agent、API DSL、k6、安全扫描、容器隔离 | `backend/services/engines/*`；Worker 镜像隔离执行 |
| 存储层 | 库表 + 截图 / 视频 / 日志 | MySQL/SQLite + `data/ui-agent/` 等对象目录 |
| 监控指标层 | 覆盖率、误报率、HTTP/Run 指标 | `GET /ai/agents` 的 `quality`；Prometheus `GET /metrics` |

## 五个专业 Agent

流水线顺序：**需求 Agent → UI Agent → 接口 Agent → 性能 Agent → 安全 Agent**。

| Agent | `key` | 生成 | 执行引擎 | 接入 API |
|------|-------|------|----------|----------|
| 需求 Agent | `requirement` | LLM → 需求评审 / 功能用例 | 评审项转用例 | `POST .../ai/requirement-review`、`.../functional-cases`、`.../convert-to-cases` |
| UI Agent | `ui` | 功能用例 → Playwright DSL | Playwright GUI Agent | `POST .../ui-automation/generate-from-case`、`execute-agent` |
| 接口 Agent | `interface` | LLM → YAML DSL 产物 | HTTP DSL runner | `POST .../ai/api-automation`、`.../artifacts/{id}/execute` |
| 性能 Agent | `perf` | LLM → k6 压测方案 | k6 local / distributed | `POST .../ai/perf-plan`、`.../dispatch-perf` |
| 安全 Agent | `security` | LLM → Payload / 扫描策略 | builtin / nuclei / zap | `POST .../ai/security-scan`、`.../dispatch-security` |

目录：`GET /ai/agents`（含网关统计 `gateway` 与覆盖/误报 `quality`）。工具缺失时执行结果为 `skipped` 并带 `detail.reason`，不硬崩溃。

## 五大 AI 业务模块（Prompt / 产物）

需求分析与功能用例由 **需求 Agent** 封装；后四个模块由对应 Agent 封装 `run_ai_module`。

| 模块 | `module_type` | API |
|------|---------------|-----|
| 需求预评审 | `requirement_review` | `POST /projects/{id}/ai/requirement-review` |
| 功能用例 | `functional_cases` | `POST /projects/{id}/ai/functional-cases` |
| 接口自动化 | `api_automation` | `POST /projects/{id}/ai/api-automation` |
| 性能方案 | `perf_plan` | `POST /projects/{id}/ai/perf-plan` |
| 安全策略 | `security_scan` | `POST /projects/{id}/ai/security-scan` |

Prompt 维护：`GET/POST/PATCH /ai/prompt-templates`，启动时种子 5 套内置模板。

## 分层补充

| 层级 | 当前实现 | 规划演进 |
|------|----------|----------|
| 前端 | Vue3 + Arco Design + Vite；智能流水 01–05 | 监控大盘、Agent 质量看板 |
| 后端 API | FastAPI：项目/用例/运行/报告/RBAC/AI；根路径健康 JSON | 版本、任务编排 API |
| **AI 网关** | `gateway.complete`：模型路由、Token 日志仍在 scheduler | 限流、多租户计费 |
| 测试引擎 | Playwright / API DSL / k6 / 安全扫描器 | 更细的容器配额 |
| 存储 | SQLite / MySQL + Alembic；Redis（队列/缓存） | 生产集群 |
| 任务队列 | `execution_jobs` + 多后端 Worker（db/redis/rq/celery） | 多租户配额、死信队列 |
| 可观测性 | Prometheus `/metrics`、请求 Trace 头、可选 OTLP；Agent `quality` | 统一 APM 大盘 |

## 模型路由

- **高精度**（需求评审、压测方案）：`AI_HIGH_PRECISION_MODEL` → 失败降级 `AI_FALLBACK_MODEL`
- **大批量**（用例、安全 Payload）：优先 `AI_LOCAL_*`，否则 `AI_BULK_MODEL`
- 无 API Key 时自动 **stub** 结构化 JSON，便于本地联调

## 权限

- `ai.read` / `ai.execute`
- `prompt.read` / `prompt.write`

## 上下文缓存

同项目连续生成时，`REDIS_URL` 可用则 Redis 缓存需求上下文；否则进程内内存缓存（`AI_CONTEXT_TTL_SEC`）。

---

## 执行任务队列（execution_jobs）

Run 启动后不再使用 FastAPI `BackgroundTasks`，而是写入持久化表 `execution_jobs`，由独立 Worker 认领执行（`backend/services/job_queue.py` → `orchestrator.execute_run`）。

### 生命周期

```text
pending → running → completed | failed | cancelled
```

- 认领：DB 模式原子 `pending→running`（防多 Worker 重复执行）
- 取消：`cancel_requested` 由 API 置位，执行中轮询 `is_run_cancel_requested`
- 重试：失败且 `attempt_count < max_attempts` 时回 `pending` 并重新入队
- 报告：Run/Item 状态与 stdout/stderr 持久化；失败触发告警（见下文）

### 队列后端（`JOB_QUEUE_BACKEND`）

| 值 | 入队 | Worker 启动方式 | 说明 |
|----|------|-----------------|------|
| `db`（默认） | 仅写 DB | `python -m backend.worker` 或 API 内嵌（`JOB_WORKER_IN_API=true`） | 轮询 + DB 认领，无 Redis 依赖 |
| `redis` | DB + `LPUSH` 队列 | 同上，`BRPOP` 后 DB 认领 | 轻量通知，执行语义仍以 DB 为准 |
| `rq` | DB + RQ `enqueue` | `python -m backend.worker`（内置 RQ Worker） | 需 `REDIS_URL`，`pip install -e ".[worker]"` |
| `celery` | DB + `delay` | `celery -A backend.celery_app worker -l info -Q ai_tp_execution` | 需 `REDIS_URL` 作 broker/backend |

任务入口（RQ/Celery 共用）：`backend/services/job_tasks.process_execution_job(job_id)` → `process_job(..., auto_claim=True)`。

生产建议：

```bash
# API：关闭内嵌 Worker
JOB_WORKER_IN_API=false uvicorn backend.main:app --port 8001

# Worker（按 JOB_QUEUE_BACKEND 选择其一）
JOB_WORKER_ENABLED=true python -m backend.worker

# RQ
JOB_QUEUE_BACKEND=rq REDIS_URL=redis://127.0.0.1:6379/0 python -m backend.worker

# Celery
JOB_QUEUE_BACKEND=celery celery -A backend.celery_app worker -l info -Q ai_tp_execution
```

`rq` / `celery` 模式下 API **不会**启动内嵌 DB 轮询线程，避免与专用 Worker 重复消费。

相关 API：`POST /runs/{id}/start`（入队）、`POST .../cancel`、`POST .../retry`；`RunOut.execution_job` 暴露任务状态。

---

## 数据库迁移与启动模式（Alembic / Bootstrap）

| `SCHEMA_BOOTSTRAP_MODE` | 行为 |
|-------------------------|------|
| `alembic` | 校验核心表存在 → 仅 seed（用户/Prompt/k6 默认节点）；**不** `create_all`、**不** ALTER 补丁 |
| `bootstrap` / `legacy` | `create_all` + `_ensure_legacy_column_patches()`（旧 SQLite 增量列）→ seed |

**新环境推荐：**

```bash
alembic upgrade head
SCHEMA_BOOTSTRAP_MODE=alembic
uvicorn backend.main:app --port 8001
```

迁移链：`20250603_0001` → `0002_schema_v068`（含 `execution_jobs` 等）→ `20250604_0003`（运维说明 revision）。旧实例可继续 `SCHEMA_BOOTSTRAP_MODE=bootstrap` 直至完成 Alembic 对齐。

实现：`backend/db/bootstrap.py`（启动时由 `main.py` / `worker.py` 调用）。

---

## 可观测性

### Prometheus

- 端点：`GET /metrics`（无需鉴权；`METRICS_ENABLED=false` 可关 HTTP 指标中间件，端点仍可用）
- 指标示例：
  - `ai_tp_http_requests_total{method,path_template,status}`
  - `ai_tp_http_request_duration_seconds`
  - `ai_tp_execution_jobs_total{status,backend}`
- 依赖：`pip install -e ".[observability]"` 或 `prometheus-client`

### 请求链路

- 中间件：`RequestTracingMiddleware`（`backend/core/tracing.py`）
- 入站可传 `X-Request-ID` / `X-Trace-ID`；响应回写同名头
- 可选 OpenTelemetry：配置 `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_SERVICE_NAME`，启动时 `FastAPIInstrumentor` 自动埋点

### 与 Run 的关系

任务处理结束会递增 `ai_tp_execution_jobs_total`（按最终 `status` 与 `JOB_QUEUE_BACKEND` 标签）。HTTP 路径模板当前为实际 path（非 OpenAPI 路由模板），抓取时注意高基数。

---

## P2 — 平台化 / 商业化

| 能力 | 状态 | 实现 |
|------|------|------|
| 多租户 | 已落地 | `organizations`；`projects.organization_id`；用户 `organization_id=null` 为平台管理员 |
| AI 配额 / 计费基础 | 已落地 | `monthly_ai_token_quota` 按月汇总 `ai_call_logs` 并拦截超额；`GET /organizations/{id}/quota` |
| 项目级 BYOK | 已落地 | `project_ai_credentials`（Fernet 加密）；`PUT/GET /projects/{id}/ai-credentials` |
| 审计合规 | 已落地 | 审计字段扩展；`GET /logs/export`；`POST /logs/retention/purge` |
| SSO/OIDC | 基础 | `GET /auth/oidc/login` + callback（需 `OIDC_ENABLED` 与 IdP 配置） |

对外 SaaS 时建议优先完成：租户隔离 → 配额 → BYOK → 审计导出 → OIDC。迁移：`alembic upgrade head`（`20250606_0005`）。默认租户：`seed_default_organization()`。

**租户隔离（PR-1）**：所有 `/projects/{id}/*` 项目资源路由与 `/runs/{id}/*` 经 `get_tenant_project` / `get_tenant_run`（`backend/api/deps.py`）校验；`/runs/recent` 对非平台用户按 `organization_id` 过滤。例外：`POST /integrations/ci/{id}/webhook`（`X-CI-Token`）。

**Dashboard / Metrics（PR-2）**

| 端点 | 行为 |
|------|------|
| `GET /dashboard/summary`、`/dashboard/run-trends` | 租户用户仅本 `organization_id`；平台管理员可选 `?organization_id=` 或全局（不传） |
| `GET /metrics` | `METRICS_AUTH_ENABLED=true` 时需 `METRICS_BEARER_TOKEN`（`Authorization: Bearer` 或 `X-Metrics-Token`），或未配置 token 时 JWT + `system.read` |

**OIDC state（PR-3）**：`store_oidc_state` / `consume_oidc_state`（`backend/services/oidc_state_store.py`）。配置 `REDIS_URL` 时用 Redis（`SETEX`，TTL `OIDC_STATE_TTL_SEC`）；否则进程内内存（单实例）。多副本 API 必须配 Redis。

**前端项目壳（PR-3）**：`ProjectLayout` 通过 `provideProjectScope` 统一加载项目；子路由页（`ProjectCasesSection` / `ProjectAiSection` / `ProjectRunsSection` / `ProjectReportsSection` 等）`inject` 复用，避免重复请求。原「概览」中的报告邮件收件人迁至 **集成** Tab（`ProjectRecipientsSection`），对应 `GET/POST/DELETE /projects/{id}/recipients`。

**P2 深化**

| 能力 | API |
|------|-----|
| 成员 + 角色绑定 | `GET/POST /organizations/{id}/members`；`POST .../members/by-role-names`；`DELETE .../members/{user_id}`；角色 `org_admin` / `member` / `viewer` |
| AI 租户校验 | 所有 `/projects/{id}/ai/*` 经 `_get_project` → `get_project_for_user` |
| OIDC 挂租户 | Claim `OIDC_ORGANIZATION_CLAIM`（默认 `org_slug`）；`OIDC_DEFAULT_MEMBER_ROLES` |
| 账单 PDF | `POST .../billing/invoices/generate`；`GET .../invoices/{id}/pdf` |
| Stripe | `POST .../billing/checkout`；`POST /billing/stripe/webhook`（`pip install -e ".[billing]"`） |

**P2 生态与商业化**（迁移 `20250607_0006`）

| 能力 | API / 行为 |
|------|------------|
| AI 工作台 | `GET/POST /projects/{id}/workbench/sessions`；`POST .../chat`（可选 RAG）；`POST .../apply` 写入用例/评审等 |
| CI Webhook | `GET/PUT /projects/{id}/integrations/ci`；`POST /integrations/ci/{id}/webhook`（`X-CI-Token`）；Run 完成后可选 GitHub PR 评论 |
| UI 自动化闭环 | `functional_cases.ui_script`；`POST .../ui-automation/preview|execute-step`；functional Run 有脚本时走 Playwright（未安装则 `skipped`） |
| 权限 | `workbench.read/execute`；`integration.ci.read/manage` |

`CI_WEBHOOK_PUBLIC_BASE_URL`：对外展示的 Webhook 基址（默认同 API）。

---

## Run 失败告警

触发：执行 Job 耗尽重试或 Run 失败（`notify_run_failure`）。

| 通道 | 配置 | 实现 |
|------|------|------|
| 邮件 | `SMTP_*` + 项目 `Recipient` | `send_report_email` |
| 通用 Webhook | `RUN_FAILURE_WEBHOOK_URL` + `generic` in channels | JSON `event=run.failed` |
| 钉钉 | `DINGTALK_WEBHOOK_URL`、可选 `DINGTALK_WEBHOOK_SECRET`（加签） | markdown |
| 企微 | `WECOM_WEBHOOK_URL` | markdown |

`RUN_FAILURE_ALERT_CHANNELS=generic,dingtalk,wecom`（逗号分隔）。实现：`backend/services/alert_channels.py`，编排：`backend/services/run_alert_service.py`。

---

## v0.8 性能监控与安全增强

- k6 结构化指标入库（`summary_metrics` / `time_series`），Dashboard `latest_k6` + `GET /dashboard/run-trends`（ECharts）
- 向量 RAG：`knowledge_chunks.embedding` + `GET .../knowledge/search`；Agent/用例生成接入检索
- 计划/套件驱动 Run：`suite_id` / `plan_id` → `functional` kind；前端子路由 `/projects/:id/{cases,ai,runs,reports}`
- k6 NDJSON 时序解析（`parse_k6_ndjson_timeseries`），替代纯 synthetic 曲线（仍保留 summary 回退）
- 任务中心：`GET /runs/recent` + 前端 `/tasks`
- Run 状态：任一测试项 `failed`/`error` 则整次 Run 为 `failed`
- k6 execution segment 环境变量 + 分片元数据
- `POST .../perf/k6-jobs/{id}/analyze-bottleneck` AI 瓶颈建议
- `start_run` 的 `perf_*` / `security_*` 与 k6、bandit、AI 扫描、nuclei/zap 适配器打通
- 安全报告 HTML/PDF、漏洞项复核（误报/确认 → Prompt 反馈闭环）

## v0.7 接口自动化闭环

- `start_run` 的 `api` kind：`api_mode=auto` 时若项目有 DSL 产物则走 `dsl://api-automation`（替代 pytest）
- `api_regression_sets`：按 `case_id` 绑定回归集，`regression_set_id` 驱动批量 DSL 执行
- DSL 工具：`/api-automation/dsl/preview`、`/dsl/execute-step`；产物脚本 `PATCH .../script`
- 失败归因：`POST .../artifacts/{id}/analyze-failure`（AI 根因 + 修复建议）

## v0.6 需求预评审增强

- Word/Markdown/TXT 上传解析（`python-docx`）
- 评审报告 HTML 在线预览
- 评审项一键转功能用例（打通模块 1→2）
- 两版评审 diff（`from_id` / `to_id`）

## v0.5 新增能力

- **安全扫描引擎**：真实 HTTP 发包 + 启发式漏洞识别，结果写入 `security_scan_jobs`
- **分布式 k6**：`k6_worker_nodes` + 并发分片调度；Worker 暴露 `POST /internal/k6/run`
- **Alembic autogenerate**：`alembic revision --autogenerate` → `8fc22864ffb9_full_schema_v05`
- **前端 Arco 全量**：登录、RBAC、项目详情、k6 节点管理页

## v0.4 新增能力

- **DSL 执行器**：`POST .../artifacts/{id}/execute`，YAML DSL + httpx 断言
- **k6 压测下发**：`POST .../artifacts/{id}/dispatch-perf`，AI 压测方案转 k6 脚本
- **需求评审 PDF**：`GET .../requirement-reviews/{id}/pdf`
- **Prompt 闭环**：`POST /ai/prompt-feedback` → `apply-suggestions` 生成新模板版本
- **Alembic**：`alembic upgrade head`（MySQL 新环境）
- **前端 Arco**：Shell 布局、首页看板、项目列表、Prompt 页

### MySQL 生产部署示例

```bash
DATABASE_URL=mysql+pymysql://user:pass@127.0.0.1:3306/ai_tp?charset=utf8mb4
pip install -e ".[mysql,redis,worker,observability]"

alembic upgrade head
export SCHEMA_BOOTSTRAP_MODE=alembic
export JOB_WORKER_IN_API=false
export JOB_QUEUE_BACKEND=rq          # 或 celery / redis / db
export REDIS_URL=redis://127.0.0.1:6379/0

# API
uvicorn backend.main:app --host 0.0.0.0 --port 8001

# Worker（另进程/容器）
python -m backend.worker
# 或: celery -A backend.celery_app worker -l info -Q ai_tp_execution
```

可观测性：抓取 `http://<api>:8001/metrics`；链路导出配置 `OTEL_EXPORTER_OTLP_ENDPOINT`。
