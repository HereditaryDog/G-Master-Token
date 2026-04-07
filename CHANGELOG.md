# Changelog

本文件记录项目的可见版本变更。

## 1.2.4 - 2026-04-08

### Added

- 新增 `shop/emails.py`、`shop/services/audit.py`、`shop/services/order_helpers.py`、`shop/services/support.py`，把邮件通知、敏感操作日志、订单辅助判断和工单消息写入从视图层中抽离
- 新增 `shop/views/` 包结构，按商家后台职责拆分为 `merchant_dashboard.py`、`merchant_users.py`、`merchant_products.py`、`merchant_inventory.py`、`merchant_orders.py`、`merchant_support.py`

### Changed

- 仓库发布版本提升为 `1.2.4`
- 原单文件 `shop/views.py` 升级为模块化 package，并保留 `from shop.views import ...` 的兼容导出，避免影响现有 URL 与测试 patch 路径
- 商家后台用户管理、库存、订单、工单视图已经按模块收口，更适合团队并行协作和后续继续拆分
- README 同步补充当前视图层组织方式与代码结构说明

### Fixed

- 修复视图层职责混杂导致的单文件膨胀问题，降低商家后台相关改动的冲突概率
- 修复邮件通知、日志记录、工单消息与视图 HTTP 编排耦合过深的问题

### Verified

- `docker compose --env-file .env.server run --rm web python manage.py check`
- `docker compose --env-file .env.server run --rm web python manage.py test shop.tests.StoreOrderFlowTests shop.tests.MerchantOperationsTests shop.tests.SupportSystemTests`
- `http://127.0.0.1:8000/health/`
- `https://gmtoken.shop/health/`

## 1.1.4 - 2026-04-07

### Added

- 商家后台首页的“运营快照”四张卡片新增实际跳转，可直接进入分类管理、帮助文章、待处理工单和库存卡密页面

### Changed

- 仓库发布版本提升为 `1.1.4`
- 顶部站点导航重新排版为“左侧品牌信息、右侧整排导航按钮”，避免登录态按钮被页面宽度挤压换行
- 顶部导航栏整体压薄，缩小上下留白，保留原有按钮样式和相对位置
- 商家后台首页 Hero 区块压缩高度，并把 `新增商品 / 导入卡密 / 高级后台` 三个快捷按钮下移到底部操作区
- README 同步补充本次后台首页与导航栏优化说明

### Fixed

- 修复顶部导航在部分宽度下按钮被挤压错位、`退出` 按钮掉到下一行的问题
- 修复商家后台首页 Hero 区块过厚、快捷按钮位置不稳的问题

### Verified

- `docker compose --env-file .env.server exec -T web python manage.py check`
- `https://gmtoken.shop/health/`
- 首页导航与商家后台首页模板渲染检查通过

## 1.1.3 - 2026-04-06

### Added

- 商家后台新增“用户管理”入口，可查看当前注册用户、邮箱/手机号、订单数、已支付订单数和累计消费
- 新增用户详情页，可直接查看单个用户的订单列表、最近下单时间和消费汇总
- 为商家后台补充用户管理专项测试，覆盖列表统计与详情页订单展示

### Changed

- 仓库发布版本提升为 `1.1.3`
- README 同步补充用户管理能力说明与当前发布状态
- 商家后台侧边栏从“商品 / 库存 / 订单”扩展为“用户 / 商品 / 库存 / 订单”统一运营视图

### Verified

- `docker compose --env-file .env.server run --rm web python manage.py test shop.tests.MerchantOperationsTests`
- `docker compose --env-file .env.server run --rm web python manage.py check`
- `http://127.0.0.1:8000/health/`
- `https://gmtoken.shop/health/`

## 1.1.2 - 2026-04-05

### Added

- 新增统一安全跳转辅助逻辑，商家后台商品、库存、订单操作中的 `next` 参数统一改为站内安全校验
- 新增库存卡密标准分页，`/dashboard/inventory/` 现支持 `page` 查询参数并保留现有筛选条件
- 新增 Django 文件日志输出，默认写入 `/app/runtime_logs/app.log`

### Changed

