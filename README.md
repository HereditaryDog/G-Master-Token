# G-Master-Token

面向数字点卡、Token 充值与自动发货场景的商城系统。  
当前版本：`1.2.4`

快速导航：快速开始 • 核心能力 • 部署方式 • 环境变量 • Stripe 接入 • PostgreSQL 迁移 • 常用命令 • 路线图

## 项目简介

G-Master-Token 是一套基于 Django 的完整商城与交付系统，覆盖：

- 前台商城、商品搜索、下单与订单查询
- 用户注册登录、邮箱验证码、账号中心
- 商家后台、库存卡密、订单处理与客服工单
- Stripe Checkout + Webhook 自动确认支付
- 库存卡密 / 合作 API 两种发货模式
- PostgreSQL、Docker、Cloudflare Tunnel、Gmail SMTP

这套仓库适合用作：

- 海外支付测试站
- 数字商品自动发货站
- Token / 点卡 / 会员兑换类商城底座
- 需要快速搭建“下单 - 支付 - 发货 - 查单”闭环的测试环境

## 核心能力

### 商城与订单

- 商品展示、关键词搜索、详情页与相关商品推荐
- 登录用户快速下单，自动生成订单与支付记录
- 订单详情、支付结果页、账号中心订单管理
- 访客可通过订单号 + 邮箱查询订单

### 支付与发货

- 已接入 Stripe Checkout 跳转支付
- 已接入 Stripe Webhook：`checkout.session.completed`、`checkout.session.async_payment_succeeded`、`checkout.session.async_payment_failed`、`checkout.session.expired`
- 支持库存卡密自动发货
- 支持库存卡密按商品筛选、批量删除与低库存高亮提醒
- 支持合作 API 自动供货，路径、鉴权头和鉴权方案均可通过环境变量配置

### 用户与后台

- 普通用户登录 / 注册 / 邮箱验证码
- 独立商家登录页与商家后台
- 商家后台新增用户管理，可查看注册用户、订单数、已支付订单与累计消费，并进入用户详情页核对订单明细
- 商家后台首页已补齐可点击运营快照入口，可直接跳到分类、帮助文章、待处理工单和库存卡密
- 商品管理支持批量上架、批量下架与批量删除
- 商品删除采用软删除策略，历史订单保留不受影响
- 工单系统、订单跟进、发货重试
- Django Admin 高级后台
- 商家后台视图已按模块拆分到 `shop/views/merchant_*.py`，便于后续多人协作维护

### 当前代码结构

- `shop/views/public.py`：前台商城、查单、账号中心、支付结果与 webhook
- `shop/views/merchant_dashboard.py`：商家总览首页
- `shop/views/merchant_users.py`：用户管理与用户详情
- `shop/views/merchant_products.py`：商品管理
- `shop/views/merchant_inventory.py`：库存卡密管理
- `shop/views/merchant_orders.py`：订单管理
- `shop/views/merchant_support.py`：客服工单管理
- `shop/emails.py`：订单提醒与工单通知邮件
- `shop/services/`：支付、发货、日志、工单、订单辅助逻辑

### 安全与运维

- 登录、注册发码、订单查询等关键入口已加入验证码与限流
- 支持后台 IP 白名单、可信代理 IP 识别
- Docker + PostgreSQL 部署
- Cloudflare Tunnel 公网接入
- Gmail SMTP 邮件发送
- `/health/` 与 `/health/readiness/` 可直接用于巡检

## 快速开始

### 方式一：Docker 部署（推荐）

```bash
git clone https://github.com/HereditaryDog/G-Master-Token.git
cd G-Master-Token
cp .env.server.example .env.server
```

先编辑 `.env.server`，至少填好：

