# AI-TP 阿里云 ECS Docker 部署指南

> 适用版本：v0.8 · 前置阅读：[DEPLOYMENT.DOCKER.md](./DEPLOYMENT.DOCKER.md)  
> 本指南面向**阿里云 ECS 单实例**生产/预发环境，使用 Docker Compose 一键拉起全栈。

---

## 1. 架构与资源建议

```text
Internet
   │
   ▼
┌─────────────────────────────────────────┐
│  阿里云 ECS（公网 IP / 弹性 IP）           │
│  ┌───────────────────────────────────┐  │
│  │  安全组：22 / 80 / 443（生产）       │  │
│  │  ┌─────────┐                        │  │
│  │  │  web    │ :80 ← WEB_PUBLISH_PORT │  │
│  │  │ Nginx   │                        │  │
│  │  └────┬────┘                        │  │
│  │       │ /api → api:8002              │  │
│  │  ┌────┴────┐  ┌────────┐  ┌───────┐ │  │
│  │  │  api    │  │ worker │  │ mysql │ │  │
│  │  └─────────┘  └────────┘  │ redis │ │  │
│  │                           └───────┘ │  │
│  │  Docker 网络内互通，DB/Redis 不暴露公网 │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

| 场景 | ECS 规格（最低） | 系统盘 | 说明 |
|------|------------------|--------|------|
| 内网试用 | 2 vCPU / 4 GiB | 40 GiB | worker-tools 首次构建较慢 |
| **生产推荐** | 4 vCPU / 8 GiB | 80 GiB | 含 k6 / Playwright / nuclei 的 Worker 镜像 |
| 压测密集 | 8 vCPU / 16 GiB + 独立 k6 节点 | 100 GiB+ | 见 ARCHITECTURE 分布式 k6 |

**操作系统**：Alibaba Cloud Linux 3、Ubuntu 22.04 LTS 或 Debian 12（均支持 Docker CE）。

---

## 2. 阿里云控制台准备

### 2.1 创建 ECS

1. 地域选离用户/LLM API 较近节点（如华东、华北）。
2. 分配**弹性公网 IP**（或后续绑 SLB）。
3. 登录方式：SSH 密钥对（推荐）或密码。

### 2.2 安全组规则

| 方向 | 协议 | 端口 | 授权对象 | 说明 |
|------|------|------|----------|------|
| 入 | TCP | 22 | 你的办公 IP/32 | SSH 管理，勿对 0.0.0.0/0 长期开放 |
| 入 | TCP | 80 | 0.0.0.0/0 | HTTP（可配合 SLB/证书） |
| 入 | TCP | 443 | 0.0.0.0/0 | HTTPS |
| 入 | TCP | 8088 | 0.0.0.0/0 | **仅调试期**；生产改 80/443 后删除 |

**切勿**对公网开放 `3306`（MySQL）、`6379`（Redis）。生产使用 `compose.prod.yml` 取消端口映射。

### 2.3 （可选）域名与证书

- 域名解析 A 记录 → ECS 公网 IP（或 SLB）。
- HTTPS 方案见 [第 7 节](#7-https-与域名)。

---

## 3. ECS 初始化（安装 Docker）

SSH 登录后执行（Alibaba Cloud Linux 3 / CentOS 系）：

```bash
# 更新系统
sudo yum update -y

# 安装 Docker CE（官方脚本，国内 ECS 一般可访问）
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker

# Compose 插件（Docker 24+ 通常已自带）
docker compose version

# 将部署用户加入 docker 组（免 sudo）
sudo usermod -aG docker "$USER"
# 重新登录 SSH 使组生效
```

Ubuntu 22.04：

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

**国内镜像加速（可选，加速 pull `mysql`/`redis`/`node`）：**

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://registry.cn-hangzhou.aliyuncs.com"
  ]
}
EOF
sudo systemctl restart docker
```

---

## 4. 部署方式选型

| 方式 | 适用 | 步骤概要 |
|------|------|----------|
| **A. 源码构建** | 有 Git 访问、可接受首次 build 10～30 分钟 | `git clone` → `up -d --build` |
| **B. 镜像拉取** | 已在 Docker Hub / ACR 推送镜像 | 仅拷贝 compose + env → `pull` → `up` |

镜像推送见 [DOCKER_HUB.md](./DOCKER_HUB.md)；阿里云容器镜像服务 ACR 用法与 Docker Hub 相同，只需改 `AI_TP_*_IMAGE` 为 `registry.cn-xxx.aliyuncs.com/namespace/ai-tp-api:latest`。

---

## 5. 方式 A：ECS 上源码构建（推荐首次上线）

