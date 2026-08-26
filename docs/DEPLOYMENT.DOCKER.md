# AI-TP 容器化部署指导方案

> 配套文件：根目录 `docker-compose.yml`、`deploy/`  
> 总览部署见 [DEPLOYMENT.md](./DEPLOYMENT.md)

---

## 1. 分析结论：为何这样拆容器

| 组件 | 是否独立容器 | 原因 |
|------|--------------|------|
| **web** (Nginx + 前端 dist) | 是 | 静态资源与 TLS/反代边界清晰；多阶段构建不含 Node 运行时 |
| **api** (Uvicorn) | 是 | 无状态 HTTP；可水平扩副本 |
| **worker** | 是（默认可选 **tools 镜像**） | Run/AI 任务耗时长；tools 镜像含 k6 / Playwright / nuclei，缺失工具仍 `skipped` |
| **mysql** | 是 | 生产禁止 SQLite；数据卷持久化 |
| **redis** | 是 | RQ 队列 + AI 上下文缓存 |

**最佳默认栈（场景 C）：**

```text
浏览器 → web:8088
           ├─ /        → frontend/dist
           └─ /api/*   → api:8002
                            ├─ MySQL
                            └─ Redis ← worker (RQ)
```

同镜像 `deploy/Dockerfile` 同时服务 API / Worker，只改启动命令，保证依赖一致、构建成本低。

---

## 2. 仓库内已提供的产物

| 路径 | 作用 |
|------|------|
| `docker-compose.yml` | 一键编排 mysql / redis / api / worker / web（含可配置 `image:` 便于 Hub 推送） |
| `deploy/Dockerfile` | 多阶段：`runtime`（API）+ `worker-tools`（k6 / Playwright / nuclei） |
| `deploy/Dockerfile.worker-tools` | 兼容别名（推荐直接用 Dockerfile target） |
| `deploy/Dockerfile.web` | Node 构建前端 + Nginx 托管 |
| `deploy/nginx/default.conf` | SPA + `/api` 反代 |
| `deploy/scripts/entrypoint-*.sh` | 等待依赖、迁移、启动进程 |
| `deploy/scripts/push-images.sh` | 构建并推送 api/web 镜像到 Docker Hub（等） |
| `deploy/.env.docker.example` | 容器环境变量模板（含 `AI_TP_*_IMAGE`） |
| `.dockerignore` | 缩小构建上下文、避免打入 `.env`/venv |

---

## 3. 快速启动（推荐路径）

### 3.1 前置

- Docker Engine 24+ / Docker Compose v2  
- 本机端口：`8088`（Web）、可选 `3307`（MySQL 映射）、`6380`（Redis 映射）

### 3.2 配置

```bash
cd /path/to/ai-tp
cp deploy/.env.docker.example deploy/.env.docker
# 至少修改：MYSQL_*_PASSWORD、BOOTSTRAP_ADMIN_PASSWORD、AI_CREDENTIALS_ENCRYPTION_KEY
# 建议配置：DEEPSEEK_API_KEY 或 OPENAI_API_KEY
```

### 3.3 构建并启动

```bash
docker compose --env-file deploy/.env.docker up -d --build
```

### 3.4 验证

```bash
# 前端
curl -sI http://127.0.0.1:8088/ | head -5

# API（经 Nginx）
curl -s http://127.0.0.1:8088/api/ | head -c 200; echo

# 直连 API 容器网络外：默认未映射 8002；可用
docker compose --env-file deploy/.env.docker exec api curl -s http://127.0.0.1:8002/
```

浏览器打开：**http://localhost:8088/**  
默认管理员与登录页一致：`admin` / `admin123456`（由 `BOOTSTRAP_ADMIN_*` 在**首次建库**时写入）。若你改过示例密码，请用该密码登录，或重建数据卷。**登录后立刻改密。**

### 3.5 常用运维命令

```bash
# 日志
docker compose --env-file deploy/.env.docker logs -f api worker web

# 扩容 Worker
docker compose --env-file deploy/.env.docker up -d --scale worker=2

# 迁移（API 启动已自动 alembic；也可手动）
docker compose --env-file deploy/.env.docker exec api alembic upgrade head

# 停止并保留数据卷
docker compose --env-file deploy/.env.docker down

# 危险：清数据
docker compose --env-file deploy/.env.docker down -v
```

---

## 4. 镜像与进程设计要点

### 4.1 API 入口 (`entrypoint-api.sh`)

1. 等待 MySQL TCP 就绪  
2. `Base.metadata.create_all`（补齐 ORM 核心表；Alembic 增量修订依赖它们已存在）  
3. `alembic upgrade head`（`RUN_MIGRATIONS=true`；增量修订均为幂等）  
4. `uvicorn backend.main:app --host 0.0.0.0 --port 8002`  
5. 强制 `JOB_WORKER_IN_API=false`（由 Compose 注入）