- `DJANGO_SECRET_KEY`
- `CARD_SECRET_KEY`
- `DJANGO_DEBUG=false`
- `TRUSTED_PROXY_IPS`
- `DATABASE_PASSWORD`
- `SITE_BASE_URL`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_WEBHOOK_SECRET`

然后启动：

```bash
docker compose --env-file .env.server up -d --build
docker compose --env-file .env.server exec -T web python manage.py migrate
docker compose --env-file .env.server exec -T web python manage.py seed_demo_store
```

### 方式二：本地开发

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

默认建议也使用 PostgreSQL：

```bash
python manage.py migrate
python manage.py seed_demo_store
python manage.py runserver
```

## 部署方式

### Docker Compose

项目自带 [docker-compose.yml](./docker-compose.yml)，包含：

- `web`：Django + Waitress
- `db`：PostgreSQL 17
- `cloudflared`：可选的 Cloudflare Tunnel connector
- `web_logs`：持久化 Django 应用日志，默认写入 `/app/runtime_logs/app.log`

当前运行中的网页页脚版本号会读取仓库内版本文件，因此每次发版都需要同步更新：

- `VERSION`
- `config/version.py`

启动命令：

```bash
docker compose --env-file .env.server up -d --build
```

如果使用 Cloudflare Tunnel，可在 `.env.server` 中填入：

```env
CLOUDFLARE_TUNNEL_TOKEN=
```

### 生产必须覆写

下面 4 项当前为了保留开发便利性仍有默认行为，但正式环境必须手动覆写：

- `DJANGO_SECRET_KEY`：必须换成独立随机值
- `CARD_SECRET_KEY`：必须独立配置，不要继续回退到 `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`：必须设为 `false`
- `TRUSTED_PROXY_IPS`：如果前面挂了 Cloudflare Tunnel / Nginx / 网关代理，必须填入可信代理 IP

如果遗漏这些配置，`/health/readiness/` 和 `python manage.py preflight_check` 会给出明确告警，但不会阻止本地开发启动。

### 公网访问

当前推荐使用 Cloudflare Tunnel，而不是临时端口映射或随机隧道：

- 域名固定
- 不需要直暴露本机端口
- 方便 Stripe webhook 与外部联调

## 当前发布状态

- 当前线上测试版本：`1.2.4`
- 已完成顶部导航优化、商家后台首页优化、用户管理、库存卡密管理增强、审计整改以及视图层模块化拆分

## 关键环境变量

### 站点与安全

```env
SITE_NAME=G-MasterToken
SITE_BASE_URL=https://gmtoken.shop
DJANGO_ALLOWED_HOSTS=*
DJANGO_CSRF_TRUSTED_ORIGINS=https://gmtoken.shop,https://www.gmtoken.shop
DJANGO_SECRET_KEY=
CARD_SECRET_KEY=
DJANGO_DEBUG=false
TRUSTED_PROXY_IPS=198.41.192.0/21,2400:cb00::/32
DJANGO_LOG_LEVEL=INFO
```

### 数据库

```env
DATABASE_ENGINE=postgres
DATABASE_NAME=web_store
DATABASE_USER=postgres
DATABASE_PASSWORD=
DATABASE_HOST=db
DATABASE_PORT=5432
DATABASE_CONN_MAX_AGE=60
```

### 邮件（Gmail SMTP）

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
DEFAULT_FROM_EMAIL=G-MasterToken <your@gmail.com>
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
```

### Stripe 支付

```env
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_PUBLISHABLE_KEY=pk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_CURRENCY=cny
PAYMENT_ENABLE_MOCK_GATEWAY=false
PAYMENT_ENABLE_STRIPE_GATEWAY=true
PAYMENT_ENABLE_ALIPAY_GATEWAY=false
PAYMENT_ENABLE_WECHAT_GATEWAY=false
PAYMENT_ENABLE_USDT_GATEWAY=false
PAYMENT_ENABLE_BANK_GATEWAY=false
```

### 合作供货接口

```env
PARTNER_API_BASE_URL=https://partner.example.com/api
PARTNER_API_KEY=partner-token
PARTNER_API_FULFILL_PATH=/fulfill
PARTNER_API_AUTH_HEADER=Authorization
PARTNER_API_AUTH_SCHEME=Bearer
PARTNER_TIMEOUT=20
```

