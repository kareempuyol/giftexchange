import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, NotificationItem } from '../api/client'
import { useAuth } from '../auth/AuthContext'

/** 全局顶栏：品牌 + 导航 + 通知铃铛 + 用户菜单 */
export default function Header() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [notifs, setNotifs] = useState<NotificationItem[]>([])
  const [showNotif, setShowNotif] = useState(false)
  const [unread, setUnread] = useState(0)
  const notifRef = useRef<HTMLDivElement>(null)

  // 拉通知（仅登录后）
  useEffect(() => {
    if (!user) return
    const load = async () => {
      try {
        const data = await api.get<{ items: NotificationItem[]; unread: number }>('/notifications')
        setNotifs(data.items || [])
        setUnread(data.unread || 0)
      } catch { /* 静默 */ }
    }
    load()
    const timer = setInterval(load, 30000)
    return () => clearInterval(timer)
  }, [user])

  // 点击外部关闭通知面板
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) setShowNotif(false)
    }
    document.addEventListener('click', onClick)
    return () => document.removeEventListener('click', onClick)
  }, [])

  const markRead = async (id: number) => {
    try {
      await api.post('/notifications/read', { id })
      setNotifs(prev => prev.map(n => n.id === id ? { ...n, read: true } : n))
      setUnread(prev => Math.max(0, prev - 1))
    } catch { /* 静默 */ }
  }

  const markAllRead = async () => {
    try {
      await api.post('/notifications/read', {})
      setNotifs(prev => prev.map(n => ({ ...n, read: true })))
      setUnread(0)
    } catch { /* 静默 */ }
  }

  const onLogout = () => {
    logout()
    navigate('/login')
  }

  if (!user) return null

  return (
    <header className="app-header">
      <div className="app-header-inner">
        <Link to="/events" className="app-brand">🎁 互送礼物</Link>

        <nav className="app-nav">
          <Link to="/events" className="app-nav-link">我的活动</Link>
          <Link to="/events/new" className="app-nav-link app-nav-cta">+ 创建</Link>
        </nav>

        <div className="app-header-right">
          {/* 通知铃铛 */}
          <div className="notif-wrap" ref={notifRef}>
            <button
              className="notif-bell"
              onClick={() => setShowNotif(v => !v)}
              aria-label="通知"
              title="通知"
            >
              🔔
              {unread > 0 && <span className="notif-badge">{unread > 9 ? '9+' : unread}</span>}
            </button>

            {showNotif && (
              <div className="notif-panel">
                <div className="notif-panel-header">
                  <span>通知</span>
                  {unread > 0 && (
                    <button className="notif-mark-all" onClick={markAllRead}>全部已读</button>
                  )}
                </div>
                {notifs.length === 0 ? (
                  <div className="notif-empty">暂无通知</div>
                ) : (
                  <div className="notif-list">
                    {notifs.slice(0, 20).map(n => (
                      <div key={n.id} className={`notif-item${n.read ? '' : ' unread'}`} onClick={() => markRead(n.id)}>
                        <div className="notif-title">{n.title}</div>
                        {n.message && <div className="notif-msg">{n.message}</div>}
                        <div className="notif-meta">
                          {n.eventCode && (
                            <Link to={`/events/${n.eventCode}`} onClick={(e) => e.stopPropagation()}>
                              查看活动 ↗
                            </Link>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 用户菜单 */}
          <div className="app-user">
            <Link to="/profile" className="app-username" title="个人资料" style={{ cursor: 'pointer' }}>
              {user.displayName || user.username} ⚙️
            </Link>
            <button className="btn btn-ghost btn-sm" onClick={onLogout}>退出</button>
          </div>
        </div>
      </div>
    </header>
  )
}