> 若曾因迁移半失败留下脏库，需 `docker compose ... down -v` 后重建（会清空数据卷）。

### 4.2 Worker 入口 (`entrypoint-worker.sh`)

1. 等待 MySQL / Redis  
2. `python -m backend.worker`（`JOB_QUEUE_BACKEND=rq`）

### 4.3 Web 镜像

- Build 阶段：`npm ci` + `VITE_API_BASE_URL=/api`  
- Runtime：仅 Nginx + `dist`，反代到 `api:8002`

### 4.4 数据卷

| Volume | 内容 |
|--------|------|
| `ai_tp_mysql` | 业务库 |
| `ai_tp_redis` | AOF |
| `ai_tp_data` | 报告、k6 产物、SMTP dry-run 发件箱等 |

---

## 5. 环境变量分层

| 层级 | 来源 | 说明 |
|------|------|------|
| Compose 插值 | `deploy/.env.docker` 中 `MYSQL_*`、`WEB_PUBLISH_PORT` | 给 compose 文件 `${VAR}` |
| 容器运行时 | 同文件 `env_file` + `environment` 覆盖 | `DATABASE_URL`/`REDIS_URL` 由 compose 指向服务名 |
| 前端构建期 | `Dockerfile.web` `ARG VITE_API_BASE_URL` | **构建后不可靠改**；同域 `/api` 最省事 |

**切勿**把 `deploy/.env.docker` 提交进 Git（已在 `.gitignore` 的 `.env*` 规则覆盖；示例文件 `deploy/.env.docker.example` 可提交）。

---

## 6. 场景变体

### 6.1 仅内网试用（减配）

- 可将 `JOB_QUEUE_BACKEND=db`，仍建议保留独立 `worker` 服务  
- 可去掉对外映射的 MySQL/Redis 端口（编辑 compose `ports`）

### 6.2 生产 HTTPS / 收紧端口

```bash
# 不暴露 MySQL/Redis 到宿主机（需 Compose v2.24+）
docker compose -f docker-compose.yml -f compose.prod.yml --env-file deploy/.env.docker up -d
```

在宿主机或前置再挂一层 Caddy/Nginx/云 LB 做 443，反代到 `web:80`；或扩展 `web` 服务挂证书。

### 6.3 需要本机执行器（k6 / Playwright）

默认应用镜像**偏瘦**，未预装 k6/浏览器。选项：

1. **扩展 Worker Dockerfile**：安装 k6、playwright 依赖（镜像变大）  
2. **Sidecar / 独立 k6-worker 容器**：走现有 `/internal/k6` + `K6_WORKER_TOKEN`  
3. 接受工具缺失时 Run 项为 `skipped`

### 6.4 多副本 API

```bash
docker compose --env-file deploy/.env.docker up -d --scale api=2
```

注意：需在 `web` 前加负载均衡，或改 Nginx `upstream`；迁移只应有一个实例执行（可用 `RUN_MIGRATIONS=false` 在副本上关闭）。

---

## 7. 安全清单（容器专属）

- [ ] 修改所有默认密码与 `AI_CREDENTIALS_ENCRYPTION_KEY`  
- [ ] 生产不要映射 MySQL/Redis 到公网；仅 Docker 网络互通  
- [ ] `BACKEND_CORS_ORIGINS` 改为真实域名  
- [ ] `METRICS_AUTH_ENABLED=true` 并配置 Token  
- [ ] 镜像构建上下文已被 `.dockerignore` 排除 `.env` / `.venv`  
- [ ] 定期 `docker volume` 备份（至少 `ai_tp_mysql`、`ai_tp_data`）

---

## 8. 故障排查

| 现象 | 排查 |
|------|------|
| web 502 | `docker compose logs api`；健康检查是否通过；迁移是否卡住 |
| 登录后任务一直 pending | `worker` 是否启动；`REDIS_URL` / `JOB_QUEUE_BACKEND=rq` |
| 前端调 API 404 | 确认构建使用 `/api` 且 Nginx `location /api/` 存在 |
| DB 连接失败 | Compose 内主机名必须是 `mysql` 而非 `127.0.0.1` |
| 权限/表不存在 | `exec api alembic upgrade head`；`SCHEMA_BOOTSTRAP_MODE=alembic` |
| worker 构建 `Unable to locate package k6` | 官方 apt 源无 arm64 包（Apple Silicon 常见）。当前 Dockerfile 已改为按架构下载 GitHub 官方二进制 |
| redis `Bind ... 6379 failed: port is already allocated` | 宿主机 6379 被其他栈/本机 Redis 占用。发布端口已默认改为 `6380`（容器内仍是 `redis:6379`） |
| web `Bind ... 8080 failed: port is already allocated` | 宿主机 8080 被其他栈占用。发布端口已默认改为 `8088` |
| 打开 8088 却看到别的系统（如医疗问诊） | 多半是 Nginx 把 `/api` 绝对重定向到了宿主机 `:80`。已改为相对重定向；请访问 http://localhost:8088/login |

