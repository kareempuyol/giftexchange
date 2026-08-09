/**
 * 主题切换（暗色模式）
 * ===================
 * 生效方式：<html data-theme="dark">，变量覆盖层见 tokens.css `:root[data-theme='dark']`。
 * 优先级：localStorage('gift-theme') 手动覆盖 > 系统 prefers-color-scheme > 默认浅色。
 * 系统主题变化时自动跟随（仅未手动覆盖时）。
 */
const STORAGE_KEY = 'gift-theme'

export type Theme = 'light' | 'dark'

function systemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function getStoredTheme(): Theme | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return v === 'light' || v === 'dark' ? v : null
  } catch {
    return null
  }
}

export function applyTheme(theme?: Theme): Theme {
  const resolved = theme ?? getStoredTheme() ?? systemTheme()
  document.documentElement.dataset.theme = resolved
  return resolved
}

/** 手动覆盖（UI 开关可调用；无开关时跟随系统） */
export function setTheme(theme: Theme): void {
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    /* 隐私模式等场景：仅本次生效 */
  }
  applyTheme(theme)
}

/** 取消手动覆盖，回到跟随系统 */
export function clearThemeOverride(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
  applyTheme()
}

// 跟随系统主题变化（仅未手动覆盖时）
if (typeof window !== 'undefined' && window.matchMedia) {
  window
    .matchMedia('(prefers-color-scheme: dark)')
    .addEventListener('change', (e) => {
      if (!getStoredTheme()) applyTheme(e.matches ? 'dark' : 'light')
    })
}
