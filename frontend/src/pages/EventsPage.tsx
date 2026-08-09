// 文案暂未接入 i18n（示范迁移仅 Header/登录页/Toast 公共文案）：后续按 i18n.ts 迁移指南接入
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, EventSummary } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Badge from '../components/Badge'
import SafeImage from '../components/SafeImage'
import { useToast } from '../components/Toast'
import Modal from '../components/Modal'
import { formatDeadline, formatMoney } from '../utils/format'
import { LIST_STATE_KEY, readListState } from '../utils/listState'
import type { ListTab } from '../utils/listState'
import { usePageTitle } from '../utils/usePageTitle'
import { t, useLocale } from '../i18n'

/** 列表角标（纯前端计算，EventsPage 全部 tab 共用）：已抽签 → 🎯 已抽签；报名中且参与者 ≥5 → 🔥 热度；否则报名中
 *  注：/events/public 后端只返回 open 活动，因此 🔥 热度主要出现在公开列表，🎯 已抽签出现在我创建的/我参与的列表 */
function heatBadge(status: string, participantCount: number) {
  if (status !== 'open') return <Badge tone="gold">🎯 {t('已抽签')}</Badge>
  if (participantCount >= 5) return <Badge tone="error">🔥 {t('热度')}</Badge>
  return <Badge tone="success">{t('报名中')}</Badge>
}

/** 从剪贴板文本识别邀请码：完整分享链接（/events/<code>）或纯 6 位字母数字 */
function detectInviteCode(text: string): string | null {
  const txt = (text || '').trim()
  if (!txt) return null
  const urlMatch = txt.match(/\/events\/([A-Za-z0-9-]{6,40})/)
  if (urlMatch) return urlMatch[1]
  if (/^[A-Za-z0-9]{6}$/.test(txt)) return txt
  return null
}

// 下拉刷新参数
const PULL_THRESHOLD = 72
const PULL_MAX = 96
const PULL_HOLD = 44
type PullState = 'idle' | 'pulling' | 'ready' | 'refreshing'

// ===== 列表状态保留（详情页返回不丢 tab/搜索/滚动位置）=====
// React Router（BrowserRouter）默认不保留列表状态：离开列表页时把
// tab/search/滚动位置写入 sessionStorage，返回时恢复。
// 状态读写/清理在 utils/listState.ts（Header 显式导航也要用，且它在首屏 bundle）。
// Header 的「我的活动/品牌」是显式导航，会先 clearListState()（见 Header.tsx）直达默认视图。

