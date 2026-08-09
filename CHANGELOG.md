# CHANGELOG

> 项目无发布版本号，按开发波次记录。提交哈希取 `git log` 短哈希。
> 格式：日期 · 波次标题（commit）—— 内容。最新在前。

## 2026-08-10 · Hackathon 轮17 — 收官功能 5 项（691aae1）
- 活动热度角标：EventsPage heatBadge（已抽签 🎯 gold / 报名中 ≥5 人 🔥 热度 error），应用于全部列表 tab（公开列表后端只返回 open 活动，🎯 在我创建的/我参与的可见）；i18n 新增 `热度`（en: Hot）
- 礼物墙统计卡：解锁后顶部 3 格（总心意数/平均评分/最高评分）；**规格勘误**：后端 gift-wall 无 totalPosted/totalStars 字段，统计改为前端从 wall.items 评分直接计算（无评分显示 `—`），375px 无横向溢出
- 通知角标点击清零：打开面板时乐观清零 + POST /notifications/read 服务端同步（30s 轮询校正兜底）；服务端核验 0 未读/4 已读（非仅前端乐观）
- AuthBrand 组件抽取：登录/注册/找回密码三页品牌区统一引用（含 useLocale 订阅），消除三处重复
- 预算均摊展示：详情 meta 网格 + 未登录预览卡追加 `· 平均每人 ¥N`（Math.round(budget/count)，预算≤0 或 0 人不显示）；i18n `平均每人 {perPerson}`
- 纯前端轮（后端零改动）：pytest 269 全绿 + build 通过 + 浏览器实测 5/5；wxcloudrun/ 恢复无 diff（部署前需重新 build）

## 2026-08-10 · Hackathon 轮16 — 真实负载模拟（8467b51）
- `.audit/load_sim.py`：50 虚拟用户 × 5 分钟真实节奏（0.5–3s 思考时间，独立 token），隔离实例 `127.0.0.1:8085` + 独立 DB（跑完删除，开发库零接触）
- 结果：**10,646 请求 0 5xx / 0 错误事件 / 0 锁死**，2xx 97.48%（4xx 全为业务语义：满员/重复加入/已抽签），服务端 p99 **32.9ms** / max 71.8ms，>500ms 请求 0；RSS 52MB 平坦、WAL 峰值 32KB 无膨胀
- 结论：**可上线（当前规模）**；写路径单写者串行化，若再上 1–2 个数量级建议切 MySQL（双引擎就绪）
- load_sim.py 自修 3 bug（http.client latin-1 中文 body / 非 ASCII 查询参数编码 / call 返回元组不一致致线程静默死亡）；应用代码零问题
- 产物：`.audit/LOAD_REPORT.md` + `load_results.json`（59 次资源采样）；pytest 269 全绿

## 2026-08-10 · Hackathon 轮15 — 收官回归 + 报告更新（1ad1d89）
- FINAL2 全量回归核对（`.audit/FINAL2_CHECK.md`）：pytest 269 / CI 5 连绿 / build+重启+health+公网冒烟 / E2E 48/48 复跑 / 工作区状态确认
- HACKATHON_DELIVERY.md：轮12/13/14 入时间线、commit 22→25（全仓 84）、缺陷 60+→68、性能亮点行
- CHANGELOG.md：补轮12/13/14 条目；轮9/10/11「未 commit」标注修正为实际 commit hash
- `.audit/REPORTS_INDEX.md`：范围扩至轮1–15，新增轮12/13/14/15 章节

## 2026-08-10 · Hackathon 轮14 — 性能极限 + 打磨（d509a01）
- 性能：vite manualChunks vendor 拆分（react→vendor-react、router→vendor-router），单次发版重下 gzip 75.9→19.7KB（**-74%**）；上传前图片压缩（utils/imageCompress.ts，长边>1600 降采样 + JPEG/WebP 0.8，≤256KB 跳过，扩展名随内容改写），实测 4.53MB→570KB（**-87.4%**）；API 4 列表端点瘦身为 10 字段 summary（helpers.api_event_summary，note 截断 80 字符）；api_event 移除 createdAt/updatedAt；EventsPage 懒加载 + 登录后预取 chunk
- 修 P0：ImageBitmap.close() 在 drawImage 前调用导致所有上传误报「上传失败」（先绘制后 close，注释防回归）
- 打磨：统一 404 页（NotFoundPage，React Router `*`）、9 页面 document.title（usePageTitle，活动名动态，zh/en）；favicon/404/静态资源 200 确认
- 新增 tests/test_api_slim.py（4 用例：summary 字段集合/note 截断/detail 保留）；pytest 265→**269**