---

## 9. 与非容器部署的关系

| 非容器（DEPLOYMENT.md） | 容器 |
|-------------------------|------|
| systemd 管 API/Worker | Compose `restart: unless-stopped` |
| 本机 Nginx | `web` 服务 |
| 本机 MySQL/Redis | `mysql` / `redis` 服务 |
| 手动 `alembic` | API entrypoint 自动迁移 |

**一句话：** 用 Compose 一次拉起「Web + API + Worker + MySQL + Redis」；密钥放 `deploy/.env.docker`；对外只暴露 Web（及可选 HTTPS 入口）。

---

## 10. 推送到 Docker Hub 并在其他电脑运行

> **独立操作手册（推荐先读）**：[DOCKER_HUB.md](./DOCKER_HUB.md)

Docker Desktop 里名为 `ai-tp` 的条目是 **Compose 项目（一组容器）**，不能整包当成一个镜像上传。需要推送的只有自定义镜像；`mysql` / `redis` 用官方镜像，异地会自动拉取。

| 服务 | 镜像 | 是否 push |
|------|------|-----------|
| mysql | `mysql:8.4` | 否 |
| redis | `redis:7-alpine` | 否 |
| api / worker | `AI_TP_API_IMAGE`（同一镜像，worker 换启动命令） | **是** |
| web | `AI_TP_WEB_IMAGE` | **是** |

### 10.1 本机：登录并推送

```bash
# 1) 注册 https://hub.docker.com ，本机登录
docker login

# 2) 配置（把 youruser 换成 Hub 用户名）
cp -n deploy/.env.docker.example deploy/.env.docker
# 编辑 deploy/.env.docker：
#   AI_TP_API_IMAGE=youruser/ai-tp-api:latest
#   AI_TP_WEB_IMAGE=youruser/ai-tp-web:latest
# 并填好 MYSQL_*、BOOTSTRAP_ADMIN_*、AI_CREDENTIALS_ENCRYPTION_KEY 等

# 3) 构建并推送（推荐脚本）
chmod +x deploy/scripts/push-images.sh
./deploy/scripts/push-images.sh youruser
# 或指定版本标签：
# ./deploy/scripts/push-images.sh youruser v0.8.0
```

等价手动命令：

```bash
docker build -f deploy/Dockerfile -t youruser/ai-tp-api:latest .
docker build -f deploy/Dockerfile.web -t youruser/ai-tp-web:latest .
docker push youruser/ai-tp-api:latest
docker push youruser/ai-tp-web:latest
```

### 10.2 拷贝到其他电脑的文件

至少需要（**不要**把含真实密钥的 `.env.docker` 提交到公开 Git）：

- `docker-compose.yml`
- `deploy/.env.docker`（由 example 复制并改好 `AI_TP_*_IMAGE` 与密钥）

无需拷贝完整源码即可 `pull` + `up`（镜像已在 Hub）。若仍要用 `--build`，则需要完整仓库。

### 10.3 其他电脑：拉取并启动

```bash
# 安装 Docker Desktop / Engine + Compose v2 后：
docker login   # 同一 Hub 账号（私有仓库必须；公开仓库可省略）

cd /path/to/ai-tp-deploy-bundle   # 含 compose 与 deploy/.env.docker
docker compose --env-file deploy/.env.docker pull
docker compose --env-file deploy/.env.docker up -d
# 不要加 --build，否则会要求本地有构建上下文
```

浏览器打开：`http://localhost:8088/`（或 `.env` 中 `WEB_PUBLISH_PORT`）。

### 10.4 注意

- **数据卷不会随镜像上传**：异地是新库；迁库需 `mysqldump` 或 volume 备份，不在本流程内。
- 本地开发仍可用默认 `ai-tp-api:local` / `ai-tp-web:local` + `up -d --build`。
- 其他 Compose 项目（如 `mt-edu`）按同样套路：只 push 自定义镜像，带走该项目的 compose + env。

---

## 11. 建议的后续工程化

1. CI：`docker build` 推送 `ghcr.io/<org>/ai-tp-api` / `ai-tp-worker` / `ai-tp-web`  
2. 生产叠加：`compose.prod.yml`（已提供：收紧 DB/Redis 端口、建议开启 metrics auth）  
3. 备份 Cron：`mysqldump` + `ai_tp_data` 卷归档  

Worker 工具镜像已默认启用（`target: worker-tools`）。若构建过慢，可改 `AI_TP_WORKER_TARGET=runtime` 回退为瘦镜像（工具缺失时任务仍 `skipped`）。 
