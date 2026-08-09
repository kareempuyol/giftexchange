import { useCallback, useEffect, useState } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { api, ApiError, GiftWall, GiftWallItem, Participant } from '../api/client'
import { useToast } from '../components/Toast'
import PosterModal, { PosterData } from '../components/PosterModal'
import Modal from '../components/Modal'

export default function GiftWallPage() {
  const { code = '' } = useParams()
  const { toast } = useToast()

  const [wall, setWall] = useState<GiftWall | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [poster, setPoster] = useState<PosterData | null>(null)
  const navigate = useNavigate()
  // 揭晓状态：同一次访问内记住已揭晓的卡片（matchId -> true）
  const [revealed, setRevealed] = useState<Record<number, boolean>>({})
  // 模糊照片：点击查看原图（matchId -> true = 已查看）
  const [viewPhoto, setViewPhoto] = useState<Record<number, boolean>>({})
  // 点赞请求在途的卡片（matchId 集合）：防连点
  const [likingIds, setLikingIds] = useState<Set<number>>(() => new Set())
  // 「再开一局」弹窗：勾选复制成员名单（默认开）
  const [replayOpen, setReplayOpen] = useState(false)
  const [copyMembers, setCopyMembers] = useState(true)
  const [replayBusy, setReplayBusy] = useState(false)

  // 再开一局：复制 title/budget/note（互避规则暂不复制，未来可做）到草稿，
  // 勾选时把当前活动成员用户名（含 userId，供创建页互避规则解析）一并带入
  const startReplay = async () => {
    setReplayBusy(true)
    const base = { title: wall.title, note: wall.note, budget: wall.budget }
    try {
      if (copyMembers) {
        try {
          const data = await api.get<{ participants: Participant[] }>(`/events/${code}/participants`)
          const members = data.participants.map((p) => ({
            username: p.username,
            userId: p.userId,
            displayName: p.displayName,
          }))
          localStorage.setItem('gift_draft', JSON.stringify({ ...base, members }))
          toast(`已复制 ${members.length} 位成员名单`)
        } catch {
          // 未登录/接口失败：降级为仅复制活动配置
          localStorage.setItem('gift_draft', JSON.stringify(base))
          toast('成员名单获取失败，已仅复制活动配置', 'error')
        }
      } else {
        localStorage.setItem('gift_draft', JSON.stringify(base))
      }
      setReplayOpen(false)
      navigate('/events/new')
    } finally {
      setReplayBusy(false)
    }
  }

  const reveal = (matchId: number) => {
    setRevealed((prev) => (prev[matchId] ? prev : { ...prev, [matchId]: true }))
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.get<GiftWall>(`/events/${code}/gift-wall`)
      setWall(data)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '加载礼物墙失败')
    } finally {
      setLoading(false)
    }
  }, [code])

  useEffect(() => {
    load()
  }, [load])

  // 点赞/取消点赞：前端乐观更新，再按服务端返回校正
  const toggleLike = async (item: GiftWallItem) => {
    // 防连点：同一卡片请求在途时忽略后续点击
    if (likingIds.has(item.matchId)) return
    setLikingIds((prev) => new Set(prev).add(item.matchId))
    const wasLiked = item.likedByMe
    const prev = wall
    setWall(
      prev
        ? {
            ...prev,
            items: prev.items.map((i) =>
              i.matchId === item.matchId
                ? { ...i, likedByMe: !wasLiked, likeCount: Math.max(0, i.likeCount + (wasLiked ? -1 : 1)) }
                : i
            ),
          }
        : prev
    )
    try {
      const resp = wasLiked
        ? await api.delete<{ likeCount: number }>(`/events/${code}/gift-wall/like?matchId=${item.matchId}`)
        : await api.post<{ likeCount: number }>(`/events/${code}/gift-wall/like`, { matchId: item.matchId })
      setWall(
        prev
          ? {
              ...prev,
              items: prev.items.map((i) =>
                i.matchId === item.matchId ? { ...i, likedByMe: !wasLiked, likeCount: resp.likeCount } : i
              ),
            }
          : prev
      )
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '操作失败', 'error')
      load()
    } finally {
      setLikingIds((prev) => {
        const next = new Set(prev)
        next.delete(item.matchId)
        return next
      })
    }
  }

  if (loading) return <div className="page-loading">加载中…</div>
  if (error)
    return (
      <div className="page-container" style={{ maxWidth: 760 }}>
        <div className="page-header">
          <h1 className="page-title">礼物墙</h1>
          <Link to={`/events/${code}`} className="btn btn-ghost btn-sm">返回</Link>
        </div>
        <div className="gw-empty">{error}</div>
      </div>
    )
  if (!wall) return <div className="page-container">暂无数据</div>

  const { unlocked, posted, total, items } = wall
  const { remaining } = wall.progress
  const pct = total > 0 ? Math.round((posted / total) * 100) : 0

  return (
    <div className="page-container page-container--wide">
      <div className="page-header">
        <h1 className="page-title">🎁 礼物墙</h1>
        <Link to={`/events/${code}`} className="btn btn-ghost btn-sm">返回</Link>
      </div>

      {!unlocked ? (
        <div className="gw-progress-card">
          <div className="gw-progress-text">
            {total === 0
              ? '还没有人加入活动，礼物墙稍后揭晓 🎁'
              : `${posted}/${total} 已送出并晒图，还差 ${remaining} 人解锁 🔒`}
          </div>
          <div className="gw-progress-bar">
            <div className="gw-progress-fill" style={{ width: `${pct}%` }} />
          </div>
          {posted === 0 ? (
            <p className="gw-lock-note">还没有人晒出礼物，收到礼物并晒图后，礼物墙就会揭晓 🎀</p>
          ) : (
            <p className="gw-lock-note">所有参与者送出礼物并晒图后，礼物墙自动解锁，敬请期待 ✨</p>
          )}
          <Link to={`/events/${code}`} className="btn btn-primary" style={{ width: 'auto', marginTop: 16, padding: '0 28px' }}>
            去晒出你的礼物
          </Link>
        </div>
      ) : items.length === 0 ? (
        <div className="gw-empty">
          <p>礼物墙已解锁，但还没有晒出的礼物 🎁</p>
          <Link to={`/events/${code}`} className="btn btn-primary" style={{ width: 'auto', marginTop: 16, padding: '0 28px' }}>
            返回活动晒出第一份礼物
          </Link>
        </div>
      ) : (
        <>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginBottom: 20 }}>
          <button
            className="btn btn-primary"
            style={{ width: 'auto', padding: '0 28px' }}
            onClick={() => {
              const totalStars = items.reduce((sum, it) => sum + (it.giftPost.rating || 0), 0)
              setPoster({
                kind: 'highlight',
                title: wall.title,
                participantCount: total,
                totalPosted: posted,
                totalStars,
              })
            }}
          >
            🏆 生成高光海报
          </button>
          <button
            className="btn btn-secondary"
            style={{ width: 'auto', padding: '0 28px' }}
            onClick={() => setReplayOpen(true)}
          >
            🔁 再开一局
          </button>
        </div>
        <div className="gw-grid">
          {items.map((item) => {
            const isRevealed = !!revealed[item.matchId]
            // 晒图隐私：后端返回 item.privacy 与 giftPost.privacy（旧数据缺省视为 photo）
            const privacy = item.giftPost.privacy || item.privacy || 'photo'
            const isBlur = privacy === 'blur'
            const isTextView = privacy === 'text' && !item.giftPost.photoUrl
            return (
              <div key={item.matchId} className={`gw-item-card${isRevealed ? ' revealed' : ''}`}>
                {/* 揭晓星星散落装饰（纯 CSS 动画，无库） */}
                <div className="gw-reveal-stars" aria-hidden="true">
                  <span>✨</span>
                  <span>⭐</span>
                  <span>✨</span>
                  <span>🌟</span>
                  <span>⭐</span>
                </div>

                {/* 礼物内容 */}
                <div className="gw-item-body" aria-hidden={!isRevealed}>
                  <div className="gw-item-header">
                    <div className="gw-people">
                      {item.giverName}
                      <span className="gw-arrow">→</span>
                      {item.receiverName}
                    </div>
                    <Stars rating={item.giftPost.rating} />
                  </div>

                  {item.giftPost.review && <p className="gw-review">“{item.giftPost.review}”</p>}

                  {isTextView ? (
                    <div className="gw-text-badge" role="img" aria-label="仅文字晒图">
                      📝 文字心意
                    </div>
                  ) : item.giftPost.photoUrl ? (
                    <div className="gw-photo-wrap">
                      <img
                        className={`gw-photo${isBlur ? ' gw-photo-blur' : ''}${isBlur && viewPhoto[item.matchId] ? ' viewing' : ''}`}
                        src={item.giftPost.photoUrl}
                        alt={isBlur ? '模糊照片，点击查看原图' : '礼物照片'}
                        loading="lazy"
                        onClick={isBlur ? () => setViewPhoto((prev) => ({ ...prev, [item.matchId]: !prev[item.matchId] })) : undefined}
                        onError={(e) => {
                          // 图片加载失败降级：显示占位（不再显示裂图）
                          const t = e.target as HTMLImageElement
                          t.style.display = 'none'
                          const wrap = t.parentElement
                          if (wrap) {
                            wrap.classList.add('gw-photo-fallback')
                            wrap.textContent = '🎁 礼物照片'
                          }
                        }}
                      />
                      {isBlur && (
                        <span className="gw-blur-hint">
                          {viewPhoto[item.matchId] ? '👁 点击隐藏原图' : '🌫️ 模糊照片 · 点击查看'}
                        </span>
                      )}
                    </div>
                  ) : null}

                  <div className="gw-item-footer">
                    <button
                      className={`gw-like-btn${item.likedByMe ? ' liked' : ''}`}
                      onClick={() => toggleLike(item)}
                      disabled={likingIds.has(item.matchId)}
                      aria-pressed={item.likedByMe}
                    >
                      <span className="gw-heart">{item.likedByMe ? '❤️' : '🤍'}</span>
                      <span>{item.likeCount}</span>
                    </button>
                  </div>
                </div>

                {/* 遮罩态：礼盒 + 点击揭晓（揭晓后翻走隐藏，保留动画出口） */}
                <button
                  type="button"
                  className={`gw-mask${isRevealed ? ' gw-mask-hidden' : ''}`}
                  onClick={() => reveal(item.matchId)}
                  aria-label="点击揭晓这份礼物"
                  aria-hidden={isRevealed}
                  tabIndex={isRevealed ? -1 : 0}
                >
                  <span className="gw-mask-gift">🎁</span>
                  <span className="gw-mask-hint">点击揭晓</span>
                </button>
              </div>
            )
          })}
        </div>
        </>
      )}

      <PosterModal data={poster} onClose={() => setPoster(null)} />

      {replayOpen && (
        <Modal title="🔁 再开一局" onClose={() => !replayBusy && setReplayOpen(false)}>
          <p style={{ marginTop: 8, color: 'var(--gift-text-secondary)' }}>
            用当前活动的标题、预算和说明创建新活动
          </p>
          <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginTop: 16, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={copyMembers}
              onChange={(e) => setCopyMembers(e.target.checked)}
              style={{ marginTop: 4, flexShrink: 0 }}
            />
            <span>
              复制成员名单
              <span className="form-hint" style={{ display: 'block' }}>
                带入上期成员用户名，方便复制邀请（不会自动加入）
              </span>
            </span>
          </label>
          <p className="form-hint" style={{ marginTop: 10 }}>
            互避规则暂不复制，新活动需重新配置
          </p>
          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <button
              className="btn btn-secondary"
              style={{ flex: 1 }}
              onClick={() => setReplayOpen(false)}
              disabled={replayBusy}
            >
              取消
            </button>
            <button className="btn btn-primary" style={{ flex: 1 }} onClick={startReplay} disabled={replayBusy}>
              {replayBusy ? '准备中…' : '确认再开一局'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function Stars({ rating }: { rating: number | null }) {
  if (!rating) return null
  return (
    <span className="gw-stars" aria-label={`评分 ${rating}/5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <span key={n} className={n <= rating ? 'gw-star on' : 'gw-star'}>★</span>
      ))}
    </span>
  )
}
