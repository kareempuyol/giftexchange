/**
 * 展示格式化工具：截止时间友好倒计时、金额/数字千分位
 * 所有页面共用，禁止各页自行拼 ISO 日期字符串
 */

/** 金额：¥1,000（千分位） */
export function formatMoney(n: number | string | null | undefined): string {
  const num = Number(n)
  if (!Number.isFinite(num) || num <= 0) return ''
  return `¥${num.toLocaleString('zh-CN')}`
}

/** 参与人数等数字：千分位（不补零） */
export function formatCount(n: number | null | undefined): string {
  const num = Number(n)
  if (!Number.isFinite(num)) return '0'
  return num.toLocaleString('zh-CN')
}

/**
 * 报名截止时间：友好倒计时
 * - 今天截止 / 明天截止 / 还剩 N 天（≤30 天）
 * - 超过 30 天或已截止 → 展示日期（已截止附加文案）
 */
export function formatDeadline(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const diffMs = d.getTime() - now.getTime()
  const diffDays = Math.ceil(diffMs / 86400000)
  if (diffDays > 30) return d.toLocaleDateString('zh-CN')
  if (diffDays > 1) return `还剩 ${diffDays} 天`
  if (diffDays === 1) return '明天截止'
  if (diffDays === 0) return '今天截止'
  return `已截止（${d.toLocaleDateString('zh-CN')}）`
}

/** 注册日期等历史日期：zh-CN 日期 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('zh-CN')
}
