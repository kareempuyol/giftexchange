import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import { t, useLocale } from '../i18n'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  useLocale() // 订阅语言切换：setLocale 后重渲染（i18n 示范迁移）
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [showPwd, setShowPwd] = useState(false)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) {
      setError(t('请输入用户名和密码'))
      return
    }
    setSubmitting(true)
    setError('')
    try {
      await login(username, password)
      // 支持邀请链接直达：登录后回到原目标页
      const from = new URLSearchParams(window.location.search).get('from')
      navigate(from ? `/${from}` : '/events', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('登录失败，请稍后重试'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <div className="auth-logo">🎁</div>
          <h1 className="auth-title">{t('互送礼物')}</h1>
          <p className="auth-slogan">{t('和朋友们交换惊喜')}</p>
        </div>

        <h2 className="auth-subtitle">{t('登录')}</h2>

        <form onSubmit={onSubmit}>
          <div className="form-group">
            <label className="sr-only" htmlFor="login-username">{t('用户名')}</label>
            <input
              id="login-username"
              className="form-input"
              placeholder={t('用户名')}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              aria-describedby={error ? 'login-error' : undefined}
            />
          </div>
          <div className="form-group">
            <div className="pwd-wrap">
              <label className="sr-only" htmlFor="login-password">{t('密码')}</label>
              <input
                id="login-password"
                className="form-input"
                type={showPwd ? 'text' : 'password'}
                placeholder={t('密码')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                aria-describedby={error ? 'login-error' : undefined}
              />
              <button
                type="button"
                className="pwd-toggle"
                onClick={() => setShowPwd(v => !v)}
                aria-label={showPwd ? t('隐藏密码') : t('显示密码')}
              >
                {showPwd ? '🙈' : '👁️'}
              </button>
            </div>
            <div style={{ marginTop: 8, textAlign: 'right' }}>
              <Link to="/forgot-password" className="form-hint">{t('忘记密码？')}</Link>
            </div>
          </div>

          {error && <div id="login-error" className="form-error" role="alert" style={{ marginBottom: 12 }}>{error}</div>}

          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? t('登录中…') : t('登录')}
          </button>
        </form>

        <div className="auth-footer">
          <span>{t('还没有账号？')}</span>
          <Link to={(() => {
            const from = new URLSearchParams(window.location.search).get('from')
            return from ? `/register?from=${encodeURIComponent(from)}` : '/register'
          })()}>
            {t('立即注册')}
          </Link>
        </div>
      </div>
    </div>
  )
}
