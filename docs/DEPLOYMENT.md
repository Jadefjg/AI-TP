# AI-TP 部署指导方案

> 适用版本：v0.8 · 仓库：https://github.com/Jadefjg/AI-TP  
> 目标：给出可落地的**最佳默认路径**，并按场景给出升级选项。

---

## 1. 项目特征分析（决定怎么部署）

| 维度 | 现状 | 部署含义 |
|------|------|----------|
| 架构 | 前后端分离：Vue3(Vite) + FastAPI | 生产需分别构建前端静态资源与 API 进程 |
| 存储 | 默认 SQLite；已支持 MySQL + Alembic | **演示可用 SQLite；正式环境必须 MySQL（或兼容库）** |
| 任务 | `execution_jobs` + Worker（db/redis/rq/celery） | 跑测试/AI 任务建议 **API 与 Worker 进程分离** |
| 执行器 | 本机调用 pytest / k6 / bandit / playwright 等 | Worker 所在机器需安装对应工具；缺失则 `skipped` 不崩 |
| 密钥 | `.env`（LLM、SMTP、OIDC、Stripe、飞书等） | **严禁进镜像/仓库**；用环境变量或密钥托管 |
| 前端代理 | 开发态 Vite `/api` → 后端 | 生产由 Nginx 反代，或把 `VITE_API_BASE_URL` 指到公网 API |
| CI | GitHub Actions：pytest + `npm run build` | 可直接接到「构建 → 发版」流水线 |
| 容器化 | 见 [DEPLOYMENT.DOCKER.md](./DEPLOYMENT.DOCKER.md)、[DEPLOYMENT.ALIYUN.md](./DEPLOYMENT.ALIYUN.md) 与根目录 `docker-compose.yml` | **推荐默认：Compose 一键部署** |

**结论：**  
- 短平快演示：单机 + SQLite + API 内嵌 Worker。  
- **推荐生产默认：** Docker Compose（Nginx + API + Worker + MySQL + Redis）。  
- 高并发/多租户：再拆多副本 API、RQ/Celery Worker、对象存储与独立 k6 节点。

完整容器步骤 → **[DEPLOYMENT.DOCKER.md](./DEPLOYMENT.DOCKER.md)**。  
阿里云 ECS 专项 → **[DEPLOYMENT.ALIYUN.md](./DEPLOYMENT.ALIYUN.md)**。

---

## 2. 推荐拓扑（最佳默认）

```text
                    ┌─────────────┐
  用户 ──HTTPS──►   │   Nginx     │
                    │  :443/:80   │
                    └──────┬──────┘
           /               │               /api
           ▼               │               ▼
    frontend/dist     （静态文件）     uvicorn API :8002
                                           │
                           ┌───────────────┼───────────────┐
                           ▼               ▼               ▼
                        MySQL           Redis          Worker
                     (业务数据)     (队列/缓存可选)   (执行 Run/AI)
                           │                               │
                           └────────── data 卷 ◄───────────┘
                                 (报告/k6/outbox)
```

**进程职责**

| 组件 | 作用 | 关键配置 |
|------|------|----------|
| Nginx | TLS、静态前端、`/api` 反代 | `proxy_pass` → API |
| API | HTTP 业务、鉴权、入队 | `JOB_WORKER_IN_API=false` |
| Worker | 认领并执行 `execution_jobs` | `JOB_WORKER_ENABLED=true` |
| MySQL | 持久化 | `DATABASE_URL=mysql+pymysql://...` |
| Redis | 队列通知 / AI 上下文缓存 | `REDIS_URL`；`JOB_QUEUE_BACKEND=redis` 或 `rq` |

---

## 3. 分场景选型

| 场景 | 数据库 | 队列 | Worker | 适用 |
|------|--------|------|--------|------|
| **A. 本地/演示** | SQLite | `db` + 内嵌 | `JOB_WORKER_IN_API=true` | 开发联调 |
| **B. 内网试用（推荐起步）** | MySQL | `db` 或 `redis` | 独立 `python -m backend.worker` | 小团队 1～2 台机 |
| **C. 正式生产（最佳默认）** | MySQL | `rq` + Redis | 独立 RQ Worker | 稳定跑任务、可扩容 |
| **D. 规模化** | MySQL 主从 | Celery + Redis | 多 Worker + k6 节点 | 多租户、压测密集 |

**最佳默认选 C（或先 B 再平滑升到 C）。** 不建议生产长期使用 SQLite 与 API 内嵌 Worker。

---

## 4. 生产环境变量清单（必改项）

从 `.env.example` 复制为部署环境变量（勿提交真实 `.env`）。

### 4.1 必须修改