export default function EventsPage() {
  const { user } = useAuth()
  const { toast } = useToast()
  useLocale()
  usePageTitle('我的活动')
  const navigate = useNavigate()
  const savedState = useRef(readListState())
  const [tab, setTab] = useState<ListTab>(savedState.current?.tab ?? 'mine')
  const [events, setEvents] = useState<EventSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  // 恢复操作在途的活动码（防连点）
  const [restoring, setRestoring] = useState<Record<string, boolean>>({})
  const [search, setSearch] = useState(savedState.current?.search ?? '')
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
  const loadRef = useRef<(tab: typeof tab) => Promise<void>>(async () => {})
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
        toast(t('检测到剪贴板邀请码 {code}，已为你填入', { code }))
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
      toast(t('请输入邀请码'), 'error')
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

  const load = async (tab: typeof tab) => {
    setLoading(true)
    setLoadError('')
    try {
      if (tab === 'mine') {
        const data = await api.get<EventSummary[]>('/events/mine')
        setEvents(data)
      } else if (tab === 'joined') {
        const data = await api.get<EventSummary[]>('/events/joined')
        setEvents(data)
      } else if (tab === 'archived') {
        const data = await api.get<EventSummary[]>('/events/archived')
        setEvents(data)
      } else {
        const data = await api.get<{ events: EventSummary[] }>(
          `/events/public?search=${encodeURIComponent(search)}`
        )
        setEvents(data.events)
      }
    } catch (err) {
      // 网络/服务异常：不误导成空态，显示错误 + 重试
      setEvents([])
      setLoadError(err instanceof Error ? err.message : t('加载失败，请稍后重试'))
    } finally {
      setLoading(false)
    }
  }
  loadRef.current = load

  useEffect(() => {
    load(tab)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  // 返回列表时恢复滚动位置（首次加载完成后执行一次；数据渲染为异步，须等 loading 结束）
  const restoreScrollY = useRef(savedState.current?.scrollY ?? null)
  useEffect(() => {
    if (loading || restoreScrollY.current == null) return
    const y = restoreScrollY.current
    restoreScrollY.current = null
    // 双 rAF：等首帧 + 布局稳定后再滚动，避免被浏览器导航后的滚动重置覆盖
    requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo(0, y)))
  }, [loading])

  // 点击列表项导航离开前记录滚动位置：浏览器在导航提交时会重置文档滚动
  // （被移除的聚焦元素滚动回位），卸载清理时读 window.scrollY 已被污染，必须提前捕获
  const scrollAtNavRef = useRef<number | null>(null)
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const onCaptureClick = () => {
      scrollAtNavRef.current = window.scrollY
    }
    el.addEventListener('click', onCaptureClick, true)
    return () => el.removeEventListener('click', onCaptureClick, true)
  }, [])

  // 离开列表页时保存 tab/搜索/滚动位置，供返回恢复
  useEffect(() => {
    return () => {
      try {
        sessionStorage.setItem(
          LIST_STATE_KEY,
          JSON.stringify({ tab, search, scrollY: scrollAtNavRef.current ?? window.scrollY })
        )
      } catch {
        /* ignore */
      }
    }
  }, [tab, search])

  const onSearch = () => load('public')

  const onRestore = async (code: string) => {
    if (restoring[code]) return
    setRestoring((prev) => ({ ...prev, [code]: true }))
    try {
      await api.post(`/events/${code}/unarchive`)
      toast(t('活动已恢复'))
      load(tab)
    } catch (err) {
      toast(err instanceof Error ? err.message : t('恢复失败'), 'error')
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
          {pullState === 'ready' ? t('松开刷新') : pullState === 'refreshing' ? t('刷新中…') : t('下拉刷新')}
        </span>
      </div>

      <div className="page-header">
        <h1 className="page-title">{tab === 'public' ? t('发现活动') : tab === 'joined' ? t('我参与的') : tab === 'archived' ? t('已归档') : t('我的活动')}</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Link to="/events/new" className="btn btn-primary btn-sm">+ {t('创建活动')}</Link>
        </div>
      </div>

      {user && (
        <p style={{ color: 'var(--gift-text-secondary)', marginBottom: 16 }}>
          {t('你好，{name}', { name: user.displayName || user.username })}
        </p>
      )}

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {([
          ['mine', t('我创建的')],
          ['joined', t('我参与的')],
          ['public', t('发现活动')],
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
            {t('已归档')}
          </button>
        )}
      </div>

      {tab === 'public' && (
        <form
          style={{ display: 'flex', gap: 8, marginBottom: 16 }}
          onSubmit={(e) => { e.preventDefault(); onSearch() }}
        >
          <label className="sr-only" htmlFor="events-search">{t('搜索活动')}</label>
          <input
            id="events-search"
            className="form-input"
            style={{ flex: 1 }}
            placeholder={t('搜索活动名称 / 邀请码')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button type="submit" className="btn btn-secondary btn-sm">{t('搜索')}</button>
        </form>
      )}

      {loading ? (
        <div className="page-loading"><span className="spinner" aria-hidden="true" />{t('加载中…')}</div>
      ) : loadError ? (
        <div className="empty-state gift-card">
          <div className="empty-title">{t('加载失败')}</div>
          <p className="empty-sub">{loadError}</p>
          <button
            className="btn btn-secondary btn-sm"
            style={{ width: 'auto', marginTop: 12 }}
            onClick={() => load(tab)}
          >
            {t('重试')}
          </button>
        </div>
      ) : events.length === 0 ? (
        <div className="empty-state gift-card">
          <div className="empty-title">
            {tab === 'mine' ? t('你还没有创建活动') : tab === 'joined' ? t('你还没有参与活动') : tab === 'archived' ? t('没有已归档的活动') : t('没有找到活动')}
          </div>
          {tab === 'mine' && (
            <>
              <p className="empty-sub">{t('发起一个互送礼物活动，邀请朋友一起玩 🎁')}</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center', marginTop: 12 }}>
                <Link to="/events/new" className="btn btn-primary btn-sm" style={{ width: 'auto' }}>
                  {t('创建第一个活动')}
                </Link>
                <button
                  className="btn btn-secondary btn-sm"
                  style={{ width: 'auto' }}
                  onClick={openJoin}
                >
                  {t('用邀请码加入')}
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ width: 'auto' }}
                  onClick={() => { setTab('public'); setSearch('') }}
                >
                  {t('发现活动')}
                </button>
              </div>
            </>
          )}
          {tab === 'joined' && (
            <>
              <p className="empty-sub">{t('朋友分享了邀请码？输入后即可加入')}</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center', marginTop: 12 }}>
                <button
                  className="btn btn-secondary btn-sm"
                  style={{ width: 'auto' }}
                  onClick={openJoin}
                >
                  {t('用邀请码加入')}
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ width: 'auto' }}
                  onClick={() => { setTab('public'); setSearch('') }}
                >
                  {t('发现活动')}
                </button>
              </div>
            </>
          )}
          {tab === 'public' && (
            <>
              <p className="empty-sub">{search ? t('换个关键词试试') : t('还没有公开活动，发起一个让大家一起玩吧')}</p>
              <Link to="/events/new" className="btn btn-primary btn-sm" style={{ width: 'auto', marginTop: 12 }}>
                {t('创建公开活动')}
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
                    {ev.title} {heatBadge(ev.status, ev.participantCount)}
                    {tab === 'archived' && <Badge tone="warning">{t('已归档')}</Badge>}
                  </div>
                  <div className="event-card-meta">
                    {ev.note && <span className="event-card-note">{ev.note}</span>}
                    <span>{formatMoney(ev.budget)}</span>
                    <span>
                      {ev.maxParticipants
                        ? t('{count}/{max} 人', { count: ev.participantCount, max: ev.maxParticipants })
                        : t('{count} 人参与', { count: ev.participantCount })}
                    </span>
                    {ev.drawDate && <span>{t('报名 {deadline}', { deadline: formatDeadline(ev.drawDate) })}</span>}
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
                  {restoring[ev.code] ? t('恢复中…') : t('恢复')}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {joinOpen && (
        <Modal title={t('用邀请码加入')} onClose={() => setJoinOpen(false)}>
          <p style={{ marginTop: 8, color: 'var(--gift-text-secondary)' }}>
            {t('输入朋友分享的 6 位邀请码，即可进入活动')}
          </p>
          <form onSubmit={(e) => { e.preventDefault(); onJoinByCode() }}>
            <label className="sr-only" htmlFor="join-code-input">{t('邀请码')}</label>
            <input
              id="join-code-input"
              className="form-input"
              style={{ marginTop: 12 }}
              placeholder={t('例如：ABC123')}
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value)}
              maxLength={40}
              autoFocus
            />
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button type="button" className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setJoinOpen(false)}>
                {t('取消')}
              </button>
              <button type="submit" className="btn btn-primary" style={{ flex: 1 }}>
                {t('加入')}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