## 审计整改要点

- 商家后台所有 `next` 跳转已统一校验，只允许站内安全地址，外部重定向会自动回退到默认页面
- 密码修改与重置页面不再信任 `help_text|safe`，帮助文本会强制转义
- 首页和账号中心的 GET 搜索已加 `max_length=120` 校验，超长输入只报错不执行过滤
- 库存卡密页已改为标准分页，支持 `page` 参数，并保留商品 / 状态 / 关键词筛选条件
- Docker `web` 容器已改为非 root 用户运行
- Django 应用日志已写入 `/app/runtime_logs/app.log`，并通过 `web_logs` volume 持久化

## Stripe 接入

项目当前使用 Stripe Checkout 跳转支付，Webhook 入口为：

```text
https://your-domain/webhooks/stripe/
```

建议在 Stripe 后台订阅以下事件：

- `checkout.session.completed`
- `checkout.session.async_payment_succeeded`
- `checkout.session.async_payment_failed`
- `checkout.session.expired`

配置完成后可以直接检查：

```bash
python manage.py verify_stripe_setup
python manage.py verify_stripe_setup --json
```

## PostgreSQL 迁移

如果你之前的旧环境仍在使用 SQLite，可以按下面步骤迁移到 PostgreSQL。

先导出：

```bash
python manage.py dumpdata \
  --natural-foreign \
  --natural-primary \
  --exclude contenttypes \
  --exclude auth.permission \
  > data-migration.json
```

然后把数据库环境变量改成 PostgreSQL：

```env
DATABASE_ENGINE=postgres
DATABASE_NAME=web_store
DATABASE_USER=postgres
DATABASE_PASSWORD=change-me
DATABASE_HOST=127.0.0.1
DATABASE_PORT=5432
```

再执行：

```bash
python manage.py migrate
python manage.py loaddata data-migration.json
```

## 常用命令

```bash
python manage.py check
python manage.py test accounts shop
python manage.py preflight_check
python manage.py verify_stripe_setup
docker compose --env-file .env.server up -d --build
docker compose --env-file .env.server logs -f web
docker compose --env-file .env.server exec -T web sh -lc 'tail -n 100 /app/runtime_logs/app.log'
```

## 常用入口

- 首页：`/`
- 用户登录：`/accounts/login/`
- 商家登录：`/accounts/merchant/login/`
- 商家后台：`/dashboard/`
- 订单查询：`/order-lookup/`
- 管理后台：`/admin/`
- 健康检查：`/health/`
- 就绪检查：`/health/readiness/`

## 当前发布状态

`1.1.4` 版本已经完成以下关键链路：

- Stripe 测试支付已接通
- Webhook 回调地址已固定为公网 HTTPS 域名
- 模拟支付已关闭，测试站默认只走 Stripe
- Gmail SMTP 已接通
- Docker + PostgreSQL + Cloudflare Tunnel 已跑通
- 支付配置、供货配置、数据库配置均已环境变量化
- 商家后台已支持用户管理，可查看注册用户、订单统计、累计消费与用户详情订单明细
- 商家后台首页已支持运营快照快捷跳转，导航栏布局也已收紧并整理为右侧整排按钮
- 商家后台商品管理已支持批量上架、批量下架与软删除
- 库存卡密页已支持库存概览、按商品筛选、标准分页和批量删除可售卡密
- 商家后台危险跳转参数已收口为站内安全跳转
- Docker 默认以非 root 运行，并持久化应用日志
- readiness / preflight 对 `DJANGO_SECRET_KEY`、`CARD_SECRET_KEY`、`DEBUG` 风险提示更明确

## 路线图

- 接入支付宝 / 微信支付 / USDT / 银行转账
- 完成商家 2FA
- 接入正式合作供货 API
- 补充更细的运维监控和告警
- 拆分更完整的管理员与商家权限层

## 更新日志

完整发布记录见 [CHANGELOG.md](./CHANGELOG.md)。
