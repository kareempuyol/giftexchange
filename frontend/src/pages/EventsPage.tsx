// 文案暂未接入 i18n（示范迁移仅 Header/登录页/Toast 公共文案）：后续按 i18n.ts 迁移指南接入
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, EventInfo } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Badge from '../components/Badge'
import SafeImage from '../components/SafeImage'
import { useToast } from '../components/Toast'
import Modal from '../components/Modal'
import { formatDeadline, formatMoney } from '../utils/format'

function statusBadge(status: string) {
  if (status === 'open') return <Badge tone="success">报名中</Badge>
  return <Badge tone="gold">已抽签</Badge>
}

/** 从剪贴板文本识别邀请码：完整分享链接（/events/<code>）或纯 6 位字母数字 */
function detectInviteCode(text: string): string | null {
  const t = (text || '').trim()
  if (!t) return null
  const urlMatch = t.match(/\/events\/([A-Za-z0-9-]{6,40})/)
  if (urlMatch) return urlMatch[1]
  if (/^[A-Za-z0-9]{6}$/.test(t)) return t
  return null
}

// 下拉刷新参数
const PULL_THRESHOLD = 72
const PULL_MAX = 96
const PULL_HOLD = 44
type PullState = 'idle' | 'pulling' | 'ready' | 'refreshing'

