/**
 * 活动列表状态保留（EventsPage：详情页返回不丢 tab/搜索/滚动位置）。
 * 独立成模块：Header「我的活动/品牌」显式导航需要 clearListState()，
 * 而 Header 在首屏 bundle 中——若留在 EventsPage（路由分包懒加载）会把它拉回主包。
 */
export const LIST_STATE_KEY = 'gift-list-state'
export const LIST_TABS = ['mine', 'joined', 'public', 'archived'] as const

export type ListTab = (typeof LIST_TABS)[number]

export interface ListState {
  tab: ListTab
  search: string
  scrollY: number
}

export function readListState(): ListState | null {
  try {
    const raw = sessionStorage.getItem(LIST_STATE_KEY)
    if (!raw) return null
    const s = JSON.parse(raw)
    if (s && LIST_TABS.includes(s.tab) && typeof s.scrollY === 'number') {
      return { tab: s.tab, search: typeof s.search === 'string' ? s.search : '', scrollY: s.scrollY }
    }
    return null
  } catch {
    return null
  }
}

export function clearListState() {
  try {
    sessionStorage.removeItem(LIST_STATE_KEY)
  } catch {
    /* ignore */
  }
}
