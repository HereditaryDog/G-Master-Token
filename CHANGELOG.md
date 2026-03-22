# Changelog

All notable changes to this project will be documented in this file.

## 0.0.2 - 2026-03-23

- Refined the storefront visual direction toward a cleaner Apple-inspired landing page.
- Added multi-gateway payment architecture with reserved interfaces for Alipay, WeChat Pay, USDT, and bank transfer.
- Reworked account registration to require username, email, phone number, password, and email verification code.
- Reworked login to support username or email plus password and human-verification captcha.
- Added email verification code model, sending utilities, custom auth backend, and admin visibility for verification records.
- Switched local email delivery from console output to Gmail SMTP for real verification email delivery.
- Expanded automated tests for registration, login, captcha, payment gateway exposure, and help center behavior.

## 0.0.1 - 2026-03-23

- Initialized the `web_0.0.1` Django storefront workspace.
- Added buyer registration, login, product catalog, checkout flow, and order pages.
- Added merchant dashboard pages for product, inventory, and order management.
- Added card-code inventory, payment attempts, delivery records, and partner API abstraction.
- Added public order lookup, announcements, help center, and help article pages.
- Added a multi-gateway payment abstraction with reserved interfaces for Alipay, WeChat Pay, USDT, and bank transfer.
- Added SQLite/PostgreSQL environment-based configuration and Windows startup scripts.
- Added demo seed data, automated tests, and initial GitHub repository publishing support.
