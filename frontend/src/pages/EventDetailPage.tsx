import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, EventInfo, Participant, MyMatch } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Badge from '../components/Badge'
import { useToast } from '../components/Toast'

export default function EventDetailPage() {
  const { code = '' } = useParams()
  const { user } = useAuth()
  const { toast } = useToast()

  const [event, setEvent] = useState<EventInfo | null>(null)
  const [participants, setParticipants] = useState<Participant[]>([])
  const [myMatch, setMyMatch] = useState<MyMatch | null>(null)
  const [joined, setJoined] = useState(false)
  const [loading, setLoading] = useState(true)
  const [showJoinForm, setShowJoinForm] = useState(false)
  const [confirmDraw, setConfirmDraw] = useState(false)
  const [drawing, setDrawing] = useState(false)

  const isOwner = user?.id === event?.ownerId

  const load = async () => {
    setLoading(true)
    try {
      const ev = await api.get<EventInfo>(`/events/${code}`)
      setEvent(ev)
      const [parts, match] = await Promise.all([
        api.get<{ participants: Participant[] }>(`/events/${code}/participants`).catch(() => null),
        api.get<MyMatch>(`/events/${code}/my-match`).catch(() => null),
      ])
      if (parts) setParticipants(parts.participants)
      setMyMatch(match)
      setJoined(!!match || parts?.participants.some((p) => p.userId === user?.id))
    } catch {
      toast('加载活动失败', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code])

  const onDraw = async () => {
    setDrawing(true)
    try {
      await api.post(`/events/${code}/draw`)
      toast('抽签完成！')
      setConfirmDraw(false)
      load()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '抽签失败', 'error')
    } finally {
      setDrawing(false)
    }
  }

  // 复制邀请链接：用短码生成分享 URL，未登录用户点开会先看到登录页
  const copyInviteLink = async () => {
    const shareCode = event?.shortCode || code
    const inviteUrl = `${window.location.origin}/events/${shareCode}`
    try {
      await navigator.clipboard.writeText(inviteUrl)
      toast('邀请链接已复制！')
    } catch {
      // 剪贴板不可用（如非 HTTPS）时退化为选中提示
      toast(`邀请链接：${inviteUrl}`, 'info')
    }
  }

  if (loading) return <div className="page-loading">加载中…</div>
  if (!event) return <div className="page-container">活动不存在</div>

  return (
    <div className="page-container" style={{ maxWidth: 760 }}>
      <div className="page-header">
        <h1 className="page-title">{event.title}</h1>
        <Link to="/events" className="btn btn-ghost btn-sm">返回</Link>
      </div>

      <div className="gift-card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Badge tone={event.status === 'open' ? 'success' : 'gold'}>
            {event.status === 'open' ? '报名中' : '已抽签'}
          </Badge>
          {event.isPublic ? <Badge tone="info">公开活动</Badge> : <Badge tone="warning">私密活动</Badge>}
          {isOwner && <Badge tone="gold">我是组织者</Badge>}
        </div>

        {/* 邀请区：短码 + 复制链接 */}
        {event.shortCode && (
          <div className="invite-box">
            <div className="invite-info">
              <span className="invite-label">邀请码</span>
              <span className="invite-code">{event.shortCode}</span>
            </div>
            <button
              className="btn btn-primary btn-sm"
              style={{ width: 'auto', flexShrink: 0 }}
              onClick={copyInviteLink}
            >
              📋 复制邀请链接
            </button>
          </div>
        )}

        {event.note && <p style={{ color: 'var(--gift-text-secondary)', marginBottom: 12 }}>{event.note}</p>}

        <div className="event-meta-grid">
          <div><span className="meta-label">预算</span><span className="meta-value">¥{event.budget}</span></div>
          <div><span className="meta-label">参与人数</span><span className="meta-value">{event.participantCount}</span></div>
          {event.drawDate && (
            <div><span className="meta-label">报名截止</span><span className="meta-value">{new Date(event.drawDate).toLocaleDateString('zh-CN')}</span></div>
          )}
          {event.maxParticipants && (
            <div><span className="meta-label">人数上限</span><span className="meta-value">{event.maxParticipants}</span></div>
          )}
        </div>

        {!joined && event.status === 'open' && (
          <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={() => setShowJoinForm(true)}>
            加入这个活动
          </button>
        )}

        {joined && event.status === 'open' && !isOwner && (
          <p style={{ marginTop: 12, color: 'var(--gift-success)' }}>✅ 你已加入，等待组织者抽签</p>
        )}

        {isOwner && event.status === 'open' && (
          <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
            <Link to={`/events/${code}/dashboard`} className="btn btn-secondary" style={{ flex: 1 }}>活动管理台</Link>
            <button
              className="btn btn-primary"
              style={{ flex: 1 }}
              onClick={() => setConfirmDraw(true)}
              disabled={event.participantCount < 2}
            >
              {event.participantCount < 2 ? '至少 2 人才能抽签' : '开始抽签'}
            </button>
          </div>
        )}
      </div>

      {confirmDraw && (
        <div className="modal-overlay" onClick={() => setConfirmDraw(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>确认抽签？</h3>
            <p style={{ marginTop: 8 }}>
              当前 <b>{event.participantCount}</b> 人参与。抽签后不可撤销，每个人将获得一个送礼对象。
            </p>
            <p style={{ marginTop: 8, fontSize: 14, color: 'var(--gift-text-secondary)' }}>
              {participants.filter((p) => !p.contactComplete).length > 0 &&
                `提示：${participants.filter((p) => !p.contactComplete).length} 人未填完整收件信息，抽签后对方可能收不到礼物。`}
            </p>
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button className="btn btn-secondary" onClick={() => setConfirmDraw(false)}>取消</button>
              <button className="btn btn-primary" onClick={onDraw} disabled={drawing}>
                {drawing ? '抽签中…' : '确认抽签'}
              </button>
            </div>
          </div>
        </div>
      )}

      {joined && myMatch && event.status === 'drawn' && (
        <div className="gift-card" style={{ marginBottom: 16 }}>
          <h2 className="section-title">🎯 我的送礼任务</h2>
          <p style={{ marginTop: 8, fontSize: 18 }}>
            我要送给 <b style={{ color: 'var(--gift-brand)' }}>{myMatch.receiverDisplayName}</b>
          </p>
          <div style={{ marginTop: 12, fontSize: 14, color: 'var(--gift-text-secondary)' }}>
            <p>💰 预算参考：¥{event.budget}</p>
            {myMatch.preference.likes && <p>❤️ 喜欢：{myMatch.preference.likes}</p>}
            {myMatch.preference.dislikes && <p>🚫 不喜欢：{myMatch.preference.dislikes}</p>}
            {myMatch.preference.notes && <p>📝 备注：{myMatch.preference.notes}</p>}
            {myMatch.note && <p>💬 悄悄话：{myMatch.note}</p>}
          </div>
          <div style={{ marginTop: 12, padding: 12, background: 'var(--gift-bg-muted)', borderRadius: 12 }}>
            <p><b>收件人：</b>{myMatch.contact.receiverName}</p>
            <p><b>电话：</b>{myMatch.contact.phone}</p>
            <p><b>地址：</b>{myMatch.contact.address}</p>
          </div>
        </div>
      )}

      <div className="gift-card">
        <h2 className="section-title">参与者（{participants.length}）</h2>
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {participants.map((p) => (
            <div key={p.id} className="participant-row">
              <span style={{ fontWeight: 500 }}>{p.displayName || p.username}</span>
              <span style={{ display: 'flex', gap: 6 }}>
                {p.contactComplete ? <Badge tone="success">信息完整</Badge> : <Badge tone="warning">缺信息</Badge>}
              </span>
            </div>
          ))}
        </div>
      </div>

      {showJoinForm && (
        <JoinForm
          code={code}
          onClose={() => setShowJoinForm(false)}
          onJoined={() => {
            setShowJoinForm(false)
            load()
            toast('加入成功！')
          }}
        />
      )}
    </div>
  )
}

function JoinForm({ code, onClose, onJoined }: { code: string; onClose: () => void; onJoined: () => void }) {
  const { toast } = useToast()
  const [receiverName, setReceiverName] = useState('')
  const [phone, setPhone] = useState('')
  const [address, setAddress] = useState('')
  const [likes, setLikes] = useState('')
  const [dislikes, setDislikes] = useState('')
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!receiverName || !phone || !address) {
      setError('请填写收件人、电话和地址')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      await api.post(`/events/${code}/join`, {
        receiverName,
        phone,
        address,
        preferenceLikes: likes,
        preferenceDislikes: dislikes,
        preferenceNotes: notes,
      })
      onJoined()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '加入失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <h3>加入活动</h3>
        <p className="form-hint" style={{ marginBottom: 16 }}>填写收件信息，抽签后送礼的人会看到这些</p>
        <form onSubmit={onSubmit}>
          <div className="form-group">
            <label className="form-label">收件人姓名 *</label>
            <input className="form-input" value={receiverName} onChange={(e) => setReceiverName(e.target.value)} maxLength={120} />
          </div>
          <div className="form-group">
            <label className="form-label">联系电话 *</label>
            <input className="form-input" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={50} />
          </div>
          <div className="form-group">
            <label className="form-label">收件地址 *</label>
            <textarea className="form-textarea" value={address} onChange={(e) => setAddress(e.target.value)} maxLength={500} />
          </div>
          <div className="form-group">
            <label className="form-label">我喜欢的礼物（选填）</label>
            <input className="form-input" placeholder="例如：咖啡、书、手作" value={likes} onChange={(e) => setLikes(e.target.value)} maxLength={500} />
          </div>
          <div className="form-group">
            <label className="form-label">我不想要的（选填）</label>
            <input className="form-input" placeholder="例如：香水、毛绒玩具" value={dislikes} onChange={(e) => setDislikes(e.target.value)} maxLength={500} />
          </div>
          <div className="form-group">
            <label className="form-label">备注（选填）</label>
            <textarea className="form-textarea" placeholder="尺码、颜色偏好等" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} />
          </div>
          {error && <div className="form-error" style={{ marginBottom: 12 }}>{error}</div>}
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="btn btn-secondary" onClick={onClose} style={{ flex: 1 }}>取消</button>
            <button type="submit" className="btn btn-primary" disabled={submitting} style={{ flex: 1 }}>
              {submitting ? '提交中…' : '确认加入'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