- 仓库发布版本提升为 `1.1.2`
- 保留 `DJANGO_SECRET_KEY`、`CARD_SECRET_KEY` 回退和 `DEBUG` 默认值的开发便利，但 readiness / preflight 现在会明确提示生产风险
- 首页与账号中心的搜索改为 GET Form 校验，`q` 超过 120 字符只报错不执行过滤
- Docker `web` 容器改为非 root 用户 `appuser` 运行
- 示例环境文件、README 和 DEPLOYMENT 文档补充了 `TRUSTED_PROXY_IPS`、日志持久化和生产必须覆写项说明

### Fixed

- 修复商家后台多个批量操作接口可接受外部 `next` 地址，存在开放重定向风险的问题
- 修复密码修改和密码重置模板仍对 `help_text` 使用 `|safe` 的输出风险
- 修复库存卡密页只截取最近记录、无法做标准分页浏览的问题

### Verified

- `docker compose --env-file .env.server run --rm web python manage.py test accounts.tests.AccountAuthFlowTests shop.tests.StoreOrderFlowTests shop.tests.MerchantOperationsTests shop.tests.AccountCenterEnhancementTests shop.tests.ReadinessChecksTests`
- `docker compose --env-file .env.server run --rm web python manage.py check`
- `docker compose --env-file .env.server build web`
- `docker compose --env-file .env.server exec -T web id -u`
- `https://gmtoken.shop/health/`
- `https://gmtoken.shop/health/readiness/`

## 1.0.2 - 2026-04-05

### Added

- 库存卡密页新增商品级库存概览，可直接查看每个库存商品的可售、已售和总量
- 库存卡密页新增按商品、状态、关键词筛选能力，并支持单条或批量删除可售卡密

### Changed

- 仓库发布版本提升为 `1.0.2`
- 库存卡密页重构为导入区、库存概览区、卡密管理区三段式布局
- 商品库存概览卡片重做为更醒目的指标卡样式，低库存商品增加高亮警示和补货提示
- 库存导入与库存筛选统一只展示“库存卡密”类型商品，避免与 API 商品混用

### Fixed

- 修复库存卡密页只能查看最近记录、无法按商品做日常库存管理的问题
- 修复已售卡密与可售卡密缺少明确区分、容易误删的问题

### Verified

- `docker compose --env-file .env.server exec -T web python manage.py test shop.tests.MerchantOperationsTests.test_inventory_preview_and_import_history shop.tests.MerchantOperationsTests.test_inventory_page_masks_plaintext_codes shop.tests.MerchantOperationsTests.test_inventory_page_filters_card_codes_by_product_and_status shop.tests.MerchantOperationsTests.test_inventory_batch_delete_only_removes_available_codes shop.tests.MerchantOperationsTests.test_inventory_code_reveal_returns_plaintext_and_logs`
- `docker compose --env-file .env.server exec -T web python manage.py check`
- `https://gmtoken.shop/health/`

## 1.0.1 - 2026-04-05

### Added

- 商家后台商品管理页新增批量操作，支持批量上架、批量下架与批量删除
- 商品模型新增软删除标记，删除后的商品会自动从前台与商家列表隐藏

### Changed

- 仓库发布版本提升为 `1.0.1`
- 商品删除策略从物理删除调整为软删除，历史订单引用的商品也可以安全执行删除操作
- 商品选择器、商品详情、首页商品列表与商家商品列表统一过滤已删除商品

### Fixed

- 修复商家后台批量删除商品时，已被订单引用的商品因数据库保护关系无法删除的问题
- 修复库存卡密导入等后台表单仍可选中已删除商品的问题

### Verified

- `docker compose --env-file .env.server exec -T web python manage.py test shop.tests.MerchantOperationsTests.test_batch_product_status_actions_can_activate_and_deactivate_selected_products shop.tests.MerchantOperationsTests.test_batch_product_delete_skips_products_referenced_by_orders`
- `docker compose --env-file .env.server exec -T web python manage.py showmigrations shop`
- `https://gmtoken.shop/health/`

## 1.0.0 - 2026-04-05

### Added

