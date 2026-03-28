# G-MasterToken

数字点卡与 Token 充值站点。  
当前包含前台商城、用户系统、订单查询、商家后台、自动发货、Stripe 支付链路和基础安全加固。

当前版本：`0.1.10`

## 快速启动

```bash
python -m venv .venv
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo_store
python manage.py runserver
```

Windows 也可以直接用：

```powershell
.\Start-WebStore.ps1
```

## Docker

```powershell
docker compose --env-file .env.server up -d --build
```

## 关键配置

最少关注这些：

```env
SITE_NAME=G-MasterToken
SITE_BASE_URL=
CARD_SECRET_KEY=
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_CURRENCY=cny
```

Stripe 配置检查：

```bash
python manage.py verify_stripe_setup
```

## 常用入口

- 首页：`/`
- 用户登录：`/accounts/login/`
- 商家登录：`/accounts/merchant/login/`
- 商家后台：`/dashboard/`
- 订单查询：`/order-lookup/`
- 就绪检查：`/health/readiness/`

## 当前状态

- 前后台主流程可跑
- Docker 可跑
- Stripe Checkout / webhook 主链路已接入
- 登录、发码、查单已加服务端验证码与限流
- 商家 2FA 预留，尚未完成
- 真实供应 API 尚未正式接入

## 验证

```bash
python manage.py check
python manage.py test accounts shop
```

更多变更见 [CHANGELOG.md](CHANGELOG.md)。