## 2026-08-10 · Hackathon 轮13 — 功能增量 5 项（d4abe8f）
- 复制活动：已抽签详情页组织者「📋 复制活动」→ title（副本）/budget/note/公开性/上限/互避规则/成员名单写入 draft → 跳创建页（互避按 userId 反查用户名行格式）
- 礼物墙分享文案：顶部「📋 复制分享文案」（解锁前可用，含短码），gift-wall 响应新增 shortCode 字段
- 心愿清单：迁移 v12（users.wishlist/wishlist_visible）；资料页输入 + 展示开关；my-match 返回 receiverWishlist **仅收礼人开启时**（隐私门控）
- 截止提醒横幅：组织者视角过 drawDate 未抽签红色提醒（纯前端 zh/en）
- 列表 X/N 人：有 maxParticipants 时显示 `{count}/{max} 人`
- 新增 tests/test_features_r13.py（8 用例）；pytest 258→**265**

## 2026-08-10 · Hackathon 轮12 — 收官总报告（7954f7c）
- HACKATHON_DELIVERY.md 总报告 + .audit/DELIVERY_CHECK.md 核对记录（pytest 258 复跑 / E2E 48/48 / CI 5 连绿 / 工作区零 diff）

## 2026-08-10 · Hackathon 轮11 — 体验收尾 + 微信生态预留（90576db）
- 空态引导：首页空态卡片三入口可达（创建活动 / 邀请码加入 / 发现活动），joined 空态补「发现活动」；截图走查 desktop+mobile（ui-shots/r13/）
- 列表状态保留：详情页返回恢复 tab/搜索/滚动位置（sessionStorage 自管 + `history.scrollRestoration='manual'`，规避浏览器导航滚动重置污染保存值）；Header「我的活动/品牌」显式导航清除状态
- 表单回车补齐：搜索栏/邀请码弹窗改为真 `<form onSubmit>`；加入表单步骤①「下一步」改 type=submit（原先无 submit 按钮 + textarea 阻断隐式提交，回车无响应），空字段回车报错、已填回车进步骤②、不跳过心愿单
- 加载与错误恢复复核：登录后 /events 为 spinner 非白屏；列表加载失败内联重试按钮 + 页面不死（截图确认）
- 微信预留：确认 users.openid/unionid/session_key 列（migration v5）写路径；新增公开 `GET /api/site/config`（registration_enabled/site_name）；docs/ARCHITECTURE.md 增「微信生态接入规划」节（接入路径+红线，无假实现）
- 邀请制开关前端：登录页按配置隐藏注册入口、注册页 403 →「注册暂未开放」（i18n zh+en）；新增 tests/test_site_config.py（3 用例）

## 2026-08-10 · Hackathon 轮10 — i18n 全量迁移 + 登录安全深化（54da190）
- i18n 全站迁移：9 页 + 6 组件 + App/format/client 全部文案接入 t()，en 字典 499 key 100% 覆盖（生成自 .audit/en_dict_gen.py），未翻译 key 回退原文 = 0
- en-US 全站走查通过（登录/列表/详情/礼物墙/个人中心/创建页/海报弹窗截图 7+1 张，.audit/i18n2-shots/）；zh 默认逐字不变；document.title 随语言
- 顺带修复：EventDetailPage 缺失 SafeImage import（渲染崩溃隐患）
- login_required 开销实测（.audit/login_required_bench.py）：~0.40ms 中位/0.90ms p99，保持每请求单列 SELECT（安全>微优化），结论见 .audit/I18N2_REPORT.md
- 登录审计补全：注销账号登录尝试计入 login_failed（含 IP/用户名/时间）+ 限速
- 密码策略 P2：密码不能与用户名相同（注册/改密/重置，前后端 + 大小写不敏感），docs/API.md 同步