- 新增 Gmail SMTP 发信配置，注册验证码与系统邮件可切到真实邮箱投递
- 新增 Cloudflare Tunnel 正式公网接入流程，测试域名与 Stripe webhook 可稳定联通
- 新增合作供货接口环境变量：`PARTNER_API_FULFILL_PATH`、`PARTNER_API_AUTH_HEADER`、`PARTNER_API_AUTH_SCHEME`
- 新增 mock 支付关闭状态下的直链保护与对应回归测试

### Changed

- 仓库发布版本正式提升为 `1.0.0`
- README 全量重写为正式发布文档风格，统一收口快速开始、部署、环境变量、Stripe 接入与 PostgreSQL 迁移说明
- 默认部署配置统一切换到 PostgreSQL 方案，示例环境文件同步更新
- 测试站支付通道正式切换为仅 Stripe，关闭模拟支付
- 首页品牌资源、favicon、页头页脚品牌展示完成统一

### Fixed

- 修复测试环境邮箱验证码提示与实际投递能力不一致的问题
- 修复 Cloudflare Tunnel 双 connector 并存导致公网访问间歇性 `502` 的问题
- 修复 mock 支付在禁用后仍可通过旧直链访问的问题
- 修复合作供货接口路径与鉴权方式写死在代码中的问题

### Verified

- `python manage.py check`
- `python manage.py verify_stripe_setup --json`
- `python manage.py test shop.tests.SupplierServiceTests shop.tests.ReadinessChecksTests`
- `python manage.py test shop.tests.StoreOrderFlowTests.test_mock_payment_route_returns_404_when_gateway_disabled shop.tests.StoreOrderFlowTests.test_mock_payment_completes_order_and_delivers_code`
- `https://gmtoken.shop/health/`

## 0.1.11 - 2026-03-29

### Changed

- 账号中心里的待支付订单新增“继续支付”入口，避免用户只能重新下单
- 注册页手机号改为真正格式校验，支持清洗 `+86`、空格和横杠后再校验

### Fixed

- 修复待支付订单在“我的订单”列表里缺少继续支付入口的问题
- 修复注册手机号可被任意乱填的问题

### Verified

- `manage.py test accounts.tests.AccountAuthFlowTests shop.tests.AccountCenterEnhancementTests`

## 0.1.10 - 2026-03-29

### Added

- 登录验证码改为服务端生成并校验的 SVG 图形验证码，前端不再直接拿到明文答案
- 新增通用安全限流模型 `SecurityThrottle` 与账号/IP 双维度频控服务

### Changed

- 登录、商家登录、注册发码、订单查询的频控策略统一收口到账号安全层
- 站点公告改写为当前开发阶段更贴近真实状态的内容，并自动停用旧公告残留

### Fixed

- 修复登录验证码以 JSON 明文返回导致前端可直接获知答案的问题
- 修复查单接口错误提示可枚举订单条件的问题
- 修复商家登录和普通登录可以通过切换用户名/邮箱绕过部分账号限流的问题

### Verified

- `manage.py check`
- `manage.py test accounts shop`
- `http://127.0.0.1:8000/accounts/login/captcha/`
- `http://127.0.0.1:8001/accounts/login/captcha/`

## 0.1.9 - 2026-03-27

### Added

- 新增 `verify_stripe_setup` 管理命令，可直接检查 Stripe key、webhook 地址与 API 连通性
- 新增订单详情页支付参考号展示与复制入口，便于排查真实支付记录

### Changed

- 全站项目名称统一调整为 `G-MasterToken`
- Stripe readiness 检查补充公网 HTTPS 回调地址校验
- 订单详情页与商家订单详情页把“支付流水”统一改名为更准确的“支付参考号 / Stripe 会话编号”

### Fixed

- 修复真实 Stripe Checkout 跳转链接过长时 `checkout_url` 字段落库失败的问题
- 修复长串 Stripe 会话编号在订单详情页里挤坏布局的问题

### Verified

- `manage.py check`
- `manage.py test`

## 0.1.8 - 2026-03-27

### Changed

- 首页 Hero 的快捷操作区重做为独立控件组，按钮与搜索框尺寸重新统一
- 首页 Hero 在移动端改为专用响应式布局，不再复用通用按钮区样式

### Fixed

