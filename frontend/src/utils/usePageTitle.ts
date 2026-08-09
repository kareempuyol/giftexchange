import { useEffect } from 'react'
import { t, useLocale } from '../i18n'

/**
 * 页面级标签页标题：`{titleKey 翻译} - 互送礼物`（随语言切换）。
 * 传入 dynamic 时优先使用（如活动详情页的活动名，非翻译 key）。
 */
export function usePageTitle(titleKey?: string, dynamic?: string) {
  const locale = useLocale()
  useEffect(() => {
    document.title = dynamic
      ? `${dynamic} - ${t('互送礼物')}`
      : titleKey
        ? `${t(titleKey)} - ${t('互送礼物')}`
        : t('互送礼物')
  }, [titleKey, dynamic, locale])
}
