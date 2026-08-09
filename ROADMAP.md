# ROADMAP — 路线图与成果（v5 全部完成版）

> 状态：**全部计划批次完成 ✅（2026-08-10）** · pytest **250 项全绿** + CI 全绿 + E2E 107 断言
> 执行方式：omp（Oh My Pi）headless × 并行 + 多模型 advisor 实时监督 + 独立复核三重验收
> 来源沿革：MOA 三方审视（GLM-5.2 + Kimi K3-256K + GPT-5.6 Luna）→ DeepSeek V4 Flash 聚合 → hackathon 轮0–9 迭代

## 完成清单（v5）

### Hackathon 轮次（轮0–轮8，功能/质量全部交付）
| 轮次 | 主题 | 关键交付 | Commit | 验证 |
|---|---|---|---|---|
| 轮0 | 用户视角 E2E 全旅程 + 个人中心 | 48 步旅程脚本、7 缺陷修复、个人中心补全 | c7ffeea | E2E 48/48 |
| SEC | 安全审计修复 | 登录限速 / CORS 收紧 / 错误处理 | cbf0da6 | pytest + 审计 |
| 1-B | UX 打磨 | 22 项体验优化 | 2c1d233 | UX 审计 |
| 2-A | 性能优化 | API 计时 + 索引 + 懒加载 | 477f7be | PERF_REPORT |
| 2-B | 稳定性提升 | 异常路径、竞态 | 8e65c3d | STABILITY_REPORT |
| 波次3 | 部署就绪 | Docker 多阶段 / 微信云托管 / MySQL | 02c5d07 | DEPLOY.md |
| 波次4 | 用户旅程补强 | 旅程完善 | d06e4e3 | JOURNEY_REPORT |
| 波次5 | 数据运维 | 备份 / 孤儿清理 / 健康核查脚本 | e210684 | OPS_REPORT |
| 波次6 | 异常路径 E2E | 33 断言 + 6 缺陷修复 | c9b601e | EDGE_REPORT |
| 轮2-B | 数据模型深化 | 模型精化 + 迁移 | c786b80 | pytest |
| 轮2-A | 移动端深化 PWA | 移动端适配 / 离线 / manifest | dc6773f | MOBILE2_REPORT |
| 轮3 | 无障碍 + 桌面响应式 | a11y 扫描 / 键盘走查 / 桌面布局 | c36f207 | A11Y_DESKTOP_REPORT |
| 轮4 | 并发竞态修复（压测） | 压测发现 → 修复 | e658f86 | STRESS_REPORT |
| 轮5 | i18n + 演示种子数据 | 前端 i18n 架构、seed_demo 幂等造数 | 6dab9aa | I18N_SEED_REPORT |
| 轮6 | 浏览器兼容矩阵 | Chrome/Edge 桌面+移动 4 矩阵 | 951a643 | BROWSER_REPORT |
| 轮7 | 终审补测 + 报告索引 | 246→248 测试、6 页视觉终审、15 报告索引 | 8a5cca4 | FINAL_REPORT |
| 轮8 | 场景扩展 E2E + 性能复测 | 6 场景 59 断言、2 个 P1 修复（加入确认通知、资料预填）、9 接口 4–5ms 复测 | 49e14dc | SCENARIOS2_REPORT，pytest 250 |

### Hackathon 轮9（本文件所属，文档轮）
| 交付 | 内容 |
|---|---|
| README.md | 全面重写：定位/8 大功能/3 步快速开始/技术栈表/架构图/质量说明/文档导航 |
| docs/ARCHITECTURE.md | 模块图（后端 8 域 + 前端结构）、数据模型（6+2 表关系）、关键机制（抽签/状态机/通知/限速/迁移/安全） |
| docs/API.md | 49 个接口全量文档，与路由文件 grep 清单核对 100% 覆盖 |
| ROADMAP.md | 本文（v5） |
| CHANGELOG.md | 按波次的变更日志（含 commit） |
| .audit/DOCS_REPORT.md | 本轮报告 |

### MOA 质检批次（v4 沉淀，全部完成）
| 批次 | 任务 | Commit | 验证 |
|---|---|---|---|
| 第一批 R1–R6 | 抽签纯函数+CI / 游客落地页 / 揭晓动效 / 抽签幂等 / notify 抽象+截止提醒 / SQLite WAL | d12deef, fe427a0, aaa159e, 96872c3 | pytest 12 + 接口 9/9 等 |
| 第二批 | Blueprint 拆分（1900 行 → 8 模块）/ Canvas 海报 / storage 抽象 | d372067 | 回归 12/12 + pytest 14 |
| 第三批 | KDNiao 封装 / 上传魔数校验 / 晒图隐私三模式 | 14ec720 | pytest 15 |
| 第四批 | 送礼状态机 / 可观测性 / 版本化迁移 | 2f74da4 | pytest 13 + 11 + 5 |
| 第五批 P0/P1/P2 | 晒图删除 / 忘记密码 / 重置抽签 / 成员状态+催办 / 通知批量管理 / 注销+导出 / 归档+短码安全 / 流程步骤条 / 错误提示+防重复提交 / 文案中文化 / 空状态+复用成员 | 45bc99f → acfb88e | pytest 181 + 独立复核 |

## 已知遗留（低优先，未来迭代）
1. 互避规则对新活动需成员编辑 UI（后端按 userId 存规则，前端按用户名解析——需成员管理页）
2. 微信生态：订阅消息/小程序登录（依赖微信开放平台账号）
3. 礼物档案/画像（需真实用户数据）
4. Docker/NAS 部署形态扩展（已评估难度 L，待用户决定）

## 质量体系（v5 沉淀）
- pytest 0 → **250 项全绿**（`PYTHONPATH=. python3 -m pytest tests -q`），CI 全绿（GitHub Actions）
- E2E：主旅程 48 步 + 场景扩展 59 断言 = **107 断言**（Puppeteer）
- 每波验收三重：独立 pytest + 独立接口/E2E 脚本 + advisor 记录抽查
- omp 纪律：文件域隔离约束、重启必须 `curl --noproxy '*'` 验证（本机 curl 走代理会假在线）、自报数字需独立复核（多次发现计数口径差异）
