# Deployment Guide

## 目标

把这台本地 Windows 电脑作为测试服务器，满足：

- 同事可通过公网访问网站
- 项目运行在 Docker 容器中
- 每 30 分钟自动检查 GitHub 是否更新
- 如果仓库有新提交，自动拉取并重新部署

## 方案

当前建议优先使用：

- `Windows 服务模式`：立即可用，不依赖 Docker 虚拟化

保留的后续方案：

- `Docker + PostgreSQL + Cloudflare Tunnel`

### 1. Windows 服务模式

使用：

- `Waitress`
- `NSSM`
- Windows Scheduled Task

已完成：

- 应用服务脚本
- 自动拉取更新脚本
- 每 30 分钟同步任务

### 2. 容器运行

使用 `docker-compose.yml` 启动：

- `web`：Django + Waitress
- `db`：PostgreSQL 17
- `cloudflared`：可选公网隧道

### 3. 自动更新

自动更新脚本：

- [sync-and-redeploy.ps1](C:\Users\Administrator\Desktop\web_test\scripts\sync-and-redeploy.ps1)

逻辑：

1. 检查工作区是否干净
2. `git fetch origin main`
3. 如果远程有新提交：
4. `git pull --ff-only origin main`
5. 如果有 Docker，则重建容器
6. 如果没有 Docker，则重启本地 Windows 服务

### 4. 定时任务

每 30 分钟自动执行：

- [register-sync-task.ps1](C:\Users\Administrator\Desktop\web_test\scripts\register-sync-task.ps1)

开机自动启动整套服务：

- [register-startup-task.ps1](C:\Users\Administrator\Desktop\web_test\scripts\register-startup-task.ps1)

### 5. 公网访问

推荐使用 `Cloudflare Tunnel`。

原因：

- 不需要直接把本机端口暴露到公网
- 域名固定，适合同事反复访问测试
- 比家庭宽带端口映射稳定

相关说明：

- [cloudflared/README.md](C:\Users\Administrator\Desktop\web_test\cloudflared\README.md)

## 本机部署步骤

### 1. 准备服务器环境文件

```powershell
copy .env.server.example .env.server
```

然后填好这些关键项：

- `DJANGO_SECRET_KEY`
- `CARD_SECRET_KEY`
- `DATABASE_ENGINE=postgres`
- `DATABASE_NAME`
- `DATABASE_USER`
- `DATABASE_PASSWORD`
- `DATABASE_HOST`
- `DATABASE_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `SITE_BASE_URL`
- `PAYMENT_ENABLE_MOCK_GATEWAY`
- `PAYMENT_ENABLE_STRIPE_GATEWAY`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `PARTNER_API_BASE_URL`
- `PARTNER_API_KEY`
- `PARTNER_API_FULFILL_PATH`
- `PARTNER_API_AUTH_HEADER`
- `PARTNER_API_AUTH_SCHEME`
- `CLOUDFLARE_TUNNEL_TOKEN`（如果要公网访问）

### 2. 启动本地服务

```powershell
.\scripts\install-web-service.ps1
```

### 3. 注册自动更新任务

```powershell
.\scripts\register-sync-task.ps1
```

### 4. 可选：切换到 Docker

如果后面 BIOS 开启了虚拟化，并安装了 Docker Desktop：

```powershell
.\scripts\start-server-stack.ps1
```

### 5. 可选：安装公网 Tunnel 服务

```powershell
.\scripts\install-cloudflared-service.ps1 -TunnelToken "your-token"
```

### 6. 旧版 Docker 启动方式

```powershell
.\scripts\start-server-stack.ps1
```

## 当前已完成

- Waitress Windows 服务模式
- 每 30 分钟自动同步脚本
- Windows 定时任务注册脚本
- Dockerfile
- docker-compose.yml
- PostgreSQL 容器配置
- Cloudflare Tunnel profile 骨架

## 当前仍需手动完成

- 提供 Cloudflare Tunnel Token（如果要稳定公网访问）
- 准备固定测试域名（推荐 Cloudflare）
- 如果要切 Docker，再开启 BIOS 虚拟化并安装 Docker Desktop
- 如果要切 Docker，再准备 `.env.server`
- 准备 Cloudflare Tunnel Token