export default function EventsPage() {
  const { user } = useAuth()
  const { toast } = useToast()
  const navigate = useNavigate()
  const [tab, setTab] = useState<'mine' | 'joined' | 'public' | 'archived'>('mine')
  const [events, setEvents] = useState<EventInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  // 恢复操作在途的活动码（防连点）
  const [restoring, setRestoring] = useState<Record<string, boolean>>({})
  const [search, setSearch] = useState('')
  // 「用邀请码加入」弹窗
  const [joinOpen, setJoinOpen] = useState(false)
  const [joinCode, setJoinCode] = useState('')

  // ===== 下拉刷新（移动端）=====
  // React 合成 touchmove 是 passive 监听，preventDefault 无效，
  // 必须在容器上挂原生非 passive 监听来接管下拉手势。
  const containerRef = useRef<HTMLDivElement>(null)
  const pull = useRef<{ state: PullState; dist: number; startY: number | null; dragging: boolean }>({
    state: 'idle',
    dist: 0,
    startY: null,
    dragging: false,
  })
  const [pullState, setPullState] = useState<PullState>('idle')
  const [pullDist, setPullDist] = useState(0)
  const loadRef = useRef<(t: typeof tab) => Promise<void>>(async () => {})
  const loadingRef = useRef(loading)
  loadingRef.current = loading

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const onStart = (e: TouchEvent) => {
      const p = pull.current
      if (p.state === 'refreshing' || loadingRef.current) return
      if (window.scrollY > 0) return // 不在页面顶部时不进入下拉
      p.startY = e.touches[0].clientY
      p.dragging = true
    }

    const onMove = (e: TouchEvent) => {
      const p = pull.current
      if (!p.dragging || p.startY == null) return
      const dy = e.touches[0].clientY - p.startY
      if (dy <= 0 || window.scrollY > 0) {
        // 上滑/滚动离开顶部：复位并放行
        if (p.dist !== 0 || p.state !== 'idle') {
          p.dist = 0
          p.state = 'idle'
          setPullDist(0)
          setPullState('idle')
        }
        p.dragging = false
        return
      }
      // 下拉：接管手势（阻止原生滚动/原生下拉刷新），带阻尼
      e.preventDefault()
      p.dist = Math.min(dy * 0.45, PULL_MAX)
      p.state = p.dist >= PULL_THRESHOLD ? 'ready' : 'pulling'
      setPullDist(p.dist)
      setPullState(p.state)
    }

    const onEnd = () => {
      const p = pull.current
      if (!p.dragging) return
      p.dragging = false
      p.startY = null
      if (p.state === 'ready') {
        p.state = 'refreshing'
        p.dist = PULL_HOLD
        setPullState('refreshing')
        setPullDist(PULL_HOLD)
        loadRef.current().finally(() => {
          p.dist = 0
          p.state = 'idle'
          setPullDist(0)
          setPullState('idle')
        })
      } else {
        p.dist = 0
        p.state = 'idle'
        setPullDist(0)
        setPullState('idle')
      }
    }

    el.addEventListener('touchstart', onStart, { passive: true })
    el.addEventListener('touchmove', onMove, { passive: false })
    el.addEventListener('touchend', onEnd)
    el.addEventListener('touchcancel', onEnd)

    // 关闭浏览器原生下拉刷新，避免与自定义 PTR 双触发（Chrome Android / iOS 16.4+）
    const prevOverscroll = document.body.style.overscrollBehaviorY
    document.body.style.overscrollBehaviorY = 'contain'
    return () => {
      el.removeEventListener('touchstart', onStart)
      el.removeEventListener('touchmove', onMove)
      el.removeEventListener('touchend', onEnd)
      el.removeEventListener('touchcancel', onEnd)
      document.body.style.overscrollBehaviorY = prevOverscroll
    }
  }, [])

  // ===== 剪贴板邀请码检测（每会话一次）：复制邀请码后进入列表页自动弹窗 =====
  useEffect(() => {
    if (!('clipboard' in navigator) || typeof navigator.clipboard.readText !== 'function') return
    try {
      if (sessionStorage.getItem('gift-clip-prompted')) return
    } catch {
      return
    }
    let cancelled = false
    navigator.clipboard
      .readText()
      .then((text) => {
        if (cancelled) return
        const code = detectInviteCode(text)
        if (!code) return
        try {
          sessionStorage.setItem('gift-clip-prompted', '1')
        } catch {
          /* ignore */
        }
        setJoinCode(code)
        setJoinOpen(true)
        toast(`检测到剪贴板邀请码 ${code}，已为你填入`)
      })
      .catch(() => {
        /* 无权限/非安全上下文：静默忽略 */
      })
    return () => {
      cancelled = true
    }
  }, [toast])

  const onJoinByCode = () => {
    const raw = joinCode.trim()
    if (!raw) {
      toast('请输入邀请码', 'error')
      return
    }
    // 6 位短码统一大写（uuid 含连字符则原样使用）
    const target = raw.includes('-') ? raw : raw.toUpperCase()
    setJoinOpen(false)
    navigate(`/events/${target}`)
  }

  // 打开邀请码弹窗时尝试从剪贴板预填
  const openJoin = async () => {
    setJoinOpen(true)
    if (joinCode) return
    try {
      if (navigator.clipboard && typeof navigator.clipboard.readText === 'function') {
        const text = await navigator.clipboard.readText()
        const code = detectInviteCode(text)
        if (code) setJoinCode(code)
      }
    } catch {
      /* 忽略 */
    }
  }

  const load = async (t: typeof tab) => {
    setLoading(true)
    setLoadError('')
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
    } catch (err) {
      // 网络/服务异常：不误导成空态，显示错误 + 重试
      setEvents([])
      setLoadError(err instanceof Error ? err.message : '加载失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }
  loadRef.current = load

  useEffect(() => {
    load(tab)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  const onSearch = () => load('public')

  const onRestore = async (code: string) => {
    if (restoring[code]) return
    setRestoring((prev) => ({ ...prev, [code]: true }))
    try {
      await api.post(`/events/${code}/unarchive`)
      toast('活动已恢复')
      load(tab)
    } catch (err) {
      toast(err instanceof Error ? err.message : '恢复失败', 'error')
    } finally {
      setRestoring((prev) => ({ ...prev, [code]: false }))
    }
  }

  return (
    <div className="page-container" ref={containerRef}>
      {/* 下拉刷新指示器（高度随下拉距离伸展） */}
      <div
        className={`ptr-indicator${pullState === 'ready' ? ' ptr-ready' : ''}${pullState === 'refreshing' ? ' ptr-refreshing' : ''}`}
        style={{ height: pullDist }}
        aria-hidden={pullState === 'idle'}
      >
        <span className="ptr-spinner" aria-hidden="true" />
        <span>
          {pullState === 'ready' ? '松开刷新' : pullState === 'refreshing' ? '刷新中…' : '下拉刷新'}
        </span>
      </div>

      <div className="page-header">
        <h1 className="page-title">{tab === 'public' ? '发现活动' : tab === 'joined' ? '我参与的' : tab === 'archived' ? '已归档' : '我的活动'}</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Link to="/events/new" className="btn btn-primary btn-sm">+ 创建活动</Link>
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
            aria-pressed={tab === key}
            onClick={() => { setTab(key); setSearch('') }}
          >
            {label}
          </button>
        ))}
        {(tab === 'mine' || tab === 'archived') && (
          <button
            className={`btn btn-ghost btn-sm${tab === 'archived' ? ' tab-active' : ''}`}
            aria-pressed={tab === 'archived'}
            onClick={() => { setTab('archived'); setSearch('') }}
          >
            已归档
          </button>
        )}
      </div>

      {tab === 'public' && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <label className="sr-only" htmlFor="events-search">搜索活动</label>
          <input
            id="events-search"
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
        <div className="page-loading"><span className="spinner" aria-hidden="true" />加载中…</div>
      ) : loadError ? (
        <div className="empty-state gift-card">
          <div className="empty-title">加载失败</div>
          <p className="empty-sub">{loadError}</p>
          <button
            className="btn btn-secondary btn-sm"
            style={{ width: 'auto', marginTop: 12 }}
            onClick={() => load(tab)}
          >
            重试
          </button>
        </div>
      ) : events.length === 0 ? (
        <div className="empty-state gift-card">
          <div className="empty-title">
            {tab === 'mine' ? '你还没有创建活动' : tab === 'joined' ? '你还没有参与活动' : tab === 'archived' ? '没有已归档的活动' : '没有找到活动'}
          </div>
          {tab === 'mine' && (
            <>
              <p className="empty-sub">发起一个互送礼物活动，邀请朋友一起玩 🎁</p>
              <Link to="/events/new" className="btn btn-primary btn-sm" style={{ width: 'auto', marginTop: 12 }}>
                创建第一个活动
              </Link>
            </>
          )}
          {tab === 'joined' && (
            <>
              <p className="empty-sub">朋友分享了邀请码？输入后即可加入</p>
              <button
                className="btn btn-secondary btn-sm"
                style={{ width: 'auto', marginTop: 12 }}
                onClick={openJoin}
              >
                用邀请码加入
              </button>
            </>
          )}
          {tab === 'public' && (
            <>
              <p className="empty-sub">{search ? '换个关键词试试' : '还没有公开活动，发起一个让大家一起玩吧'}</p>
              <Link to="/events/new" className="btn btn-primary btn-sm" style={{ width: 'auto', marginTop: 12 }}>
                创建公开活动
              </Link>
            </>
          )}
        </div>
      ) : (
        <div className="event-list">
          {events.map((ev) => (
            <div key={ev.code} className="event-list-row" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Link to={`/events/${ev.code}`} className="event-card" style={{ flex: 1, minWidth: 0 }}>
                {ev.coverImage && (
                  <SafeImage
                    src={ev.coverImage}
                    alt=""
                    loading="lazy"
                    style={{ width: 56, height: 56, borderRadius: 12, objectFit: 'cover', flexShrink: 0 }}
                  />
                )}
                <div className="event-card-main">
                  <div className="event-card-title">
                    {ev.title} {statusBadge(ev.status)}
                    {tab === 'archived' && <Badge tone="warning">已归档</Badge>}
                  </div>
                  <div className="event-card-meta">
                    {ev.note && <span className="event-card-note">{ev.note}</span>}
                    <span>{formatMoney(ev.budget)}</span>
                    <span>{ev.participantCount} 人参与</span>
                    {ev.drawDate && <span>报名 {formatDeadline(ev.drawDate)}</span>}
                  </div>
                </div>
                <div className="event-card-arrow">›</div>
              </Link>
              {tab === 'archived' && (
                <button
                  className="btn btn-secondary btn-sm"
                  style={{ flexShrink: 0, width: 'auto' }}
                  onClick={() => onRestore(ev.code)}
                  disabled={!!restoring[ev.code]}
                >
                  {restoring[ev.code] ? '恢复中…' : '恢复'}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {joinOpen && (
        <Modal title="用邀请码加入" onClose={() => setJoinOpen(false)}>
          <p style={{ marginTop: 8, color: 'var(--gift-text-secondary)' }}>
            输入朋友分享的 6 位邀请码，即可进入活动
          </p>
          <label className="sr-only" htmlFor="join-code-input">邀请码</label>
          <input
            id="join-code-input"
            className="form-input"
            style={{ marginTop: 12 }}
            placeholder="例如：ABC123"
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && onJoinByCode()}
            maxLength={40}
            autoFocus
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setJoinOpen(false)}>
              取消
            </button>
            <button className="btn btn-primary" style={{ flex: 1 }} onClick={onJoinByCode}>
              加入
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}