## 2026-08-10 · Hackathon 轮9 — 产品文档全面化（78450ca）
- 重写 README（定位/8 功能/快速开始/技术栈/架构图/质量/文档导航）
- 新增 docs/ARCHITECTURE.md、docs/API.md（49 接口 100% 覆盖）、CHANGELOG.md
- ROADMAP 升级 v5；新增 .audit/DOCS_REPORT.md

## 2026-08-10 · Hackathon 轮8 — 场景扩展 E2E + 性能复测（49e14dc）
- 场景 E2E 59 断言全过（多活动工作流/礼品流全链路/通知回流/深链直达/资料预填/密码强度边界）
- 修复 P1×2：加入活动发 `join_success` 本人通知；JoinForm 挂载时从 `/api/profile` 预填收件信息
- 性能复测：9 接口 4–5ms 无恶化；懒加载 7/7 验证；主 bundle gzip 64 KB

## 2026-08-10 · Hackathon 轮7 — 终审补测 + 报告索引（8a5cca4）
- pytest 246→248；主旅程复测 48/48；6 页面视觉终审无布局回归
- 补充 note 接口权限边界测试（未登录 401 / 缺参 400 / 非参与者 403 / 越权 400）
- 新增 .audit/REPORTS_INDEX.md（15 份报告索引）

## 2026-08-09 · Hackathon 轮6 — 浏览器兼容矩阵（951a643）
- Chrome/Edge 桌面+移动 4 矩阵回归，修复兼容性问题

## 2026-08-09 · Hackathon 轮5 — i18n 架构 + 演示种子数据（6dab9aa）
- 前端 i18n 架构；幂等演示种子脚本 `scripts/seed_demo.py`（3 demo 账号 + 示例活动）

## 2026-08-09 · Hackathon 轮4 — 并发竞态修复（e658f86）
- 压测暴露的并发竞态修复（抽签/加入/点赞等）

## 2026-08-09 · Hackathon 轮3 — 无障碍 + 桌面响应式（c36f207）
- a11y 扫描修复、键盘走查、桌面布局适配

## 2026-08-09 · Hackathon 轮2-A — 移动端深化 PWA（dc6773f）
- 移动端体验深化；PWA（manifest / sw.js / 图标体系）

## 2026-08-09 · Hackathon 轮2-B — 数据模型深化（c786b80）
- 数据模型精化与迁移补强

## 2026-08-09 · Hackathon 波次6 — 异常路径 E2E（c9b601e）
- 33 断言 + 6 缺陷修复

## 2026-08-09 · Hackathon 波次5 — 数据运维（e210684）
- 运维脚本：backup_db.sh / cleanup_orphans.py / cleanup_notifications.py / healthcheck_data.py

## 2026-08-09 · Hackathon 波次4 — 用户旅程补强（d06e4e3）

## 2026-08-09 · Hackathon 波次3 — 部署就绪（02c5d07）
- Docker 多阶段构建 / docker-compose / Procfile / 环境变量 fail-closed

## 2026-08-09 · Hackathon 波次2-B — 稳定性提升（8e65c3d）

## 2026-08-09 · Hackathon 波次2-A — 性能优化（477f7be）
- 高频查询索引 + API 计时基线 + 前端懒加载

## 2026-08-09 · Hackathon 波次1-B — UX 打磨 22 项（2c1d233）

## 2026-08-09 · Hackathon SEC 波次 — 安全审计修复（cbf0da6）
- 登录限速 / CORS 收紧 / 错误处理收敛

## 2026-08-09 · Hackathon 轮0 — 用户视角 E2E + 个人中心（c7ffeea）
- 48 步全旅程脚本、7 缺陷修复、个人中心补全（资料/偏好/改密）

## 2026-08-09 · 用户反馈修复（a12ed70, 57329cd）
- 流程步骤条文字重叠修复；活动详情页步骤条位置调整

## 2026-08-09 · MOA 波次5（acfb88e）
- 空状态引导 + 再开一局复用成员 + 互避规则可用性

## 2026-08-09 · 文案中文化（a890e30）
- 全站错误文案中文化 87 处

