import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, EventInfo } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Badge from '../components/Badge'
import { useToast } from '../components/Toast'

function statusBadge(status: string) {
  if (status === 'open') return <Badge tone="success">报名中</Badge>
  return <Badge tone="gold">已抽签</Badge>
}

export default function EventsPage() {
  const { user, logout } = useAuth()
  const { toast } = useToast()
  const [tab, setTab] = useState<'mine' | 'joined' | 'public' | 'archived'>('mine')
  const [events, setEvents] = useState<EventInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  const load = async (t: typeof tab) => {
    setLoading(true)
    try {
      if (t === 'mine') {
        const data = await api.get<EventInfo[]>('/events/mine')
        setEvents(data)
      } else if (t === 'joined') {
        const data = await api.get<EventInfo[]>('/events/joined')
        setEvents(data)
      } else if (t === 'archived') {
        const data = await api.get<EventInfo[]>('/events/archived')
        setEvents(data)
      } else {
        const data = await api.get<{ events: EventInfo[] }>(
          `/events/public?search=${encodeURIComponent(search)}`
        )
        setEvents(data.events)
      }
    } catch {
      setEvents([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(tab)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  const onSearch = () => load('public')

  const onRestore = async (code: string) => {
    try {
      await api.post(`/events/${code}/unarchive`)
      toast('活动已恢复')
      load(tab)
    } catch {
      toast('恢复失败', 'error')
    }
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">互送礼物</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Link to="/events/new" className="btn btn-primary btn-sm">+ 创建活动</Link>
          <button className="btn btn-ghost btn-sm" onClick={logout}>退出</button>
        </div>
      </div>

      {user && (
        <p style={{ color: 'var(--gift-text-secondary)', marginBottom: 16 }}>
          你好，{user.displayName || user.username}
        </p>
      )}

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {([
          ['mine', '我创建的'],
          ['joined', '我参与的'],
          ['public', '发现活动'],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            className={`btn btn-ghost btn-sm${tab === key ? ' tab-active' : ''}`}
            onClick={() => { setTab(key); setSearch('') }}
          >
            {label}
          </button>
        ))}
        {(tab === 'mine' || tab === 'archived') && (
          <button
            className={`btn btn-ghost btn-sm${tab === 'archived' ? ' tab-active' : ''}`}
            onClick={() => { setTab('archived'); setSearch('') }}
          >
            已归档
          </button>
        )}
      </div>

      {tab === 'public' && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <input
            className="form-input"
            style={{ flex: 1 }}
            placeholder="搜索活动名称 / 邀请码"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && onSearch()}
          />
          <button className="btn btn-secondary btn-sm" onClick={onSearch}>搜索</button>
        </div>
      )}

      {loading ? (
        <div className="page-loading">加载中…</div>
      ) : events.length === 0 ? (
        <div className="empty-state gift-card">
          <div className="empty-title">
            {tab === 'mine' ? '你还没有创建活动' : tab === 'joined' ? '你还没有参与活动' : tab === 'archived' ? '没有已归档的活动' : '没有找到活动'}
          </div>
          {tab === 'mine' && (
            <Link to="/events/new" className="btn btn-primary btn-sm" style={{ width: 'auto', marginTop: 12 }}>
              创建第一个活动
            </Link>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {events.map((ev) => (
            <div key={ev.code} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Link to={`/events/${ev.code}`} className="event-card" style={{ flex: 1, minWidth: 0 }}>
                {ev.coverImage && (
                  <img
                    src={ev.coverImage}
                    alt=""
                    style={{ width: 56, height: 56, borderRadius: 12, objectFit: 'cover', flexShrink: 0 }}
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                )}
                <div className="event-card-main">
                  <div className="event-card-title">
                    {ev.title} {statusBadge(ev.status)}
                    {tab === 'archived' && <Badge tone="warning">已归档</Badge>}
                  </div>
                  <div className="event-card-meta">
                    {ev.note && <span className="event-card-note">{ev.note}</span>}
                    <span>预算 ¥{ev.budget}</span>
                    <span>{ev.participantCount} 人参与</span>
                    {ev.drawDate && <span>截止 {new Date(ev.drawDate).toLocaleDateString('zh-CN')}</span>}
                  </div>
                </div>
                <div className="event-card-arrow">›</div>
              </Link>
              {tab === 'archived' && (
                <button className="btn btn-secondary btn-sm" style={{ flexShrink: 0, width: 'auto' }} onClick={() => onRestore(ev.code)}>
                  恢复
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
