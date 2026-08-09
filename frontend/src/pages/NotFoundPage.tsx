import { Link } from 'react-router-dom'
import { t, useLocale } from '../i18n'
import { usePageTitle } from '../utils/usePageTitle'

/** 统一 404：未知路由（React Router `*`）落到这里，替代原先跳 /events */
export default function NotFoundPage() {
  useLocale()
  usePageTitle('页面不存在')
  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <div className="auth-logo">🎁</div>
          <h1 className="auth-title">404</h1>
          <p className="auth-slogan">{t('页面不存在')}</p>
        </div>
        <Link to="/events" className="btn btn-primary" style={{ width: '100%' }}>
          {t('回到首页')}
        </Link>
      </div>
    </div>
  )
}
