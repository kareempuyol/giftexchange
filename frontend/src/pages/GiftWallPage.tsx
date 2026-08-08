import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, GiftWall, GiftWallItem } from '../api/client'
import { useToast } from '../components/Toast'

export default function GiftWallPage() {
  const { code = '' } = useParams()
  const { toast } = useToast()

  const [wall, setWall] = useState<GiftWall | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

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
    <div className="page-container" style={{ maxWidth: 860 }}>
      <div className="page-header">
        <h1 className="page-title">🎁 礼物墙</h1>
        <Link to={`/events/${code}`} className="btn btn-ghost btn-sm">返回</Link>
      </div>

      {!unlocked ? (
        <div className="gw-progress-card">
          <div className="gw-progress-text">
            {posted}/{total} 已晒，还差 {remaining} 人解锁 🔒
          </div>
          <div className="gw-progress-bar">
            <div className="gw-progress-fill" style={{ width: `${pct}%` }} />
          </div>
          {posted === 0 ? (
            <p className="gw-lock-note">还没有人晒出礼物，收到礼物并晒图后，礼物墙就会揭晓 🎀</p>
          ) : (
            <p className="gw-lock-note">所有人晒出礼物后，礼物墙自动解锁，敬请期待 ✨</p>
          )}
        </div>
      ) : items.length === 0 ? (
        <div className="gw-empty">礼物墙已解锁，但还没有晒出的礼物 🎁</div>
      ) : (
        <div className="gw-grid">
          {items.map((item) => (
            <div key={item.matchId} className="gw-item-card">
              <div className="gw-item-header">
                <div className="gw-people">
                  {item.giverName}
                  <span className="gw-arrow">→</span>
                  {item.receiverName}
                </div>
                <Stars rating={item.giftPost.rating} />
              </div>

              {item.giftPost.review && <p className="gw-review">“{item.giftPost.review}”</p>}

              {item.giftPost.photoUrl && (
                <div className="gw-photo-wrap">
                  <img className="gw-photo" src={item.giftPost.photoUrl} alt="礼物照片" loading="lazy" />
                </div>
              )}

              <div className="gw-item-footer">
                <button
                  className={`gw-like-btn${item.likedByMe ? ' liked' : ''}`}
                  onClick={() => toggleLike(item)}
                  aria-pressed={item.likedByMe}
                >
                  <span className="gw-heart">{item.likedByMe ? '❤️' : '🤍'}</span>
                  <span>{item.likeCount}</span>
                </button>
              </div>
            </div>
          ))}
        </div>
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
