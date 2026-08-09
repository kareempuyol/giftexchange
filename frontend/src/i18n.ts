/**
 * 轻量国际化（不引 react-i18next）：
 * - t(key, vars?)：key 即中文原文（key = source），zh 模式直接返回原文；
 *    en 模式查 en 字典，未翻译的 key 回退原文（保证 UI 永不缺文案）。
 * - 语言检测：localStorage('gift_locale') 可覆写；否则按 navigator.language
 *   （'en*' → en，其余 → zh；zh 默认，存量中文 UI 不受影响）。
 * - 模块级 locale + useLocale()（useSyncExternalStore）订阅重渲染；
 *   同时同步 document.documentElement.lang。
 *
 * 迁移指南（未来组件）：
 *   1. 把组件里的中文常量替换为 t('原文')；
 *   2. 若该文案是高频公共串，登记进下方 zhKeys，并在 en 字典补翻译；
 *   3. 组件内调用 useLocale()（保证 setLocale 后重渲染）。
 * 本轮示范迁移：Header / LoginPage / api client 网络错误文案；其余组件暂保留中文。
 */
import { useSyncExternalStore } from 'react'

export type Locale = 'zh' | 'en'

const STORAGE_KEY = 'gift_locale'

// zh 字典登记：高频公共串（key 即原文）。新迁移的公共文案先加到这里再补 en 翻译。
export const zhKeys = [
  // 通用动作
  '保存',
  '取消',
  '删除',
  '确认',
  '加载中…',
  '重试',
  // 网络/操作错误（Toast 公共文案）
  '网络连接失败，请检查网络后重试',
  '请求超时，请稍后重试',
  '请求已取消',
  '请求失败',
  '上传失败',
  '服务响应异常 ({status})',
  '操作失败，请重试',
  '加载失败，请稍后重试',
  // 认证
  '登录',
  '注册',
  '退出',
  '登录中…',
  '用户名',
  '密码',
  '显示密码',
  '隐藏密码',
  '忘记密码？',
  '请输入用户名和密码',
  '登录失败，请稍后重试',
  '还没有账号？',
  '立即注册',
  // Header / 通知
  '我的活动',
  '主导航',
  '创建',
  '通知',
  '通知面板',
  '全部已读',
  '清空已读',
  '暂无通知',
  '标记已读：{title}',
  '查看活动 ↗',
  '个人资料',
  '互送礼物',
  '和朋友们交换惊喜',
] as const

// en 字典：只翻译公共串；未收录 key 由 t() 回退原文（中文）
const en: Record<string, string> = {
  '保存': 'Save',
  '取消': 'Cancel',
  '删除': 'Delete',
  '确认': 'Confirm',
  '加载中…': 'Loading…',
  '重试': 'Retry',
  '网络连接失败，请检查网络后重试': 'Network error, please check your connection and retry',
  '请求超时，请稍后重试': 'Request timed out, please try again later',
  '请求已取消': 'Request cancelled',
  '请求失败': 'Request failed',
  '上传失败': 'Upload failed',
  '服务响应异常 ({status})': 'Server responded with an error ({status})',
  '操作失败，请重试': 'Operation failed, please retry',
  '加载失败，请稍后重试': 'Failed to load, please try again later',
  '登录': 'Log in',
  '注册': 'Sign up',
  '退出': 'Log out',
  '登录中…': 'Logging in…',
  '用户名': 'Username',
  '密码': 'Password',
  '显示密码': 'Show password',
  '隐藏密码': 'Hide password',
  '忘记密码？': 'Forgot password?',
  '请输入用户名和密码': 'Please enter username and password',
  '登录失败，请稍后重试': 'Login failed, please try again later',
  '还没有账号？': "Don't have an account?",
  '立即注册': 'Sign up now',
  '我的活动': 'My events',
  '主导航': 'Main navigation',
  '创建': 'Create',
  '通知': 'Notifications',
  '通知面板': 'Notifications panel',
  '全部已读': 'Mark all as read',
  '清空已读': 'Clear read',
  '暂无通知': 'No notifications',
  '标记已读：{title}': 'Mark as read: {title}',
  '查看活动 ↗': 'View event ↗',
  '个人资料': 'Profile',
  '互送礼物': 'Gift Exchange',
  '和朋友们交换惊喜': 'Exchange surprises with friends',
}

export function detectLocale(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'zh' || stored === 'en') return stored
  } catch {
    /* localStorage 不可用（隐私模式等）时回退 navigator 检测 */
  }
  const lang = (navigator.language || navigator.languages?.[0] || '').toLowerCase()
  return lang.startsWith('en') ? 'en' : 'zh'
}

let locale: Locale = typeof window !== 'undefined' ? detectLocale() : 'zh'
const listeners = new Set<() => void>()

function applyLang(): void {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = locale === 'en' ? 'en' : 'zh-CN'
  }
}
applyLang()

export function getLocale(): Locale {
  return locale
}

export function setLocale(next: Locale): void {
  if (next === locale) return
  locale = next
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch {
    /* 忽略写失败 */
  }
  applyLang()
  listeners.forEach((fn) => fn())
}

/** 订阅当前语言；locale 变化时触发重渲染（组件内调用即可）。 */
export function useLocale(): Locale {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => {
        listeners.delete(fn)
      }
    },
    getLocale,
    getLocale
  )
}

/** 翻译：key 即中文原文；en 未翻译回退原文。支持 {var} 插值（vars 传入）。 */
export function t(key: string, vars?: Record<string, string | number>): string {
  let text = locale === 'en' ? en[key] ?? key : key
  if (vars) {
    text = text.replace(/\{(\w+)\}/g, (m, name) =>
      vars[name] != null ? String(vars[name]) : m
    )
  }
  return text
}