- 修复首页 Hero 操作按钮和搜索区比例失衡、难以稳定微调的问题
- 修复登录页测试把站点名称写死，导致切换 `SITE_NAME` 后出现误报失败的问题
- 修复本地 Playwright 审查产物混入发布工作区的问题

### Verified

- `manage.py check`
- `manage.py test`

## 0.1.7 - 2026-03-26

### Changed

- 重新核对并对齐本地项目与当前工作树，确认两边代码状态一致

### Fixed

- 修复首页删除分类导航后仍残留隐形分类筛选的问题
- 修复首页 Hero 标题样式覆盖范围过宽，误伤订单详情页与结算页标题布局的问题

### Verified

- `manage.py check`
- 本地项目与当前工作树 diff 为零
- 本地 `main` 与 `origin/main` 差异计数为 `0 0`

## 0.1.6 - 2026-03-26

### Changed

- 首页进一步收敛到“品牌 Hero + 商品区 + 公告区”的主路径，彻底移除分类快捷浏览遗留交互
- 订单详情页与结算页头部改为专用布局，长订单号不再与状态和操作按钮互相挤压

### Fixed

- 修复首页已删除分类浏览区后，隐藏 `category` 参数仍会继续筛选商品的问题
- 修复首页 Hero 的标题调优通过全局 `.content-card h1` 扩散，导致订单页和结算页标题异常放大、布局错位的问题
- 修复订单详情页与结算页长订单号挤压状态区的问题

### Verified

- `manage.py check`
- `manage.py test shop.tests.StoreOrderFlowTests`

## 0.1.5 - 2026-03-25

### Added

- 演示商品新增 200 美元与 300 美元高价位套餐，方便继续做大额支付与验收展示

### Changed

- 首页结构继续收敛，移除了分类快捷浏览与热门帮助文章等冗余区块
- 首页 Hero、商品卡浮层、页眉吸顶和公告区位置继续按当前确认稿微调
- UI 调试面板关闭，并把已确认的页面宽度、字距、浮层宽度和圆角等参数固化到正式样式

### Fixed

- 修复首页样式在关闭 UI 调试后仍会回弹到旧取值的问题
- 修复商品卡顶部信息层与角标显示不稳定、可读性差的问题

### Verified

- `manage.py check`

## 0.1.4 - 2026-03-25

### Added

- 新增独立的商家登录页 `/accounts/merchant/login/`，商家后台匿名访问会直接跳转到商家登录
- 新增 Stripe 真实支付第一阶段支持，包括更完整的 Checkout 元数据、回调地址、失败/过期 webhook 处理与支付状态同步
- 新增商家登录、Stripe Checkout 创建参数、Stripe webhook 失败分支与就绪检查的回归测试

### Changed

- 普通用户登录页与商家登录页正式拆分，商家账号不再与普通用户账号共用同一个登录入口
- 结算页文案改为真实 Stripe Checkout 导向，配置完成后可直接进入真实支付页面
- 就绪检查新增 Stripe 关键配置校验，要求关注 `SITE_BASE_URL` 与 `STRIPE_WEBHOOK_SECRET`

### Fixed

- 修复商家账号仍可从普通用户登录页尝试登录的问题
- 修复 Stripe Checkout 仅处理成功场景、未覆盖失败/过期 webhook 的问题
- 修复支付创建、支付成功、支付失败三种状态在 `PaymentAttempt` 中不同步的问题

### Verified

- `manage.py check`
- `manage.py test`

## 0.1.3 - 2026-03-25

### Added

- 新增仅在本地 `DEBUG` 模式显示的 UI 调试面板，可实时调节页面宽度、字间距、标题比例、商品浮层宽度和圆角
- 页脚升级为多列导航结构，补齐快速导航、帮助支持和商家入口

### Changed

- 全站品牌名称统一切换为 `G-MasterToken`
- 首页 Hero 重构为更简洁的品牌展示形式，移除多余说明区块和帮助文章区块
- 商品卡图片浮层改回更直观的磨砂卡片样式，并收敛顶部叠字，只保留下方信息层
- 首页、商品详情、商家总览、账号中心的排版、字距、字体和视觉层次继续优化

