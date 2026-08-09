// i18n：用户可见文案已迁移至 t()（详见 i18n.ts）
import { useState } from 'react'
import { useNavigate, Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import { t, useLocale } from '../i18n'
import { usePageTitle } from '../utils/usePageTitle'
import AuthBrand from '../components/AuthBrand'

export default function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  useLocale() // 订阅语言切换：setLocale 后重渲染（i18n 示范迁移）
  usePageTitle('注册')
  const [params] = useSearchParams()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [showPwd, setShowPwd] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !email || !password) {
      setError(t('请填写所有字段'))
      return
    }
    if (password !== confirm) {
      setError(t('两次输入的密码不一致'))
      return
    }
    if (password.toLowerCase() === username.toLowerCase()) {
      setError(t('密码不能与用户名相同'))
      return
    }
    setSubmitting(true)
    setError('')
    try {
      await register(username, email, password)
      const from = params.get('from')
      navigate(from ? `/${from}` : '/events', { replace: true })
    } catch (err) {
      // 邀请制关闭（403）：后端返回「注册已关闭」，转成友好文案展示
      setError(
        err instanceof ApiError && err.status === 403
          ? t('注册暂未开放')
          : err instanceof ApiError
            ? err.message
            : t('注册失败，请稍后重试')
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <AuthBrand />

        <h2 className="auth-subtitle">{t('注册')}</h2>
        <p className="form-hint" style={{ marginBottom: 16 }}>{t('加入礼物互赠的乐趣')}</p>

        <form onSubmit={onSubmit}>
          <div className="form-group">
            <label className="sr-only" htmlFor="register-username">{t('用户名')}</label>
            <input
              id="register-username"
              className="form-input"
              placeholder={t('用户名')}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-describedby={error ? 'register-error' : undefined}
            />
            <div className="form-hint">{t('至少 2 个字符')}</div>
          </div>
          <div className="form-group">
            <label className="sr-only" htmlFor="register-email">{t('邮箱')}</label>
            <input
              id="register-email"
              className="form-input"
              type="email"
              placeholder={t('邮箱')}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-describedby={error ? 'register-error' : undefined}
            />
            <div className="form-hint">{t('用于登录和找回密码')}</div>
          </div>
          <div className="form-group">
            <div className="pwd-wrap">
              <label className="sr-only" htmlFor="register-password">{t('密码')}</label>
              <input
                id="register-password"
                className="form-input"
                type={showPwd ? 'text' : 'password'}
                placeholder={t('密码')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-describedby={error ? 'register-error' : undefined}
              />
              <button type="button" className="pwd-toggle" onClick={() => setShowPwd(v => !v)} aria-label={showPwd ? t('隐藏密码') : t('显示密码')}>
                {showPwd ? '🙈' : '👁️'}
              </button>
            </div>
            <div className="form-hint">{t('至少 6 位，需包含字母和数字')}</div>
          </div>
          <div className="form-group">
            <div className="pwd-wrap">
              <label className="sr-only" htmlFor="register-confirm">{t('确认密码')}</label>
              <input
                id="register-confirm"
                className="form-input"
                type={showConfirm ? 'text' : 'password'}
                placeholder={t('确认密码')}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                aria-describedby={confirm && password !== confirm ? 'register-mismatch' : error ? 'register-error' : undefined}
              />
              <button type="button" className="pwd-toggle" onClick={() => setShowConfirm(v => !v)} aria-label={showConfirm ? t('隐藏密码') : t('显示密码')}>
                {showConfirm ? '🙈' : '👁️'}
              </button>
            </div>
            {confirm && password !== confirm && (
              <div id="register-mismatch" className="form-error" role="alert">{t('两次输入的密码不一致')}</div>
            )}
          </div>

          {error && <div id="register-error" className="form-error" role="alert" style={{ marginBottom: 12 }}>{error}</div>}

          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? t('注册中…') : t('注册')}
          </button>
        </form>

        <div className="auth-footer">
          <span>{t('已有账号？')}</span>
          <Link to="/login">{t('立即登录')}</Link>
        </div>
      </div>
    </div>
  )
}
