# CHANGELOG

> 项目无发布版本号，按开发波次记录。提交哈希取 `git log` 短哈希。
> 格式：日期 · 波次标题（commit）—— 内容。最新在前。

## 2026-08-10 · Hackathon 轮11 — 体验收尾 + 微信生态预留（本轮，未 commit）
- 空态引导：首页空态卡片三入口可达（创建活动 / 邀请码加入 / 发现活动），joined 空态补「发现活动」；截图走查 desktop+mobile（ui-shots/r13/）
- 列表状态保留：详情页返回恢复 tab/搜索/滚动位置（sessionStorage 自管 + `history.scrollRestoration='manual'`，规避浏览器导航滚动重置污染保存值）；Header「我的活动/品牌」显式导航清除状态
- 表单回车补齐：搜索栏/邀请码弹窗改为真 `<form onSubmit>`；加入表单步骤①「下一步」改 type=submit（原先无 submit 按钮 + textarea 阻断隐式提交，回车无响应），空字段回车报错、已填回车进步骤②、不跳过心愿单
- 加载与错误恢复复核：登录后 /events 为 spinner 非白屏；列表加载失败内联重试按钮 + 页面不死（截图确认）
- 微信预留：确认 users.openid/unionid/session_key 列（migration v5）写路径；新增公开 `GET /api/site/config`（registration_enabled/site_name）；docs/ARCHITECTURE.md 增「微信生态接入规划」节（接入路径+红线，无假实现）
- 邀请制开关前端：登录页按配置隐藏注册入口、注册页 403 →「注册暂未开放」（i18n zh+en）；新增 tests/test_site_config.py（3 用例）

## 2026-08-10 · Hackathon 轮10 — i18n 全量迁移 + 登录安全深化（本轮，未 commit）
- i18n 全站迁移：9 页 + 6 组件 + App/format/client 全部文案接入 t()，en 字典 499 key 100% 覆盖（生成自 .audit/en_dict_gen.py），未翻译 key 回退原文 = 0
- en-US 全站走查通过（登录/列表/详情/礼物墙/个人中心/创建页/海报弹窗截图 7+1 张，.audit/i18n2-shots/）；zh 默认逐字不变；document.title 随语言
- 顺带修复：EventDetailPage 缺失 SafeImage import（渲染崩溃隐患）
- login_required 开销实测（.audit/login_required_bench.py）：~0.40ms 中位/0.90ms p99，保持每请求单列 SELECT（安全>微优化），结论见 .audit/I18N2_REPORT.md
- 登录审计补全：注销账号登录尝试计入 login_failed（含 IP/用户名/时间）+ 限速
- 密码策略 P2：密码不能与用户名相同（注册/改密/重置，前后端 + 大小写不敏感），docs/API.md 同步

## 2026-08-10 · Hackathon 轮9 — 产品文档全面化（本轮，未 commit）
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