### Fixed

- 修复商品卡图片顶部标签在亮色图片上可读性差的问题
- 修复首页测试仍依赖已移除帮助文章区块导致的断言失败

### Verified

- `manage.py check`
- `manage.py test`

## 0.1.2 - 2026-03-24

### Added

- 商家后台新增“重试自动发货”操作，适用于已支付但自动发货失败的订单
- 新增失败订单补库存后恢复完成、未支付订单禁止重试等回归测试

### Changed

- 订单发货逻辑支持对已支付订单进行二次自动发货尝试
- 用户订单详情页和商家订单页补充了“支付已确认但待处理”的状态提示

### Verified

- `manage.py check`
- `manage.py test`

## 0.1.1 - 2026-03-24

### Added

- 新增支付成功页、商家明文查看接口、匿名 `mock-pay`、下架商品详情页等关键回归测试
- 新增 `TRUSTED_PROXY_IPS` 配置项，仅在受信代理场景下解析转发 IP

### Changed

- 支付确认流程改为先落库“已支付”，再单独执行自动发货，避免发货异常把订单回滚成未支付
- 商家权限判断和请求来源 IP 判断提取为统一安全工具函数，减少边界分叉
- WhiteNoise 增加 finder 支持，测试与非 collectstatic 场景下也能正确提供静态资源

### Fixed

- 修复匿名访问 `mock-pay` 页面会直接触发 500，而不是跳转登录的问题
- 修复支付成功页未校验 Stripe 会话归属，可能被其他已支付 `session_id` 串单的问题
- 修复后台 IP 白名单无条件信任 `X-Forwarded-For`，导致可伪造来源地址绕过限制的问题
- 修复商家可绕过 `/dashboard/` 白名单，直接通过发货明文查看接口取码的问题
- 修复库存不足等发货失败场景下，真实已支付订单被错误回滚为未支付的问题
- 修复下架商品详情页仍可通过直链访问的问题
- 修复生产模式静态资源测试返回 `404` 的问题

### Verified

- `manage.py check`
- `manage.py test`

## 0.0.10 - 2026-03-24

### Added

- 新增 `check-server-health.ps1`，每次巡检会检查 Windows 服务、Docker 栈和公网隧道健康状态
- 新增 `start-quick-tunnel.ps1`，可自动拉起并恢复 Cloudflare Quick Tunnel
- 新增 `register-health-task.ps1`，用于注册每 30 分钟一次的健康检查任务
- 新增人民币/美元格式化模板过滤器，统一前后台金额展示

### Changed

- 商品目录统一为“人民币售价 + 美元充值面值”的展示与命名方式
- 支付测试商品调整为 1 / 5 / 10 / 30 / 50 / 100 美元充值卡和多档套餐
- 启动脚本现在会在启动应用后顺手拉起公网 Quick Tunnel

### Fixed

- 修复 Docker + Waitress 模式下静态资源无法正常加载的问题
- 修复本地 `SITE_BASE_URL` 干扰邮件测试断言的问题

### Verified

- `manage.py check`
- `manage.py test accounts shop`
- `http://127.0.0.1:8000/health/readiness/`
- `http://127.0.0.1:8001/health/readiness/`
- 当前公网 Quick Tunnel 可访问

## 0.0.9 - 2026-03-24

### Added

- 上线预检命令 `preflight_check`
- `/health/readiness/` 就绪检查接口
- Docker / Compose 部署骨架
- 本地服务器模式下的 Waitress Windows 服务脚本
- GitHub 自动拉取并重启部署脚本
- Cloudflare Tunnel 服务配置骨架

### Changed

- 本机运行环境补齐并同步到最新数据库迁移
- 本地服务改为可长期运行的 Windows 服务模式

### Verified

- `manage.py check`
- `manage.py test accounts shop`
- 本地首页与就绪接口访问正常

## 0.0.8 - 2026-03-24

### Changed

- 商品管理页拆分为独立标题卡和筛选卡，避免筛选表单与新增按钮错位拥挤
- 商品管理页筛选区按钮布局重排，中等宽度下操作区更稳定
- 全站字体栈、标题字重、按钮字重与导航排版继续微调，整体可读性提升

