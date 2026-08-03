# AI-TP：推送到 Docker Hub 并在其他电脑运行

> 配套：[`docker-compose.yml`](../docker-compose.yml)、[`deploy/scripts/push-images.sh`](../deploy/scripts/push-images.sh)、[`deploy/.env.docker.example`](../deploy/.env.docker.example)  
> 完整容器部署见 [DEPLOYMENT.DOCKER.md](./DEPLOYMENT.DOCKER.md)

---

## 1. 先看清：Compose 项目 ≠ 一个镜像

Docker Desktop 里名为 **`ai-tp`**（左侧有 `>`、ID/Image/Port 为 `-`）的是 **Compose 项目组**，不是单个可上传的镜像。

| 服务 | 镜像来源 | 是否需要推到 Docker Hub |
|------|----------|-------------------------|
| mysql | 官方 `mysql:8.4` | 否（异地自动 pull） |
| redis | 官方 `redis:7-alpine` | 否 |
| api / worker | 本仓库构建（同一镜像，worker 换启动命令） | **是** |
| web | 本仓库构建 | **是** |

正确做法：**推送 2 个自定义镜像** + 带走 `docker-compose.yml` 与 `deploy/.env.docker`。  
数据卷（数据库、报告文件）**不会**随镜像上传，异地是新库。

```text
本机 build → docker push → Docker Hub
其他电脑 docker login → compose pull → compose up -d → 浏览器访问
```

---

## 2. 前置条件

- 本机已安装 Docker Engine / Docker Desktop（含 Compose v2）
- 已注册 [Docker Hub](https://hub.docker.com) 账号（下文用 `youruser` 代替你的用户名）
- 本机在项目根目录：`/path/to/ai-tp`

---

## 3. 本机：登录 Docker Hub

```bash
docker login
# 按提示输入 Hub 用户名与密码（或 Access Token）
```

---

## 4. 本机：配置镜像名与密钥

```bash
cd /path/to/ai-tp
cp -n deploy/.env.docker.example deploy/.env.docker
```

编辑 `deploy/.env.docker`，至少设置：

```bash
# 推到 Hub 的镜像名（必改）
AI_TP_API_IMAGE=youruser/ai-tp-api:latest
AI_TP_WEB_IMAGE=youruser/ai-tp-web:latest

# 密钥（生产务必改掉示例值）
MYSQL_ROOT_PASSWORD=...
MYSQL_PASSWORD=...
AI_CREDENTIALS_ENCRYPTION_KEY=...
BOOTSTRAP_ADMIN_PASSWORD=...
# 建议配置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY
```

**切勿**把含真实密钥的 `deploy/.env.docker` 提交到公开 Git。

---

## 5. 本机：构建并推送镜像

### 方式 A（推荐）：脚本一键推送

```bash
chmod +x deploy/scripts/push-images.sh
./deploy/scripts/push-images.sh youruser
# 指定版本标签：
# ./deploy/scripts/push-images.sh youruser v0.8.0
```

脚本会：

1. 用 Compose 构建 `api` / `worker` / `web`
2. `docker push` 上述两个镜像名到 Hub

### 方式 B：手动命令

```bash
docker build -f deploy/Dockerfile -t youruser/ai-tp-api:latest .
docker build -f deploy/Dockerfile.web -t youruser/ai-tp-web:latest .
docker push youruser/ai-tp-api:latest
docker push youruser/ai-tp-web:latest
```

推送成功后，在 Hub 网页应能看到仓库：

- `youruser/ai-tp-api`
- `youruser/ai-tp-web`

（默认可能是 **Private**；若要别人免登录拉取，在 Hub 仓库设置里改为 Public。）

---

## 6. 准备「异地运行包」

拷到另一台电脑（U 盘 / 网盘 / 私有 Git 均可），至少包含：

| 文件 | 说明 |
|------|------|
| `docker-compose.yml` | 编排定义 |
| `deploy/.env.docker` | 镜像名 + 密钥（与本机推送时一致的 `AI_TP_*_IMAGE`） |

**不需要**完整源码即可 `pull` + `up`。  
若目标机还要用 `up --build`，则需要完整仓库。

建议目录结构示例：

```text
ai-tp-deploy/
  docker-compose.yml
  deploy/
    .env.docker
```

---

## 7. 其他电脑：拉取并运行

```bash
# 1) 安装 Docker Desktop / Engine + Compose v2
# 2) 登录（公开仓库可省略；私有仓库必须）
docker login

# 3) 进入异地运行包目录
cd /path/to/ai-tp-deploy

# 4) 拉取镜像并启动（不要加 --build）
docker compose --env-file deploy/.env.docker pull
docker compose --env-file deploy/.env.docker up -d
```

验证：

```bash
curl -sI http://127.0.0.1:8080/ | head -5
curl -s http://127.0.0.1:8080/api/ | head -c 200; echo
```

浏览器打开：**http://localhost:8080/**  
（端口以 `.env.docker` 里 `WEB_PUBLISH_PORT` 为准。）

常用运维：

```bash
docker compose --env-file deploy/.env.docker logs -f api worker web
docker compose --env-file deploy/.env.docker ps
docker compose --env-file deploy/.env.docker down          # 停服务，保留数据卷
docker compose --env-file deploy/.env.docker down -v       # 危险：清数据
```

---

## 8. 常见问题

| 现象 | 处理 |
|------|------|
| `pull` 报 `denied` / `unauthorized` | 执行 `docker login`；确认 Hub 仓库名与 `AI_TP_*_IMAGE` 一致；私有仓需有权限 |
| `up` 时仍尝试 build 且失败 | 不要加 `--build`；确认 `.env.docker` 里已是 Hub 镜像名而非 `*:local` |
| 镜像拉下来但 web 502 | `docker compose logs api`；等健康检查通过；检查 MySQL 密码是否与 compose 一致 |
| 登录页能开但 AI 不可用 | 在 `.env.docker` 配置 LLM Key 后 `up -d` 重建 api/worker |
| 想迁本机数据库 | 镜像推送不含数据；另做 `mysqldump` 或 volume 备份，本指南不覆盖 |

---

## 9. 其他 Compose 项目（如 mt-edu）

套路相同，在**该项目自己的目录**操作：

1. 展开 Compose，区分官方镜像 vs `build:` 自定义镜像  
2. 只 `docker build` + `docker push` 自定义镜像  
3. 带走该项目的 `docker-compose.yml` + env，在另一台 `pull` + `up`

---

## 10. 命令速查

```bash
# --- 本机 ---
docker login
# 编辑 deploy/.env.docker 中 AI_TP_API_IMAGE / AI_TP_WEB_IMAGE
./deploy/scripts/push-images.sh youruser

# --- 其他电脑 ---
docker login
docker compose --env-file deploy/.env.docker pull
docker compose --env-file deploy/.env.docker up -d
```
