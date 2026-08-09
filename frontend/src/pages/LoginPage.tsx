import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [showPwd, setShowPwd] = useState(false)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) {
      setError('请输入用户名和密码')
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
      setError(err instanceof ApiError ? err.message : '登录失败，请稍后重试')
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

        <h2 className="auth-subtitle">登录</h2>

        <form onSubmit={onSubmit}>
          <div className="form-group">
            <input
              className="form-input"
              placeholder="用户名"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
          </div>
          <div className="form-group">
            <div className="pwd-wrap">
              <input
                className="form-input"
                type={showPwd ? 'text' : 'password'}
                placeholder="密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
              <button
                type="button"
                className="pwd-toggle"
                onClick={() => setShowPwd(v => !v)}
                aria-label={showPwd ? '隐藏密码' : '显示密码'}
                tabIndex={-1}
              >
                {showPwd ? '🙈' : '👁️'}
              </button>
            </div>
            <div style={{ marginTop: 8, textAlign: 'right' }}>
              <Link to="/forgot-password" className="form-hint">忘记密码？</Link>
            </div>
          </div>

          {error && <div className="form-error" style={{ marginBottom: 12 }}>{error}</div>}

          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? '登录中…' : '登录'}
          </button>
        </form>

        <div className="auth-footer">
          <span>还没有账号？</span>
          <Link to="/register">立即注册</Link>
        </div>
      </div>
    </div>
  )
}