```bash
# 库
DATABASE_URL=mysql+pymysql://ai_tp:强密码@127.0.0.1:3306/ai_tp?charset=utf8mb4
SCHEMA_BOOTSTRAP_MODE=alembic

# 进程拆分
JOB_WORKER_IN_API=false
JOB_WORKER_ENABLED=true
JOB_QUEUE_BACKEND=rq          # 或 redis / db（试用）
REDIS_URL=redis://127.0.0.1:6379/0

# 安全
BACKEND_CORS_ORIGINS=https://your-domain.com
AI_CREDENTIALS_ENCRYPTION_KEY=请换成足够长的随机串
# 首次启动后立刻改掉默认管理员密码（默认 admin / admin123）

# 对外地址
CI_WEBHOOK_PUBLIC_BASE_URL=https://api.your-domain.com
BILLING_CHECKOUT_SUCCESS_URL=https://your-domain.com/billing/success
BILLING_CHECKOUT_CANCEL_URL=https://your-domain.com/billing/cancel

# 邮件（关闭 dry-run）
SMTP_DRY_RUN=false
SMTP_HOST=...
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_FROM=noreply@your-domain.com
```

### 4.2 按能力选配

| 能力 | 变量 |
|------|------|
| LLM | `OPENAI_*` 或 `DEEPSEEK_*`；可选 `AI_LOCAL_*` |
| 指标 | `METRICS_AUTH_ENABLED=true` + `METRICS_BEARER_TOKEN` |
| 告警 | `DINGTALK_*` / `WECOM_*` / `RUN_FAILURE_WEBHOOK_URL` |
| 飞书拉文档 | `FEISHU_APP_ID` / `FEISHU_APP_SECRET` |
| OIDC | `OIDC_ENABLED=true` + Issuer/Client |
| k6 分布式 | `K6_WORKER_TOKEN`、节点登记 |

### 4.3 前端构建期

```bash
# 与 Nginx 同域反代时（推荐）
VITE_API_BASE_URL=/api

# 或跨域直连 API
# VITE_API_BASE_URL=https://api.your-domain.com
```

生产构建：

```bash
cd frontend
cp .env.example .env   # 按上修改
npm ci
npm run build          # 产出 frontend/dist
```

---

## 5. 推荐落地步骤（无 Docker 时：单机 Linux）

> 适用于快速上线；后续可用同一套目录结构迁到 Compose。

### 5.1 系统依赖

- Python ≥ 3.11、Node ≥ 20  
- MySQL 8、Redis 7（场景 C）  
- 可选执行器：`pytest`、`k6`、`bandit`、Playwright 浏览器等（按需装在 **Worker 机**）

### 5.2 后端

```bash
git clone git@github.com:Jadefjg/AI-TP.git /opt/ai-tp
cd /opt/ai-tp
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[mysql,redis,worker,observability]"

cp .env.example .env
# 编辑 .env：DATABASE_URL / REDIS / JOB_* / CORS / 密钥等

mkdir -p data
alembic upgrade head

# API（示例端口 8002）
JOB_WORKER_IN_API=false uvicorn backend.main:app --host 127.0.0.1 --port 8002

# 另开终端：Worker
JOB_QUEUE_BACKEND=rq REDIS_URL=redis://127.0.0.1:6379/0 \
  JOB_WORKER_ENABLED=true python -m backend.worker
```

建议用 **systemd** 或 **supervisor** 托管 API / Worker，并配置开机自启与日志轮转。

### 5.3 前端

```bash
cd /opt/ai-tp/frontend
npm ci && npm run build
# 将 dist 交给 Nginx root，或 rsync 到静态目录
```

### 5.4 Nginx 示例（同域）

```nginx
server {
  listen 443 ssl http2;
  server_name your-domain.com;
  # ssl_certificate ...;

  root /opt/ai-tp/frontend/dist;
  index index.html;

  location / {
    try_files $uri $uri/ /index.html;
  }

  location /api/ {
    proxy_pass http://127.0.0.1:8002/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 32m;   # 需求文档上传
    proxy_read_timeout 300s;    # AI / 长请求
  }
}
```

注意：前端 `VITE_API_BASE_URL=/api` 时，浏览器请求 `/api/...`，Nginx 需 rewrite 或如上 `proxy_pass` 去掉 `/api` 前缀，与开发态 Vite proxy 行为一致。

### 5.5 验收清单

- [ ] `https://your-domain.com` 可打开登录页  
- [ ] `https://your-domain.com/api/docs` 或直连 API `/docs` 正常  
- [ ] 登录后改管理员密码  
- [ ] 创建项目 → 需求分析/生成用例（有 LLM Key 或接受 stub）  
- [ ] 发起一次 Run：任务进入 `running` → `completed/failed`，Worker 日志有认领记录  
- [ ] `/metrics` 在开启鉴权后需带 Token  