### 5.1 获取代码

```bash
sudo mkdir -p /opt/ai-tp && sudo chown "$USER:$USER" /opt/ai-tp
cd /opt/ai-tp

# HTTPS（公开仓库）
git clone https://github.com/Jadefjg/AI-TP.git .

# 或 SSH 私有仓库
# git clone git@github.com:YOUR_ORG/ai-tp.git .
```

### 5.2 配置环境变量

```bash
cp deploy/.env.docker.example deploy/.env.docker
chmod 600 deploy/.env.docker
```

**生产必改项**（编辑 `deploy/.env.docker`）：

```bash
# 对外端口（调试可用 8088；正式建议 WEB_PUBLISH_PORT=80 并配合 compose 调整，或前置 SLB）
WEB_PUBLISH_PORT=80

# 强密码
MYSQL_ROOT_PASSWORD=<随机强密码>
MYSQL_PASSWORD=<随机强密码>
AI_CREDENTIALS_ENCRYPTION_KEY=<32字节以上随机串>
BOOTSTRAP_ADMIN_PASSWORD=<首次管理员密码，登录后立即修改>

# 公网域名（替换为你的域名）
BACKEND_CORS_ORIGINS=https://tp.example.com,http://tp.example.com
CI_WEBHOOK_PUBLIC_BASE_URL=https://tp.example.com/api
BILLING_CHECKOUT_SUCCESS_URL=https://tp.example.com/billing/success
BILLING_CHECKOUT_CANCEL_URL=https://tp.example.com/billing/cancel

# LLM（至少一项）
DEEPSEEK_API_KEY=sk-...
# 或 OPENAI_API_KEY=...

# 生产建议
SMTP_DRY_RUN=false
METRICS_AUTH_ENABLED=true
METRICS_BEARER_TOKEN=<随机串>
```

### 5.3 生产 Compose 启动

```bash
cd /opt/ai-tp

# 生产叠加：不暴露 MySQL/Redis 到宿主机
docker compose \
  -f docker-compose.yml \
  -f compose.prod.yml \
  --env-file deploy/.env.docker \
  up -d --build
```

首次 `worker-tools` 镜像构建含 k6 / Playwright / nuclei，**耗时较长**，请保持 SSH 不断开或使用 `tmux`/`screen`。

### 5.4 一键脚本（可选）

仓库提供：

```bash
chmod +x deploy/scripts/aliyun-deploy.sh
./deploy/scripts/aliyun-deploy.sh --prod
```

---

## 6. 方式 B：仅拉取镜像（无源码构建）

在**已推送镜像**的机器上，准备最小目录：

```text
/opt/ai-tp-deploy/
  docker-compose.yml
  compose.prod.yml          # 生产建议带上
  deploy/
    .env.docker
```

```bash
cd /opt/ai-tp-deploy
docker login   # Hub 或 ACR
docker compose -f docker-compose.yml -f compose.prod.yml \
  --env-file deploy/.env.docker pull
docker compose -f docker-compose.yml -f compose.prod.yml \
  --env-file deploy/.env.docker up -d
```

`.env.docker` 中镜像名示例（ACR）：

```bash
AI_TP_API_IMAGE=registry.cn-hangzhou.aliyuncs.com/myns/ai-tp-api:v0.8.0
AI_TP_WORKER_IMAGE=registry.cn-hangzhou.aliyuncs.com/myns/ai-tp-worker:v0.8.0
AI_TP_WEB_IMAGE=registry.cn-hangzhou.aliyuncs.com/myns/ai-tp-web:v0.8.0
```

---

## 7. HTTPS 与域名

Compose 内 `web` 容器默认仅 HTTP `:80`。生产 HTTPS 常见三种做法：

### 7.1 阿里云 SLB/ALB（推荐多实例）

- SLB 监听 443，挂载阿里云 SSL 证书。
- 后端指向 ECS `WEB_PUBLISH_PORT`（如 80 或 8088）。
- ECS 安全组仅允许 SLB 网段访问 80。

### 7.2 宿主机 Caddy 反代（单 ECS 简单方案）

在 ECS 安装 Caddy，自动 Let's Encrypt：

```bash
# 示例：Caddyfile
tp.example.com {
    reverse_proxy 127.0.0.1:8088
}
```

此时 Compose 保持 `WEB_PUBLISH_PORT=8088`，仅本机监听；443 由 Caddy 占用。

### 7.3 扩展 web 容器挂证书

将证书 volume 挂入 `web` 服务并扩展 `deploy/nginx/default.conf` 增加 `listen 443 ssl`。适合已有证书文件的场景。

