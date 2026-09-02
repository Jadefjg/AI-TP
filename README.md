# AI 测试平台（ai-tp）

一个前后端分离的 AI 测试平台：

- 后端：FastAPI + SQLAlchemy
- 前端：Vue3 + Vite + TypeScript

支持能力：

1. **七层架构 + 五个专业 Agent**：接入 / 业务 / AI 网关 / 调度 / 执行引擎 / 存储 / 监控；流水线 **需求 Agent → UI Agent → 接口 Agent → 性能 Agent → 安全 Agent**
2. 需求文本生成功能测试用例（可接 LLM，未配置时回退 stub）
3. 按项目代码执行多类测试（单元、接口、性能、安全、UI）
4. 生成测试报告并发送给项目收件人
5. RAG 知识库入库与 Agent 化用例生成（根据项目知识增强上下文）

架构说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。  
**生产部署**见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。  
**容器化（推荐）**见 [docs/DEPLOYMENT.DOCKER.md](docs/DEPLOYMENT.DOCKER.md)（统一 `docker-compose.yml`，本地/阿里云通过 env 区分）。  
**阿里云 ECS**见 [docs/DEPLOYMENT.ALIYUN.md](docs/DEPLOYMENT.ALIYUN.md)。  
**推送到 Docker Hub / 异地运行**见 [docs/DOCKER_HUB.md](docs/DOCKER_HUB.md)。

**当前版本 v0.8**：接口自动化 DSL 闭环、性能 k6 结构化监控、安全扫描与 Run 整合（bandit/npm audit + nuclei/zap）、任务中心。

**v0.6**：需求预评审文档上传 / HTML / diff / 转用例。

**v0.5–v0.4**：安全扫描发包、k6 分布式、Arco Shell、Alembic、Prompt 闭环（历史能力仍保留）。

---

## 目录结构

```text
ai-tp/
  backend/      # 后端 API
  frontend/     # 前端 Web
  data/         # SQLite 等数据文件
```

---

## 1) 启动后端 API

```bash
cd /Users/mark/Documents/0Study/ai-tp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8001
```

访问：

- API 根：`http://127.0.0.1:8001/`
- Swagger：`http://127.0.0.1:8001/docs`

---

## 2) 启动前端 Web

```bash
cd /Users/mark/Documents/0Study/ai-tp/frontend
cp .env.example .env
npm install
npm run dev
```

访问：

- 前端页面：`http://127.0.0.1:5174/`（与 mt-edu 的 `5173` 区分）
- 租户管理（成员 + 账单）：`/tenant`（需 `org.read`；成员管理需 `org.member.*`，账单需 `billing.*`）
- Stripe 支付回跳：`/billing/success`、`/billing/cancel`（与 `.env` 中 `BILLING_CHECKOUT_*_URL` 一致）

---

## 关键配置

后端 `.env`：

- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`
- `AI_HIGH_PRECISION_MODEL` / `AI_BULK_MODEL` / `AI_FALLBACK_MODEL`
- `AI_LOCAL_BASE_URL` / `AI_LOCAL_MODEL`（私有化大模型）
- `REDIS_URL`（可选，AI 上下文缓存）
- `DATABASE_URL`
- `SMTP_*`
- `BACKEND_CORS_ORIGINS`（逗号分隔）
- P2 多租户：`DEFAULT_ORGANIZATION_SLUG`、`AI_CREDENTIALS_ENCRYPTION_KEY`
- P2 OIDC：`OIDC_ENABLED`、`OIDC_ISSUER_URL`、`OIDC_CLIENT_*`

前端 `.env`：

- `VITE_API_BASE_URL`（默认 `http://127.0.0.1:8001`）

---

## 测试执行说明

后端会按测试类型执行本机命令（例如 `pytest`、`k6`、`bandit`、`playwright`）。若工具不存在，会标记为 `skipped` 并记录原因，不会导致整个 run 直接崩溃。

### 生产 Worker 与队列

```bash
pip install -e ".[worker,observability]"   # RQ/Celery + Prometheus/OTLP（可选）

# API（不内嵌 Worker；rq/celery 模式 API 也不会启动 DB 轮询）
JOB_WORKER_IN_API=false uvicorn backend.main:app --port 8001

# DB / Redis 轻量队列
JOB_QUEUE_BACKEND=db          # 或 redis + REDIS_URL
JOB_WORKER_ENABLED=true python -m backend.worker

# RQ（完整集成）
JOB_QUEUE_BACKEND=rq REDIS_URL=redis://127.0.0.1:6379/0 python -m backend.worker

# Celery
JOB_QUEUE_BACKEND=celery REDIS_URL=redis://127.0.0.1:6379/0 \
  celery -A backend.celery_app worker -l info -Q ai_tp_execution
```

**数据库迁移（推荐新环境）**