---

## 6. 容器化部署（已落地）

仓库已提供完整 Compose 栈，**生产推荐优先走 Docker**，无需再手工装 MySQL/Redis/Nginx。

| 路径 | 作用 |
|------|------|
| `docker-compose.local.yml` | 本地一键部署 |
| `docker-compose.aliyun.yml` | 阿里云 ECS 一键部署 |
| `docker-compose.yml` | 基础栈 |
| `deploy/Dockerfile` | API + Worker（`runtime` / `worker-tools`） |
| `deploy/Dockerfile.web` | 前端 + Nginx |
| `deploy/.env.docker.local.example` | 本地 env 模板 |
| `deploy/.env.docker.aliyun.example` | 阿里云 env 模板 |
| `deploy/scripts/local-deploy.sh` | 本地一键脚本 |
| `deploy/scripts/aliyun-deploy.sh` | 阿里云一键脚本 |

**快速启动：**

```bash
# 本地
cp deploy/.env.docker.local.example deploy/.env.docker
docker compose -f docker-compose.local.yml up -d --build

# 阿里云 ECS
cp deploy/.env.docker.aliyun.example deploy/.env.docker
docker compose -f docker-compose.aliyun.yml up -d --build
```

**阿里云 ECS** 完整步骤（安全组、镜像加速、HTTPS、备份）→ **[DEPLOYMENT.ALIYUN.md](./DEPLOYMENT.ALIYUN.md)**。  
容器细节与故障排查 → **[DEPLOYMENT.DOCKER.md](./DEPLOYMENT.DOCKER.md)**。  
推送镜像到 Docker Hub / ACR → **[DOCKER_HUB.md](./DOCKER_HUB.md)**。

---

## 7. 安全基线

1. 默认账号 `admin` / `admin123` **上线后立即修改**  
2. 生产关闭调试热重载；API 只绑 `127.0.0.1`，对外只暴露 Nginx。  
3. `BACKEND_CORS_ORIGINS` 收紧为真实前端域名。  
4. `METRICS_AUTH_ENABLED=true`，避免指标裸奔。  
5. SMTP / LLM / Stripe / 飞书密钥用密钥管理，定期轮换。  
6. Worker 若执行用户仓库代码，按最小权限跑（独立 OS 用户、目录白名单）。  
7. 定期备份 MySQL + `data/`（报告、k6 产物、发件箱）。

---

## 8. 运维与发布

| 动作 | 建议 |
|------|------|
| 发版 | tag → CI 构建前端 + 测后端 → 滚动更新 API/Worker |
| 迁移 | 发版前 `alembic upgrade head`；`SCHEMA_BOOTSTRAP_MODE=alembic` |
| 回滚 | 保留上一版镜像/目录；DB 回滚需有备份，慎用 downgrade |
| 日志 | journald / 文件 + 请求头 `X-Request-ID` |
| 监控 | Prometheus 抓 `/metrics`；可选 OTLP |
| 告警 | Run 失败 Webhook / 钉钉 / 企微 |

---

## 9. 实施优先级（建议排期）

| 优先级 | 事项 | 产出 |
|--------|------|------|
| P0 | Docker Compose 场景 C 跑通（或 [阿里云 ECS](./DEPLOYMENT.ALIYUN.md)） | 可对外/对内访问 |
| P0 | 改密、CORS、SMTP/LLM、备份 | 安全与可用性 |
| P1 | `docker-compose.aliyun.yml` + HTTPS（SLB/Caddy） | 生产加固 |
| P1 | CI 推镜像至 Hub/ACR | 可重复发版 |
| P2 | 多 Worker 副本、k6 分布式节点 | 扩容 |
| P2 | 指标鉴权、审计导出、OIDC | 合规 |

---

## 10. 与当前开发环境的对应关系

| 本地开发 | 生产对应 |
|----------|----------|
| `uvicorn --reload :8002` | `uvicorn` 无 reload + systemd/容器 |
| Vite `:5174` + proxy `/api` | Nginx 静态 `dist` + `/api` 反代 |
| SQLite `data/ai_tp.db` | MySQL |
| `JOB_WORKER_IN_API=true` | `false` + 独立 Worker |
| `.env` 本机文件 | 主机 env / Compose secrets / 云厂商密钥 |

本地启动说明仍见根目录 [README.md](../README.md)；架构细节见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

---

## 11. 一句话决策

**正式对外（推荐）：`docker-compose.aliyun.yml`（Web + API + Worker + MySQL + Redis/RQ），前置 HTTPS。**  
无 Docker 时见 §5 单机 systemd 路径；阿里云见 [DEPLOYMENT.ALIYUN.md](./DEPLOYMENT.ALIYUN.md)。
