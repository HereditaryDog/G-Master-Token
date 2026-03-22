# Changelog

本文件记录项目的可见版本变更。

## 0.0.3 - 2026-03-23

### Added

- 登录页验证码点击刷新
- 注册页邮箱验证码发送倒计时
- 客服与售后支持页面

### Changed

- 登录与注册交互体验进一步优化
- 站点导航新增客服支持入口

### Verified

- `manage.py check`
- `manage.py test accounts shop`

## 0.0.2 - 2026-03-23

### Added

- 邮箱验证码注册流程
- 用户名或邮箱登录支持
- 登录页人机验证码
- Gmail SMTP 发信支持
- 多支付网关抽象
- 支付宝、微信支付、USDT、银行卡转账的预留支付接口

### Changed

- 首页视觉重构，整体风格更接近苹果官网方向
- 认证链路升级为更完整的注册 / 登录 / 邮箱验证方案
- 结算页升级为多支付通道展示结构
- README 重写为正式项目首页风格

### Verified

- `manage.py check`
- `manage.py test accounts shop`

## 0.0.1 - 2026-03-23

### Added

- Django 商城项目初始化
- 商品、订单、库存卡密、支付记录、发货记录模型
- 前台首页、商品详情、订单页、帮助中心、公告、订单查询
- 商家后台与 Django Admin 管理能力
- SQLite / PostgreSQL 配置支持
- Windows 启动脚本
- 初始自动化测试
