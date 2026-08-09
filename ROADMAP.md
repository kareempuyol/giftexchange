# ROADMAP — 后续任务与计划（v4 全部完成版）

> 来源：MOA 多模型审视 —— GLM-5.2 + Kimi K3-256K + GPT-5.6 Luna 三份独立意见 → DeepSeek V4 Flash 聚合
> 状态：**全部批次完成 ✅（2026-08-09）**，测试 181 项全绿 + CI 全绿
> 执行方式：omp（Oh My Pi）headless × 并行 + gpt-5.6-luna advisor 实时监督 + Hermes 主线程三重验收

## 完成清单（v4）

### 第一批（R1-R6，原始 MOA 计划）
| 任务 | Commit | 验证 |
|---|---|---|
| R1 抽签纯函数 + pytest + GitHub Actions CI | d12deef | pytest 12 + CI success |
| R2 游客邀请落地页 + 登录回跳 | d12deef | 接口 9/9 + 浏览器实测 |
| R3 信封揭晓动效 + 悄悄话门控 | fe427a0, aaa159e | 面面复验确认动画 |
| R4 抽签幂等 + 互避无解预判 | fe427a0 | 接口 6/6 |
| R5 notify 抽象 + 截止提醒 + 调度线程 | fe427a0, 96872c3 | 接口 8/8 + 自动扫描 |
| R6 SQLite WAL + busy_timeout | fe427a0 | journal_mode=wal |

### 第二批（工程化）
| 任务 | Commit | 验证 |
|---|---|---|
| Blueprint 拆分（views.py 1900 行 → 8 模块） | d372067 | 回归 12/12 |
| Canvas 分享海报 + 再开一局 + 季节模板 | d372067 | 浏览器 4/4 |
| storage.py 存储抽象 | d372067 | pytest 14 |

### 第三批（安全/稳定性）
| 任务 | Commit | 验证 |
|---|---|---|
| KDNiao 封装（3s/6h/降级） | 14ec720 | pytest 14 |
| 上传魔数校验 + storage 接入 | 14ec720 | pytest 15 |
| 晒图隐私三模式 + summary 保留修复 | 14ec720 | pytest 3 + 面面确认 |

### 第四批（可观测/工程）
| 任务 | Commit | 验证 |
|---|---|---|
| 送礼状态机（4 步进度条） | 2f74da4 | pytest 13 + 面面确认 |
| 可观测性（request_id + 结构化日志） | 2f74da4 | pytest 11 |
| 版本化迁移（schema_migrations） | 2f74da4 | pytest 5 |

### 第五批（MOA 质检 P0/P1/P2 —— 用户视角功能完备性）
| 任务 | Commit | 验证 |
|---|---|---|
| P0 晒图删除（3/3 共识） | 45bc99f | pytest 112 + 独立 10/10 |
| P0 忘记密码（3/3） | 7222b07 | pytest 130 + 独立 14/14 |
| P0 重置抽签（3/3） | 7222b07 | 同上 |
| P0 成员状态+催办（3/3） | dd252e2 | pytest 149 + 独立 14/14 |
| P1 通知批量管理（read-all/clear/偏好开关） | dd252e2 | 同上 |
| P1 账号注销+数据导出 | 94b9117 | pytest 156 + 独立 8/8 |
| P0 活动归档 + 短码安全（重置/限速） | 164fd38 | pytest 165 + 独立 13/13 |
| P1 流程步骤条 + 移动端键盘避让 + 死代码清理 | c60db11 | pytest 181 + 独立 7/7 |
| P1 错误提示统一 + 防重复提交 | c60db11 | 同上 |
| 全站错误文案中文化（87 处） | a890e30 | pytest 181 |
| P1/P2 空状态引导 + 再开一局复用成员 + 互避可用性 | acfb88e | pytest 181 + 浏览器实测 |

## 已知遗留（低优先，未来迭代）
1. 互避规则对新活动需成员编辑 UI（后端按 userId 存规则，前端按用户名解析——需成员管理页）
2. 微信生态：订阅消息/小程序登录（依赖微信开放平台账号）
3. 礼物档案/画像（需真实用户数据）
4. Docker/NAS 部署（已评估难度 L，待用户决定）

## 质量体系（v4 沉淀）
- pytest 0 → **181 项**，CI 全绿（GitHub Actions）
- 每波验收三重：独立 pytest + 独立接口脚本 + luna advisor 记录抽查
- omp 纪律：文件域隔离约束（只允许改 X/禁止改 Y）、重启必须 `curl --noproxy '*'` 验证（本机 curl 走代理会假在线）、自报数字需独立复核（多次发现计数口径差异）
