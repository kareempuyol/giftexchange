import { useState } from 'react'
import { useNavigate, Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'

export default function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
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
      setError('请填写所有字段')
      return
    }
    if (password !== confirm) {
      setError('两次输入的密码不一致')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      await register(username, email, password)
      const from = params.get('from')
      navigate(from ? `/${from}` : '/events', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '注册失败，请稍后重试')
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

        <h2 className="auth-subtitle">注册</h2>
        <p className="form-hint" style={{ marginBottom: 16 }}>加入礼物互赠的乐趣</p>

        <form onSubmit={onSubmit}>
          <div className="form-group">
            <label className="sr-only" htmlFor="register-username">用户名</label>
            <input
              id="register-username"
              className="form-input"
              placeholder="用户名"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-describedby={error ? 'register-error' : undefined}
            />
            <div className="form-hint">至少 2 个字符</div>
          </div>
          <div className="form-group">
            <label className="sr-only" htmlFor="register-email">邮箱</label>
            <input
              id="register-email"
              className="form-input"
              type="email"
              placeholder="邮箱"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-describedby={error ? 'register-error' : undefined}
            />
            <div className="form-hint">用于登录和找回密码</div>
          </div>
          <div className="form-group">
            <div className="pwd-wrap">
              <label className="sr-only" htmlFor="register-password">密码</label>
              <input
                id="register-password"
                className="form-input"
                type={showPwd ? 'text' : 'password'}
                placeholder="密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-describedby={error ? 'register-error' : undefined}
              />
              <button type="button" className="pwd-toggle" onClick={() => setShowPwd(v => !v)} aria-label={showPwd ? '隐藏密码' : '显示密码'}>
                {showPwd ? '🙈' : '👁️'}
              </button>
            </div>
            <div className="form-hint">至少 6 位，需包含字母和数字</div>
          </div>
          <div className="form-group">
            <div className="pwd-wrap">
              <label className="sr-only" htmlFor="register-confirm">确认密码</label>
              <input
                id="register-confirm"
                className="form-input"
                type={showConfirm ? 'text' : 'password'}
                placeholder="确认密码"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                aria-describedby={confirm && password !== confirm ? 'register-mismatch' : error ? 'register-error' : undefined}
              />
              <button type="button" className="pwd-toggle" onClick={() => setShowConfirm(v => !v)} aria-label={showConfirm ? '隐藏密码' : '显示密码'}>
                {showConfirm ? '🙈' : '👁️'}
              </button>
            </div>
            {confirm && password !== confirm && (
              <div id="register-mismatch" className="form-error" role="alert">两次输入的密码不一致</div>
            )}
          </div>

          {error && <div id="register-error" className="form-error" role="alert" style={{ marginBottom: 12 }}>{error}</div>}

          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? '注册中…' : '注册'}
          </button>
        </form>

        <div className="auth-footer">
          <span>已有账号？</span>
          <Link to="/login">立即登录</Link>
        </div>
      </div>
    </div>
  )
}
