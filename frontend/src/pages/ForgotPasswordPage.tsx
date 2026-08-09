// 文案暂未接入 i18n（示范迁移仅 Header/登录页/Toast 公共文案）：后续按 i18n.ts 迁移指南接入
import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useToast } from '../components/Toast'

interface ForgotResult {
  code: string
  expiresIn: number
}

export default function ForgotPasswordPage() {
  const navigate = useNavigate()
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
      setError('请输入用户名或邮箱')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const data = await api.post<ForgotResult>('/auth/forgot-password', { username: account.trim() })
      setGeneratedCode(data.code)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '获取重置码失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  // 步骤②：重置码 + 新密码 → 重置
  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!code || !newPassword || !confirm) {
      setError('请填写所有字段')
      return
    }
    if (newPassword !== confirm) {
      setError('两次输入的密码不一致')
      return
    }
    if (newPassword.length < 6 || !/[a-zA-Z]/.test(newPassword) || !/\d/.test(newPassword)) {
      setError('新密码需至少 6 位，包含字母和数字')
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
      toast('密码重置成功，请用新密码登录')
      navigate('/login')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '重置失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <div className="auth-logo">🎁</div>
          <h1 className="auth-title">互送礼物</h1>
          <p className="auth-slogan">和朋友们交换惊喜</p>
        </div>

        <h2 className="auth-subtitle">找回密码</h2>

        {!generatedCode ? (
          <form onSubmit={requestCode}>
            <div className="form-group">
              <label className="sr-only" htmlFor="forgot-account">用户名或邮箱</label>
              <input
                id="forgot-account"
                className="form-input"
                placeholder="用户名或邮箱"
                value={account}
                onChange={(e) => setAccount(e.target.value)}
                autoComplete="username"
                aria-describedby={error ? 'forgot-error' : undefined}
              />
              <div className="form-hint">输入注册时使用的用户名或邮箱</div>
            </div>

            {error && <div id="forgot-error" className="form-error" role="alert" style={{ marginBottom: 12 }}>{error}</div>}

            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting ? '生成中…' : '获取重置码'}
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
              重置码已生成：<strong>{generatedCode}</strong>
              <br />
              演示模式直接显示，生产环境将通过邮件发送；请在 15 分钟内完成重置。
            </div>

            <div className="form-group">
              <label className="sr-only" htmlFor="forgot-code">6 位重置码</label>
              <input
                id="forgot-code"
                className="form-input"
                placeholder="6 位重置码"
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
                <label className="sr-only" htmlFor="forgot-new">新密码</label>
                <input
                  id="forgot-new"
                  className="form-input"
                  type={showPwd ? 'text' : 'password'}
                  placeholder="新密码"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  aria-describedby={error ? 'forgot-error' : undefined}
                />
                <button
                  type="button"
                  className="pwd-toggle"
                  onClick={() => setShowPwd(v => !v)}
                  aria-label={showPwd ? '隐藏密码' : '显示密码'}
                >
                  {showPwd ? '🙈' : '👁️'}
                </button>
              </div>
              <div className="form-hint">至少 6 位，需包含字母和数字</div>
            </div>
            <div className="form-group">
              <div className="pwd-wrap">
                <label className="sr-only" htmlFor="forgot-confirm">确认新密码</label>
                <input
                  id="forgot-confirm"
                  className="form-input"
                  type={showConfirm ? 'text' : 'password'}
                  placeholder="确认新密码"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  autoComplete="new-password"
                  aria-describedby={confirm && newPassword !== confirm ? 'forgot-mismatch' : error ? 'forgot-error' : undefined}
                />
                <button
                  type="button"
                  className="pwd-toggle"
                  onClick={() => setShowConfirm(v => !v)}
                  aria-label={showConfirm ? '隐藏密码' : '显示密码'}
                >
                  {showConfirm ? '🙈' : '👁️'}
                </button>
              </div>
              {confirm && newPassword !== confirm && (
                <div id="forgot-mismatch" className="form-error" role="alert">两次输入的密码不一致</div>
              )}
            </div>

            {error && <div id="forgot-error" className="form-error" role="alert" style={{ marginBottom: 12 }}>{error}</div>}

            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting ? '重置中…' : '重置密码'}
            </button>
          </form>
        )}

        <div className="auth-footer">
          <span>想起来了？</span>
          <Link to="/login">返回登录</Link>
        </div>
      </div>
    </div>
  )
}
