"""兼容导入层（Blueprint 拆分重构 R2 后）。

原单文件 ~1900 行已按域拆分为：
    auth_routes    — auth/*、profile、admin/settings、登录限速
    event_routes   — events CRUD、list、public、joined、preview、join、leave、participants、dashboard
    draw_routes    — draw、matches、my-match
    gift_routes    — received-gift、gift-wall、gift-wall/like、note、shipment
    notify_routes  — notifications、notifications/read
    site_routes    — /、/api-health、/api/health、/assets、/uploads、/api/upload、SPA 兑底
    helpers        — api/site Blueprint 定义 + 全部共享辅助函数

本模块保留为聚合点（保证 import wxcloudrun.views 不报错，且 __init__.py
`from wxcloudrun.views import api, site` 一行不变）：
    - 导入本模块即完成所有路由注册（各路由模块 import 的副作用）
    - from wxcloudrun.helpers import * 重新导出所有公共辅助（含 api/site/create_notification）
"""
from wxcloudrun import auth_routes, draw_routes, event_routes, gift_routes, notify_routes, site_routes  # noqa: F401  (副作用：注册路由)
from wxcloudrun.helpers import *  # noqa: F401,F403