### Fixed

- 修复商品管理页顶部工具区被 `hero-actions` 通用布局拉伸后导致按钮异常放大的问题
- 修复商品管理页标题区与筛选区混排时的对齐问题

### Verified

- `manage.py check`
- `manage.py test`

## 0.0.7 - 2026-03-23

### Added

- 新增客服工单系统，支持用户提交工单、查看回复、商家后台处理工单
- 商家后台新增客服工单列表与工单详情处理页

### Changed

- 订单管理页、客服工单页、账号中心等后台页面继续优化响应式布局
- 商家后台筛选区和信息区重排，改善中等宽度下的拥挤与换行问题
- README 重写为更简洁的 GitHub 首页说明结构

### Fixed

- 修复工单关闭后仍可继续回复的问题
- 修复商家仅更新工单状态时用户收不到通知的问题
- 修复后台页面在部分窗口宽度下横向溢出的问题

### Verified

- `manage.py check`
- `manage.py test`

## 0.0.6 - 2026-03-23

### Added

- 卡密库存与发货内容改为应用层加密存储
- 卡密去重改为基于哈希校验
- 新增敏感操作日志，记录查看卡密、查看发货内容、发送查看提醒等操作
- 新增商家后台与 Admin 的可选 IP 白名单限制
- 新增更完整的商品详情页与同类商品推荐区
- 前台首页扩充演示商品数量，提升真实测试体验

### Changed

- 商家库存页、用户订单页、访客查单页默认只显示卡密掩码，改为按需查看
- 商家“重发卡密到邮箱”改为更安全的“发送查看提醒”
- 首页商品区文案改为中性商城表达，不再使用苹果类比
- 首页商品卡片和详情页视觉做了统一优化

### Fixed

- 修复卡密和发货内容明文落库带来的高风险泄露问题
- 修复库存导入 `bulk_create` 绕过模型加密逻辑的问题
- 修复提醒邮件在未配置 `SITE_BASE_URL` 时缺少绝对链接的问题
- 修复访客查看发货内容令牌校验过松的问题

### Verified

- `manage.py check`
- `manage.py test`

## 0.0.5 - 2026-03-23

### Added

- 商家订单管理新增关键词搜索、订单状态筛选、支付状态筛选、时间范围筛选
- 商家订单详情新增复制卡密、重发卡密到邮箱、手动标记异常
- 商品管理新增搜索、上下架切换、低库存阈值展示
- 库存管理新增导入预览、重复检测、导入历史
- 用户中心新增订单筛选、再次购买、复制订单号
- 商品新增可配置低库存提醒阈值
- 新增库存导入批次历史模型

### Changed

- 低库存提醒从固定 `<= 3` 升级为按商品阈值判断
- 用户中心订单页升级为更完整的账号中心
- 用户订单详情页与商家订单详情页都补齐了更实用的复制操作

### Fixed

- 商家订单列表缺少直观操作入口的问题
- 库存导入时只能整批失败、无法先预览重复内容的问题
- 登录后首页缺少明确用户中心入口的问题

### Verified

- `manage.py check`
- `manage.py test`

## 0.0.4 - 2026-03-23

### Added

- 登录页新增“通过邮箱找回密码”入口
- 完整接入密码找回、重置密码、已登录修改密码页面与流程
- 账号中心新增账号资料展示和修改密码入口
- 商家后台总览新增更适合窄卡片布局的最近订单卡片列表
- 密码重置邮件支持 `SITE_BASE_URL`，可切到局域网地址或正式域名

### Changed

- 顶部登录后导航从“我的订单”调整为更明确的“账号中心”
- 商家后台统计卡片改为内容居中展示
- 商家总览页最近订单区从表格改为卡片，避免长订单号挤压错位
- README 补充 `SITE_BASE_URL` 说明并修正日志链接

### Fixed

- 注册验证码发送失败时会回滚验证码记录，避免用户未收到邮件却被冷却时间拦住
- 注册发码接口增加邮箱格式校验与异常日志，排查问题更直接
- 密码重置邮件链接不再只能绑定请求主机，便于后续外部设备测试

### Verified

- `manage.py check`
- `manage.py test`

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