## 2026-08-09 · MOA 波次4（c60db11）
- 流程步骤条 + 移动端适配 + 死代码清理；错误提示统一 + 防重复提交

## 2026-08-09 · MOA 波次3-F（164fd38）
- P0 活动归档 + 短码安全（重置/限速）

## 2026-08-09 · MOA 波次3（94b9117）
- P1 账号注销 + 数据导出

## 2026-08-09 · MOA 波次2（dd252e2）
- P0 成员状态 + 催办；P1 通知批量管理（read-all/clear/偏好开关）

## 2026-08-09 · MOA 波次1（7222b07）
- P0 忘记密码 + 重置抽签

## 2026-08-09 · MOA 波次0（45bc99f）
- P0 晒图删除；MOA 三方质检启动（b14040a：16 共识缺陷/4 独到/三批计划）

## 2026-08-09 · ROADMAP v4（0f5d50d）
- 全批次完成标记（181 测试）

## 2026-08-09 · 个人资料管理（5174e8a）
- 个人资料 + 改密码 + 封面展示修复

## 2026-08-08 · ROADMAP v3（e316045）
- 全批次完成（108 测试全绿）

## 2026-08-08 · 第四批（2f74da4）
- 送礼状态机（4 步进度条）/ 可观测性（request_id + 结构化日志）/ 版本化迁移（schema_migrations）

## 2026-08-08 · 第三批（14ec720）
- KDNiao 封装（3s/6h/降级）/ 上传魔数校验 + storage 接入 / 晒图隐私三模式 + summary 保留修复

## 2026-08-08 · 第二批（d372067）
- Blueprint 拆分（views.py 1900 行 → 8 模块）/ Canvas 分享海报 + 再开一局 + 季节模板 / storage.py 抽象

## 2026-08-08 · R3–R6（fe427a0, aaa159e, 96872c3）
- 信封揭晓动效 + 悄悄话门控 / 抽签幂等 + 互避无解预判 / notify 抽象 + 截止提醒 + 调度线程 / SQLite WAL + busy_timeout

## 2026-08-08 · R1+R2（d12deef）
- 抽签纯函数 + pytest + GitHub Actions CI；游客邀请落地页 + 登录回跳

## 2026-08-07 · 阶段五 — 安全审计（8560ea4）
- 登录限速 / CORS 收紧 / 错误处理

## 2026-08-07 · 阶段四 — UI/UX 审计两轮修复（38a1017, 80809ab, e367427）
- 礼物墙文案 / 图片降级 / 点赞动效 / 页面标题换行

## 2026-08-07 · 阶段二补全（9ec7875, 8bd7aef, 302ef50）
- 通知补全 + dashboard 催办；图片上传 + 微信字段预留 + 抽签并发修复；礼物墙点赞 + 进度条

## 2026-08-07 · 阶段二 D–F（4e4ed51, 236107e, 8af490a）
- 物流自动跟踪 + 发货悄悄话；抽签互避规则 + 结果通知；报名心愿单结构化 + 分步引导

## 2026-08-07 · 阶段二 A（eed5ed5）
- 邀请短码 + 分享链接

## 2026-08-07 · React+Vite 前端工程（c3cd25e）
- Design Tokens 体系（primitive → semantic → component）+ 用户旅程文档

## 2026-08-07 · 阶段二早期修复（a3fcfa8, f46acb9, 858f617, 29be8b6）
- 发货入口与礼物状态 / 晒礼物确认状态 / 修改入口样式弱化 / 通知已读与快递提醒优化

## 2026-08-07 · 前端 UX 修复（ce25c19, d487010, ebb12a9）
- logo/图标色/按钮反馈/品牌识别；nav 图标色与间距/工具提示；头像包裹 IconButton

## 2026-08-07 · 活动广场（11a4250）
- 活动广场 + 私密开关 + 人数上限 + 活动编辑 + 头图 + 分享

## 2026-08-07 · 基础设施（e5095ee, 8bd7aef 前置）
- MySQL TEXT 列 default 值兼容修复（error 1101）

## 2026-08-07 · 初始版本（b371176 init）
- 项目初始化（微信云托管 Flask 模板形态）
