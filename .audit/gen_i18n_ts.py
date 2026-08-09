#!/usr/bin/env python3
"""由 .audit/en_dict_gen.py 的 EN 映射 + /tmp/i18n_keys.json 生成 frontend/src/i18n.ts。"""
import json
import sys

sys.path.insert(0, '/Users/hubertliu/giftexchange/.audit')
from en_dict_gen import EN  # noqa: E402

keys = json.load(open('/tmp/i18n_keys.json'))
ALLOW_ORPHANS = {'保存', '删除', '确认'}  # 公共动作注册表（保留供后续组件使用）
missing = [k for k in keys if k not in EN]
orphans = [k for k in EN if k not in keys and k not in ALLOW_ORPHANS]
if missing:
    raise SystemExit(f'MISSING EN: {missing}')
if orphans:
    raise SystemExit(f'ORPHAN EN: {orphans}')

# zhKeys = 全部 key 去重排序（注册表）
zh_lines = ['export const zhKeys = [']
for k in sorted(keys):
    zh_lines.append(f"  {json.dumps(k, ensure_ascii=False)},")
zh_lines.append('] as const')
zh_block = '\n'.join(zh_lines)

# en 字典
en_lines = ['const en: Record<string, string> = {']
for k in sorted(keys):
    en_lines.append(f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(EN[k], ensure_ascii=False)},")
en_lines.append('}')
en_block = '\n'.join(en_lines)

HEADER = '''/**
 * 轻量国际化（不引 react-i18next）：
 * - t(key, vars?)：key 即中文原文（key = source），zh 模式直接返回原文；
 *    en 模式查 en 字典，未翻译的 key 回退原文（保证 UI 永不缺文案）。
 * - 语言检测：localStorage('gift_locale') 可覆写；否则按 navigator.language
 *   （'en*' → en，其余 → zh；zh 默认，存量中文 UI 不受影响）。
 * - 模块级 locale + useLocale()（useSyncExternalStore）订阅重渲染；
 *   同时同步 document.documentElement.lang 与 document.title。
 *
 * 迁移指南（未来组件）：
 *   1. 把组件里的中文常量替换为 t('原文')；
 *   2. 若该文案是高频公共串，登记进下方 zhKeys，并在 en 字典补翻译；
 *   3. 组件内调用 useLocale()（保证 setLocale 后重渲染）。
 *
 * I18N2（hackathon 轮10）：全站文案已迁移至 t()。字典由
 * .audit/en_dict_gen.py 生成（key=原文，value=自然英文），覆盖 100% 使用中的 key；
 * 新增文案请同时补 en 翻译（未收录 key 回退原文，UI 永不缺文案）。
 */
import { useSyncExternalStore } from 'react'

export type Locale = 'zh' | 'en'

const STORAGE_KEY = 'gift_locale'

// zh 字典登记：全部使用中的 key（含高频公共串）。新迁移的公共文案先加到这里再补 en 翻译。
'''

TAIL = '''
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
    // 标签页标题随语言（index.html 静态 title 由运行时接管）
    document.title = locale === 'en' ? 'Gift Exchange' : '互送礼物'
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
    text = text.replace(/\\{(\\w+)\\}/g, (m, name) =>
      vars[name] != null ? String(vars[name]) : m
    )
  }
  return text
}
'''

out = HEADER + zh_block + '\n\n// en 字典：key=中文原文，value=自然英文（生成自 .audit/en_dict_gen.py）\n' + en_block + TAIL
with open('/Users/hubertliu/giftexchange/frontend/src/i18n.ts', 'w') as fh:
    fh.write(out)
print(f'wrote frontend/src/i18n.ts: {len(keys)} keys')
