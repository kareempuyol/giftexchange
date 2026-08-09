// i18n：用户可见文案已迁移至 t()（详见 i18n.ts）
import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useToast } from '../components/Toast'
import { t, useLocale } from '../i18n'
import { usePageTitle } from '../utils/usePageTitle'
import AuthBrand from '../components/AuthBrand'

interface ForgotResult {
  code: string
  expiresIn: number
}

export default function ForgotPasswordPage() {
  const navigate = useNavigate()
  useLocale() // 订阅语言切换：setLocale 后重渲染（i18n 示范迁移）
  usePageTitle('找回密码')
  const { toast } = useToast()
  const [account, setAccount] = useState('')
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [generatedCode, setGeneratedCode] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [showPwd, setShowPwd] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  // 步骤①：用户名/邮箱 → 生成重置码
  const requestCode = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!account.trim()) {
      setError(t('请输入用户名或邮箱'))
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const data = await api.post<ForgotResult>('/auth/forgot-password', { username: account.trim() })
      setGeneratedCode(data.code)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('获取重置码失败，请稍后重试'))
    } finally {
      setSubmitting(false)
    }
  }

  // 步骤②：重置码 + 新密码 → 重置
  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!code || !newPassword || !confirm) {
      setError(t('请填写所有字段'))
      return
    }
    if (newPassword !== confirm) {
      setError(t('两次输入的密码不一致'))
      return
    }
    if (newPassword.length < 6 || !/[a-zA-Z]/.test(newPassword) || !/\d/.test(newPassword)) {
      setError(t('新密码需至少 6 位，包含字母和数字'))
      return
    }
    // 密码 ≠ 用户名（仅当账号字段是用户名时可比；邮箱无对应用户名，交给后端）
    if (!account.includes('@') && newPassword.toLowerCase() === account.trim().toLowerCase()) {
      setError(t('新密码不能与用户名相同'))
      return
    }
    setSubmitting(true)
    setError('')
    try {
      await api.post('/auth/reset-password', {
        username: account.trim(),
        code: code.trim(),
        newPassword,
      })
      toast(t('密码重置成功，请用新密码登录'))
      navigate('/login')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('重置失败，请稍后重试'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <AuthBrand />

        <h2 className="auth-subtitle">{t('找回密码')}</h2>

        {!generatedCode ? (
          <form onSubmit={requestCode}>
            <div className="form-group">
              <label className="sr-only" htmlFor="forgot-account">{t('用户名或邮箱')}</label>
              <input
                id="forgot-account"
                className="form-input"
                placeholder={t('用户名或邮箱')}
                value={account}
                onChange={(e) => setAccount(e.target.value)}
                autoComplete="username"
                aria-describedby={error ? 'forgot-error' : undefined}
              />
              <div className="form-hint">{t('输入注册时使用的用户名或邮箱')}</div>
            </div>

            {error && <div id="forgot-error" className="form-error" role="alert" style={{ marginBottom: 12 }}>{error}</div>}

            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting ? t('生成中…') : t('获取重置码')}
            </button>
          </form>
        ) : (
          <form onSubmit={onSubmit}>
            <div
              className="form-hint"
              style={{
                marginBottom: 16,
                padding: 'var(--gift-space-md)',
                background: 'var(--gift-brand-light)',
                color: 'var(--gift-brand)',
                borderRadius: 'var(--gift-radius-md)',
              }}
            >
              {t('重置码已生成：')}<strong>{generatedCode}</strong>
              <br />
              {t('演示模式直接显示，生产环境将通过邮件发送；请在 15 分钟内完成重置。')}
            </div>

            <div className="form-group">
              <label className="sr-only" htmlFor="forgot-code">{t('6 位重置码')}</label>
              <input
                id="forgot-code"
                className="form-input"
                placeholder={t('6 位重置码')}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                maxLength={6}
                inputMode="numeric"
                autoComplete="one-time-code"
                aria-describedby={error ? 'forgot-error' : undefined}
              />
            </div>
            <div className="form-group">
              <div className="pwd-wrap">
                <label className="sr-only" htmlFor="forgot-new">{t('新密码')}</label>
                <input
                  id="forgot-new"
                  className="form-input"
                  type={showPwd ? 'text' : 'password'}
                  placeholder={t('新密码')}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  aria-describedby={error ? 'forgot-error' : undefined}
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
              <div className="form-hint">{t('至少 6 位，需包含字母和数字')}</div>
            </div>
            <div className="form-group">
              <div className="pwd-wrap">
                <label className="sr-only" htmlFor="forgot-confirm">{t('确认新密码')}</label>
                <input
                  id="forgot-confirm"
                  className="form-input"
                  type={showConfirm ? 'text' : 'password'}
                  placeholder={t('确认新密码')}
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  autoComplete="new-password"
                  aria-describedby={confirm && newPassword !== confirm ? 'forgot-mismatch' : error ? 'forgot-error' : undefined}
                />
                <button
                  type="button"
                  className="pwd-toggle"
                  onClick={() => setShowConfirm(v => !v)}
                  aria-label={showConfirm ? t('隐藏密码') : t('显示密码')}
                >
                  {showConfirm ? '🙈' : '👁️'}
                </button>
              </div>
              {confirm && newPassword !== confirm && (
                <div id="forgot-mismatch" className="form-error" role="alert">{t('两次输入的密码不一致')}</div>
              )}
            </div>

            {error && <div id="forgot-error" className="form-error" role="alert" style={{ marginBottom: 12 }}>{error}</div>}

            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting ? t('重置中…') : t('重置密码')}
            </button>
          </form>
        )}

        <div className="auth-footer">
          <span>{t('想起来了？')}</span>
          <Link to="/login">{t('返回登录')}</Link>
        </div>
      </div>
    </div>
  )
}
