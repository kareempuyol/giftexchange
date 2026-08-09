import { t, useLocale } from '../i18n'

/** 认证页统一品牌区：logo + 品牌名 + 标语（登录/注册/找回密码共用，避免三处漂移） */
export default function AuthBrand() {
  useLocale() // 订阅语言切换：setLocale 后重渲染
  return (
    <div className="auth-brand">
      <div className="auth-logo" aria-hidden="true">🎁</div>
      <h1 className="auth-title">{t('互送礼物')}</h1>
      <p className="auth-slogan">{t('和朋友们交换惊喜')}</p>
    </div>
  )
}