**改域名后务必同步**：`BACKEND_CORS_ORIGINS`、Webhook/账单回跳 URL、前端构建参数（改域名需**重新 build web 镜像**，因 `VITE_*` 为构建期变量；同域 `/api` 反代则通常无需改）。

---

## 8. 验收清单

在 ECS 或本机执行：

```bash
# 容器健康
docker compose --env-file deploy/.env.docker ps

# 前端
curl -sI "http://<公网IP或域名>/" | head -3

# API 经 Nginx
curl -s "http://<公网IP或域名>/api/" 
# 期望：{"name":"AI 测试平台 API",...}

# 迁移
docker compose --env-file deploy/.env.docker exec api alembic current

# Worker 消费
docker compose --env-file deploy/.env.docker logs --tail=20 worker
```

浏览器：

- [ ] 打开登录页，使用 `BOOTSTRAP_ADMIN_*` 登录并**立即改密**
- [ ] 创建项目 → 发起 Run → 任务从 `pending` → `running` → 结束
- [ ] `/api/docs` 或经反代的 Swagger 可访问（若未屏蔽）

---

## 9. 运维

### 9.1 日常命令

```bash
cd /opt/ai-tp   # 或部署目录

docker compose -f docker-compose.yml -f compose.prod.yml \
  --env-file deploy/.env.docker logs -f api worker

docker compose -f docker-compose.yml -f compose.prod.yml \
  --env-file deploy/.env.docker up -d --scale worker=2

docker compose -f docker-compose.yml -f compose.prod.yml \
  --env-file deploy/.env.docker exec api alembic upgrade head
```

### 9.2 开机自启

Compose 已设 `restart: unless-stopped`；确保 Docker 开机启动：

```bash
sudo systemctl enable docker
```

### 9.3 备份

```bash
# MySQL
docker compose --env-file deploy/.env.docker exec mysql \
  mysqldump -u root -p"${MYSQL_ROOT_PASSWORD}" ai_tp > ai_tp_$(date +%F).sql

# 业务文件卷（报告等）
docker run --rm -v ai-tp_ai_tp_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/ai_tp_data_$(date +%F).tar.gz -C /data .
```

建议配合阿里云 OSS + 定时任务（cron）做异地备份。

### 9.4 发版

```bash
git pull   # 方式 A
docker compose -f docker-compose.yml -f compose.prod.yml \
  --env-file deploy/.env.docker up -d --build api worker web
```

方式 B：`pull` 新 tag 后 `up -d`（Worker 与 API 镜像需版本一致）。

---

## 10. 故障排查（阿里云常见）

| 现象 | 处理 |
|------|------|
| 浏览器无法访问 | 检查安全组 80/443/8088；`ss -tlnp \| grep docker` |
| build 极慢或超时 | 配置 Docker 镜像加速；Worker 构建可改用 `AI_TP_WORKER_TARGET=runtime` 先上线 |
| LLM 调用失败 | 检查 ECS 出网与 API Key；国内访问 OpenAI 需代理或改用 DeepSeek |
| 任务一直 pending | `docker compose logs worker`；确认 `REDIS_URL`、`JOB_QUEUE_BACKEND=rq` |
| 502 Bad Gateway | `docker compose logs api`；等待 MySQL healthy；必要时 `down -v` 重建（**丢数据**） |
| 磁盘满 | `docker system prune -f`；清理旧镜像；扩容云盘 |

---

## 11. 与安全基线

与 [DEPLOYMENT.md §7](./DEPLOYMENT.md#7-安全基线) 一致，阿里云额外注意：

1. 安全组最小权限；SSH 限源 IP。
2. 使用 RAM 子账号操作 OSS/ACR，勿在 ECS 长期存放主账号 AK。
3. 生产关闭 MySQL/Redis 公网映射（`compose.prod.yml`）。
4. 启用 `METRICS_AUTH_ENABLED`，勿将 `/metrics` 暴露给公网 crawlers。
5. 定期快照 ECS 系统盘 + 数据库逻辑备份。

---

## 12. 相关文档

| 文档 | 内容 |
|------|------|
| [DEPLOYMENT.md](./DEPLOYMENT.md) | 总览、环境变量、非容器路径 |
| [DEPLOYMENT.DOCKER.md](./DEPLOYMENT.DOCKER.md) | Compose 细节、故障表 |
| [DOCKER_HUB.md](./DOCKER_HUB.md) | 镜像推送与异地 pull |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 队列、Worker、k6 节点 |

**一句话：** 阿里云 ECS 装 Docker → 配置 `deploy/.env.docker` → `compose.prod.yml up -d --build` → 安全组放通 80/443 → 验收 Run 与改密。
