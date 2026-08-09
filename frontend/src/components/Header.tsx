import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api, NotificationItem } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useToast } from '../components/Toast'
import SafeImage from '../components/SafeImage'
import { t, useLocale } from '../i18n'
import { clearListState } from '../utils/listState'

/** 全局顶栏：品牌 + 导航 + 通知铃铛 + 用户菜单 */
export default function Header() {
  const { user, logout } = useAuth()
  const { toast } = useToast()
  const navigate = useNavigate()
  useLocale() // 订阅语言切换：setLocale 后重渲染（i18n 示范迁移）
  const [notifs, setNotifs] = useState<NotificationItem[]>([])
  const [showNotif, setShowNotif] = useState(false)
  const [unread, setUnread] = useState(0)
  const [notifLoaded, setNotifLoaded] = useState(false)
  const notifRef = useRef<HTMLDivElement>(null)

  // 拉通知（仅登录后）
  useEffect(() => {
    if (!user) return
    const load = async () => {
      try {
        const data = await api.get<{ items: NotificationItem[]; unread: number }>('/notifications')
        setNotifs(data.items || [])
        setUnread(data.unread || 0)
      } catch { /* 静默：铃铛无角标，面板内显示加载失败兜底 */ } finally {
        setNotifLoaded(true)
      }
    }
    load()
    const timer = setInterval(load, 30000)
    return () => clearInterval(timer)
  }, [user])

  // 点击外部关闭通知面板 + ESC 关闭
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) setShowNotif(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowNotif(false)
    }
    document.addEventListener('click', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('click', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [])

  const markRead = async (id: number) => {
    try {
      await api.post('/notifications/read', { ids: [id] })
      setNotifs(prev => prev.map(n => n.id === id ? { ...n, read: true } : n))
      setUnread(prev => Math.max(0, prev - 1))
    } catch { /* 静默 */ }
  }

  const markAllRead = async () => {
    try {
      await api.post('/notifications/read', {})
      setNotifs(prev => prev.map(n => ({ ...n, read: true })))
      setUnread(0)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('操作失败，请重试'), 'error')
    }
  }

  const clearRead = async () => {
    try {
      await api.post('/notifications/clear')
      const data = await api.get<{ items: NotificationItem[]; unread: number }>('/notifications')
      setNotifs(data.items || [])
      setUnread(data.unread || 0)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('操作失败，请重试'), 'error')
    }
  }

  const onLogout = () => {
    logout()
    navigate('/login')
  }

  if (!user) return null

  return (
    <header className="app-header">
      <div className="app-header-inner">
        <Link to="/events" className="app-brand" onClick={clearListState}>🎁 {t('互送礼物')}</Link>

        <nav className="app-nav" aria-label={t('主导航')}>
          <Link to="/events" className="app-nav-link" onClick={clearListState} aria-current={location.pathname === '/events' ? 'page' : undefined}>{t('我的活动')}</Link>
          <Link to="/events/new" className="app-nav-link app-nav-cta" aria-current={location.pathname.startsWith('/events/new') ? 'page' : undefined}>+ {t('创建')}</Link>
        </nav>

        <div className="app-header-right">
          {/* 通知铃铛 */}
          <div className="notif-wrap" ref={notifRef}>
            <button
              className="notif-bell"
              onClick={() => setShowNotif(v => !v)}
              aria-label={t('通知')}
              aria-haspopup="true"
              aria-expanded={showNotif}
              aria-controls="notif-panel"
              title={t('通知')}
            >
              🔔
              {unread > 0 && <span className="notif-badge">{unread > 9 ? '9+' : unread}</span>}
            </button>

            {showNotif && (
              <div id="notif-panel" className="notif-panel" role="region" aria-label={t('通知面板')}>
                <div className="notif-panel-header">
                  <span>{t('通知')}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    {unread > 0 && (
                      <button className="notif-mark-all" onClick={markAllRead}>{t('全部已读')}</button>
                    )}
                    <button className="notif-mark-all" onClick={clearRead}>{t('清空已读')}</button>
                  </div>
                </div>
                {!notifLoaded ? (
                  <div className="notif-empty">{t('加载中…')}</div>
                ) : notifs.length === 0 ? (
                  <div className="notif-empty">{t('暂无通知')}</div>
                ) : (
                <div className="notif-list">
                    {notifs.slice(0, 20).map(n => (
                      <div
                        key={n.id}
                        className={`notif-item${n.read ? '' : ' unread'}`}
                        onClick={() => markRead(n.id)}
                        {...(n.eventCode
                          ? {}
                          : {
                              role: 'button',
                              tabIndex: 0,
                              'aria-label': t('标记已读：{title}', { title: n.title }),
                              onKeyDown: (e: React.KeyboardEvent) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                  e.preventDefault()
                                  markRead(n.id)
                                }
                              },
                            })}
                      >
                        <div className="notif-title">{n.title}</div>
                        {n.message && <div className="notif-msg">{n.message}</div>}
                        <div className="notif-meta">
                          {n.eventCode && (
                            <Link to={`/events/${n.eventCode}`} onClick={(e) => e.stopPropagation()}>
                              {t('查看活动 ↗')}
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
            <Link to="/profile" className="app-username" title={t('个人资料')} style={{ cursor: 'pointer' }}>
              {user.avatarUrl ? (
                <SafeImage src={user.avatarUrl} alt="" className="app-avatar" />
              ) : (
                <span className="app-avatar app-avatar-fallback">
                  {(user.displayName || user.username || '?').slice(0, 1).toUpperCase()}
                </span>
              )}
              <span className="app-username-text">{user.displayName || user.username}</span>
            </Link>
            <button className="btn btn-ghost btn-sm" onClick={onLogout}>{t('退出')}</button>
          </div>
        </div>
      </div>
    </header>
  )
}