```bash
alembic upgrade head
SCHEMA_BOOTSTRAP_MODE=alembic   # 启动时仅 seed，不再 create_all/ALTER 补丁
```

旧 SQLite 实例可继续 `SCHEMA_BOOTSTRAP_MODE=bootstrap`（等同 legacy 补丁模式）。

**可观测性**

- Prometheus：`GET /metrics`（`METRICS_ENABLED=true`）；生产可设 `METRICS_AUTH_ENABLED=true` + `METRICS_BEARER_TOKEN` 供抓取
- Dashboard：`GET /dashboard/summary`、`/dashboard/run-trends` 按租户聚合（平台管理员可选 `?organization_id=`）
- 请求链路：`X-Request-ID` / `X-Trace-ID` 响应头；配置 `OTEL_EXPORTER_OTLP_ENDPOINT` 导出 OTLP

**失败告警**

- 邮件：SMTP + 项目收件人
- 通道：`RUN_FAILURE_ALERT_CHANNELS=generic,dingtalk,wecom`
- 钉钉：`DINGTALK_WEBHOOK_URL` + 可选 `DINGTALK_WEBHOOK_SECRET`（加签）
- 企微：`WECOM_WEBHOOK_URL`
- 通用 Webhook：`RUN_FAILURE_WEBHOOK_URL`

---

## 需求预评审增强（v0.6）

- 文档上传：`.docx` / `.md` / `.txt` → `POST .../requirement-reviews/parse-document` 或 `POST .../requirement-review/upload`
- HTML 在线预览：`GET .../requirement-reviews/{id}/html`
- 评审项转用例：`POST .../requirement-reviews/{id}/convert-to-cases`
- 版本对比：`GET .../requirement-reviews/diff?from_id=&to_id=`

## 专业 Agent 与 AI 模块 API

- Agent 目录：`GET /ai/agents`（五个专业 Agent + 网关统计 + 覆盖/误报）
- 需求 Agent：`POST /projects/{id}/ai/requirement-review`；转用例 `POST .../convert-to-cases`；用例生成 `POST .../ai/functional-cases` / `.../functional-cases/generate-agent`
- UI Agent：`POST /projects/{id}/ui-automation/generate-from-case`、`execute-agent`（Playwright GUI Agent）
- Prompt 模板：`GET /ai/prompt-templates`，前端 **AI Prompt** 菜单页可视化编辑
- 接口 Agent：`POST /projects/{id}/ai/api-automation`；执行 `POST .../ai/artifacts/{aid}/execute`
- 性能 Agent：`POST /projects/{id}/ai/perf-plan`；下发 `POST .../ai/artifacts/{aid}/dispatch-perf`
- 安全 Agent：`POST /projects/{id}/ai/security-scan`；扫描 `POST .../ai/artifacts/{aid}/dispatch-security`
- Token 统计：`GET /ai/usage/summary`
- 评审 PDF：`GET /projects/{id}/ai/requirement-reviews/{rid}/pdf`
- Prompt 闭环：`POST /ai/prompt-feedback` → `POST /ai/prompt-templates/apply-suggestions`

### 数据库迁移（MySQL 生产）

```bash
pip install -e ".[mysql,redis]"
# .env: DATABASE_URL=mysql+pymysql://user:pass@host:3306/ai_tp?charset=utf8mb4
alembic upgrade head
# 新环境仅走迁移 + 种子数据（跳过 create_all）：
# SCHEMA_BOOTSTRAP_MODE=alembic
# 持久化任务队列 Worker（测试可关闭）：JOB_WORKER_ENABLED=true
# 模型变更后：
alembic revision --autogenerate -m "describe_change"
alembic upgrade head
```

### 安全扫描与分布式 k6（v0.5）

- 安全扫描：`POST /projects/{id}/ai/artifacts/{aid}/dispatch-security`（body: `target_url`, `query_params`…）
- 分布式压测：`POST .../dispatch-perf` + `distributed: true`；节点管理 `/admin/k6-workers`
- Worker Agent：`POST /internal/k6/run`（Header `X-Worker-Token` 可选）

## RAG 与 Agent 生成

### 1) 先入库项目知识（PRD、业务规则、历史缺陷）

`POST /projects/{project_id}/knowledge/chunks`

示例 body:

```json
{
  "source": "prd",
  "title": "支付模块规则",
  "content": "订单金额超过5000时必须触发二次校验..."
}
```

### 2) 使用 Agent + RAG 生成测试用例

`POST /projects/{project_id}/functional-cases/generate-agent`

这个接口会：

1. 从知识库检索相关片段
2. 将片段拼接进提示词上下文
3. 调用 LLM（或本地模板回退）生成用例
4. 返回 `cases + contexts`，便于追溯“用到了哪些知识”
# AI-TP
