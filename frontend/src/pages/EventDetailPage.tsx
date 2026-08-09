import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError, EventInfo, EventPreview, GiftPrivacy, MemberStatus, Participant, MyMatch, ReceivedGift } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Badge from '../components/Badge'
import ImageUpload from '../components/ImageUpload'
import { useToast } from '../components/Toast'
import PosterModal, { PosterData } from '../components/PosterModal'

// 成员完成度状态徽标（joined < ready < shipped < posted）
const MEMBER_STATUS_META: Record<MemberStatus, { label: string; tone: 'success' | 'warning' | 'error' | 'info' | 'gold' }> = {
  joined: { label: '📝待填信息', tone: 'warning' },
  ready: { label: '✅已就绪', tone: 'info' },
  shipped: { label: '📦已发货', tone: 'gold' },
  posted: { label: '✨已晒图', tone: 'success' },
}

export default function EventDetailPage() {
  const { code = '' } = useParams()
  const { user } = useAuth()
  const { toast } = useToast()
  const navigate = useNavigate()

  const [event, setEvent] = useState<EventInfo | null>(null)
  const [preview, setPreview] = useState<EventPreview | null>(null)
  const [participants, setParticipants] = useState<Participant[]>([])
  const [myMatch, setMyMatch] = useState<MyMatch | null>(null)
  const [joined, setJoined] = useState(false)
  const [loading, setLoading] = useState(true)
  const [showJoinForm, setShowJoinForm] = useState(false)
  const [confirmDraw, setConfirmDraw] = useState(false)
  const [drawing, setDrawing] = useState(false)
  const [confirmRedraw, setConfirmRedraw] = useState(false)
  const [redrawing, setRedrawing] = useState(false)
  const [reminding, setReminding] = useState(false)
  const [poster, setPoster] = useState<PosterData | null>(null)
  const [confirmArchive, setConfirmArchive] = useState(false)
  const [archiving, setArchiving] = useState(false)
  const [confirmResetCode, setConfirmResetCode] = useState(false)
  const [resetting, setResetting] = useState(false)

  const isOwner = user?.id === event?.ownerId

  const load = async () => {
    setLoading(true)
    try {
      if (!user) {
        // 游客模式：只读预览（邀请落地页）
        const pv = await api.get<EventPreview>(`/events/${code}/preview`)
        setPreview(pv)
        setLoading(false)
        return
      }
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
  }, [code, user])

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

  const onRedraw = async () => {
    setRedrawing(true)
    try {
      await api.post(`/events/${code}/redraw`)
      toast('已重新抽签！请查看新的任务')
      setConfirmRedraw(false)
      load()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '重新抽签失败', 'error')
    } finally {
      setRedrawing(false)
    }
  }

  // 催办未完成成员：仅组织者视角，给未完成者（未填信息/未发货/未晒图）发站内提醒
  const onRemind = async () => {
    setReminding(true)
    try {
      const res = await api.post<{ reminded: number }>(`/events/${code}/remind`)
      toast(`已提醒 ${res.reminded} 人`)
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '催办失败', 'error')
    } finally {
      setReminding(false)
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

  // 复制短码本身
  const copyShortCode = async () => {
    const sc = event?.shortCode || ''
    try {
      await navigator.clipboard.writeText(sc)
      toast(`邀请码 ${sc} 已复制！`)
    } catch {
      toast(`邀请码：${sc}`, 'info')
    }
  }

  // 归档活动：仅组织者、drawn 态；归档后从「我创建的」列表隐藏，进「已归档」（可恢复）
  const onArchive = async () => {
    setArchiving(true)
    try {
      await api.post(`/events/${code}/archive`)
      toast('活动已归档')
      setConfirmArchive(false)
      navigate('/events')
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '归档失败', 'error')
    } finally {
      setArchiving(false)
    }
  }

  // 重置邀请短码：旧码立即失效，刷新后显示新码
  const onResetShortCode = async () => {
    setResetting(true)
    try {
      await api.post(`/events/${code}/reset-short-code`)
      toast('邀请码已重置，旧邀请码已失效')
      setConfirmResetCode(false)
      load()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '重置失败', 'error')
    } finally {
      setResetting(false)
    }
  }

  if (loading) return <div className="page-loading">加载中…</div>

  // 游客模式：邀请落地预览（不泄露收件人/发货等敏感信息）
  if (!user) {
    if (!preview) return <div className="page-loading">加载中…</div>
    return (
      <div className="page-container" style={{ maxWidth: 760 }}>
        <div className="page-header">
          <h1 className="page-title">{preview.title}</h1>
          <Link to="/events" className="btn btn-ghost btn-sm">返回</Link>
        </div>

        <div className="gift-card" style={{ marginBottom: 16 }}>
          {preview.coverImage && (
            <img
              src={preview.coverImage}
              alt="活动封面"
              style={{ width: '100%', maxHeight: 240, objectFit: 'cover', borderRadius: 'var(--gift-radius-md)', marginBottom: 12 }}
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          )}
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <Badge tone={preview.status === 'open' ? 'success' : 'gold'}>
              {preview.status === 'open' ? '报名中' : '已抽签'}
            </Badge>
            {preview.isPublic ? <Badge tone="info">公开活动</Badge> : <Badge tone="warning">私密活动</Badge>}
          </div>

          {preview.note && <p style={{ color: 'var(--gift-text-secondary)', marginBottom: 12 }}>{preview.note}</p>}

          <div className="event-meta-grid">
            {preview.budget ? <div><span className="meta-label">预算</span><span className="meta-value">¥{preview.budget}</span></div> : null}
            <div><span className="meta-label">参与人数</span><span className="meta-value">{preview.participantCount} 人</span></div>
            {preview.signUpDeadline ? (
              <div><span className="meta-label">报名截止</span><span className="meta-value">{new Date(preview.signUpDeadline).toLocaleDateString('zh-CN')}</span></div>
            ) : null}
          </div>

          <p style={{ color: 'var(--gift-text-secondary)', margin: '16px 0' }}>
            {preview.status === 'open'
              ? `朋友邀请你参加「${preview.title}」🎁 登录后即可查看详情并加入`
              : '这个活动已经开始啦，登录后看看大家交换了什么礼物吧'}
          </p>

          <Link to={`/login?from=${encodeURIComponent(`events/${code}`)}`} className="btn btn-primary">
            登录后加入
          </Link>
          <div style={{ textAlign: 'center', marginTop: 12, fontSize: 'var(--gift-font-sm)' }}>
            <Link to={`/register?from=${encodeURIComponent(`events/${code}`)}`} style={{ color: 'var(--gift-brand)' }}>
              没有账号？立即注册
            </Link>
          </div>
        </div>
      </div>
    )
  }

  if (!event) return <div className="page-container">活动不存在</div>

  // 活动级流程状态（Task A）：由后端 detail 接口推导；旧后端缺失时按 status 兜底
  const flowState =
    (event as EventInfo & { flowState?: string }).flowState ||
    (event.status === 'open' ? 'recruiting' : 'active')

  return (
    <div className="page-container" style={{ maxWidth: 760 }}>
      <div className="page-header">
        <h1 className="page-title">{event.title}</h1>
        <Link to="/events" className="btn btn-ghost btn-sm">返回</Link>
      </div>

      <div className="gift-card" style={{ marginBottom: 16, overflow: 'hidden' }}>
        {/* 活动封面（登录态也展示） */}
        {event.coverImage && (
          <div style={{ margin: '-16px -16px 12px' }}>
            <img
              src={event.coverImage}
              alt="活动封面"
              style={{ width: '100%', height: 180, objectFit: 'cover', display: 'block' }}
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Badge tone={event.status === 'open' ? 'success' : 'gold'}>
            {event.status === 'open' ? '报名中' : '已抽签'}
          </Badge>
          {event.isPublic ? <Badge tone="info">公开活动</Badge> : <Badge tone="warning">私密活动</Badge>}
          {isOwner && <Badge tone="gold">我是组织者</Badge>}
        </div>

        {/* 活动级流程步骤条（区别于下方"我的送礼任务"状态机） */}
        <FlowSteps
          state={flowState}
          isOwner={isOwner}
          joined={joined}
          participantCount={event.participantCount}
        />

        {/* 邀请区：短码 + 复制链接 + 复制短码 */}
        {event.shortCode && (
          <div className="invite-box" style={{ flexWrap: 'wrap' }}>
            <div className="invite-info">
              <span className="invite-label">邀请码</span>
              <button className="invite-code-btn" onClick={copyShortCode} title="点击复制邀请码">
                {event.shortCode} 📋
              </button>
            </div>
            <button
              className="btn btn-primary btn-sm"
              style={{ width: 'auto', flexShrink: 0 }}
              onClick={copyInviteLink}
            >
              📋 复制邀请链接
            </button>
            <button
              className="btn btn-secondary btn-sm"
              style={{ width: 'auto', flexShrink: 0 }}
              onClick={() =>
                setPoster({
                  kind: 'invite',
                  title: event.title,
                  note: event.note,
                  budget: event.budget,
                  participantCount: participants.length,
                  shortCode: event.shortCode,
                  coverImage: event.coverImage,
                })
              }
            >
              🖼️ 邀请海报
            </button>
            {isOwner && (
              <button
                className="btn btn-ghost btn-sm"
                style={{ width: 'auto', flexShrink: 0 }}
                onClick={() => setConfirmResetCode(true)}
              >
                🔄 重置邀请码
              </button>
            )}
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

        {isOwner && event.status === 'drawn' && (
          <div style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <Link to={`/events/${code}/dashboard`} className="btn btn-secondary" style={{ flex: 1 }}>活动管理台</Link>
              <button
                className="btn btn-secondary"
                style={{ flex: 1, color: 'var(--gift-warning)', borderColor: 'var(--gift-warning)' }}
                onClick={() => setConfirmRedraw(true)}
              >
                重新抽签
              </button>
            </div>
            <button
              className="btn btn-secondary"
              style={{ marginTop: 8, width: '100%', color: 'var(--gift-error)', borderColor: 'var(--gift-error)' }}
              onClick={() => setConfirmArchive(true)}
            >
              归档活动
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
            {event.excludedPairs.length > 0 && (
              <p style={{ marginTop: 8, fontSize: 14, color: 'var(--gift-warning)' }}>
                ⚠️ 已配置 {event.excludedPairs.length} 组互避规则，抽签时会避开这些配对
              </p>
            )}
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

      {confirmRedraw && (
        <div className="modal-overlay" onClick={() => setConfirmRedraw(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>重新抽签？</h3>
            <p style={{ marginTop: 8 }}>
              所有成员的任务将重置，已发货/已晒图的数据会清空，此操作不可撤销。
            </p>
            {event.excludedPairs.length > 0 && (
              <p style={{ marginTop: 8, fontSize: 14, color: 'var(--gift-warning)' }}>
                ⚠️ 已配置 {event.excludedPairs.length} 组互避规则，重新抽签会继续避开这些配对
              </p>
            )}
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setConfirmRedraw(false)} disabled={redrawing}>
                取消
              </button>
              <button
                className="btn btn-primary"
                style={{ flex: 1, background: 'var(--gift-error)' }}
                onClick={onRedraw}
                disabled={redrawing}
              >
                {redrawing ? '重抽中…' : '确认重新抽签'}
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmArchive && (
        <div className="modal-overlay" onClick={() => setConfirmArchive(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>归档活动？</h3>
            <p style={{ marginTop: 8 }}>
              归档后活动将从「我创建的」列表隐藏，进入「已归档」。详情页、礼物墙、管理台数据不受影响，可随时恢复。
            </p>
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setConfirmArchive(false)} disabled={archiving}>
                取消
              </button>
              <button
                className="btn btn-primary"
                style={{ flex: 1, background: 'var(--gift-error)' }}
                onClick={onArchive}
                disabled={archiving}
              >
                {archiving ? '归档中…' : '确认归档'}
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmResetCode && (
        <div className="modal-overlay" onClick={() => setConfirmResetCode(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>重置邀请码？</h3>
            <p style={{ marginTop: 8 }}>
              旧邀请码将立即失效，已转发的旧邀请链接将无法再进入活动，此操作不可撤销。
            </p>
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setConfirmResetCode(false)} disabled={resetting}>
                取消
              </button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={onResetShortCode} disabled={resetting}>
                {resetting ? '重置中…' : '确认重置'}
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
            {myMatch.preference.size && <p>📏 尺码：{myMatch.preference.size}</p>}
            {myMatch.preference.color && <p>🎨 颜色：{myMatch.preference.color}</p>}
            {myMatch.preference.wishLinks.length > 0 && (
              <p>
                🎁 心愿链接：
                {myMatch.preference.wishLinks.map((link, i) => (
                  <a key={i} href={link} target="_blank" rel="noreferrer" style={{ marginLeft: 8 }}>
                    心愿{i + 1} ↗
                  </a>
                ))}
              </p>
            )}
            {myMatch.preference.notes && <p>📝 备注：{myMatch.preference.notes}</p>}
            {/* 悄悄话：仅当收礼人已晒图后才揭晓（纯前端门控，receivedAt 非空 = 收礼人已晒图） */}
            {myMatch.note &&
              (myMatch.giftPost.receivedAt ? (
                <p>💬 悄悄话：{myMatch.note}</p>
              ) : (
                <p className="note-pending">💬 悄悄话：收礼人晒图后揭晓 ✨</p>
              ))}
          </div>
          <div style={{ marginTop: 12, padding: 12, background: 'var(--gift-bg-muted)', borderRadius: 12 }}>
            <p><b>收件人：</b>{myMatch.contact.receiverName}</p>
            <p><b>电话：</b>{myMatch.contact.phone}</p>
            <p><b>地址：</b>{myMatch.contact.address}</p>
          </div>

          {/* 送礼状态机进度条：待购买 → 已发货 → 已签收 → 已晒图（未抽签/无 my-match 不显示） */}
          <ShipmentProgress state={myMatch.shipmentState || deriveShipmentState(myMatch)} />

          {/* 发货区：物流状态 + 填单号 + 悄悄话 */}
          <ShipmentSection
            code={code}
            matchId={myMatch.matchId}
            shipment={myMatch.shipment}
            note={myMatch.note}
            onUpdated={() => load()}
          />
        </div>
      )}

      {/* 我收到的礼物：晒图不阻塞（Luna 独到项）——可选 公开照片/仅文字/模糊照片 */}
      {joined && event.status === 'drawn' && <ReceivedGiftSection code={code} />}

      {/* 礼物墙入口：抽签后参与者/组织者可见 */}
      {event.status === 'drawn' && (isOwner || joined) && (
        <div className="gift-card" style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <div>
              <h2 className="section-title">🎁 礼物墙</h2>
              <p style={{ marginTop: 4, fontSize: 14, color: 'var(--gift-text-secondary)' }}>
                看看大家都收到了什么礼物，给喜欢的点赞！
              </p>
            </div>
            <Link to={`/events/${code}/gift-wall`} className="btn btn-primary" style={{ flexShrink: 0, width: 'auto' }}>
              去看看
            </Link>
          </div>
        </div>
      )}

      <div className="gift-card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <h2 className="section-title" style={{ margin: 0 }}>参与者（{participants.length}）</h2>
          {isOwner && (
            <button
              className="btn btn-primary btn-sm"
              style={{ width: 'auto', flexShrink: 0 }}
              onClick={onRemind}
              disabled={reminding}
            >
              {reminding ? '催办中…' : '催办未完成成员'}
            </button>
          )}
        </div>
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {participants.map((p) => {
            const status = p.status ?? (p.contactComplete ? 'ready' : 'joined')
            const meta = MEMBER_STATUS_META[status]
            return (
              <div key={p.id} className="participant-row">
                <span style={{ fontWeight: 500 }}>{p.displayName || p.username}</span>
                <span style={{ display: 'flex', gap: 6 }}>
                  <Badge tone={meta.tone}>{meta.label}</Badge>
                </span>
              </div>
            )
          })}
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

      <PosterModal data={poster} onClose={() => setPoster(null)} />
    </div>
  )
}

function JoinForm({ code, onClose, onJoined }: { code: string; onClose: () => void; onJoined: () => void }) {
  const { toast } = useToast()
  const [step, setStep] = useState<1 | 2>(1)
  // 第一步：收件信息
  const [receiverName, setReceiverName] = useState('')
  const [phone, setPhone] = useState('')
  const [address, setAddress] = useState('')
  // 第二步：心愿单（结构化）
  const [likes, setLikes] = useState('')
  const [dislikes, setDislikes] = useState('')
  const [size, setSize] = useState('')
  const [color, setColor] = useState('')
  const [wishLinks, setWishLinks] = useState('')
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  // 第一步校验通过才进第二步
  const goNext = () => {
    if (!receiverName || !phone || !address) {
      setError('请填写收件人姓名、电话和地址（必填）')
      return
    }
    setError('')
    setStep(2)
  }

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await api.post(`/events/${code}/join`, {
        receiverName,
        phone,
        address,
        preferenceLikes: likes,
        preferenceDislikes: dislikes,
        preferenceSize: size,
        preferenceColor: color,
        wishLinks: wishLinks.split(/[,，\n]/).map((s) => s.trim()).filter(Boolean).slice(0, 3),
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
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 520 }}>
        <h3>加入活动</h3>

        {/* 步骤指示器 */}
        <div className="step-indicator">
          <div className={`step-dot${step === 1 ? ' active' : ''}${step === 2 ? ' done' : ''}`}>
            <span>{step === 2 ? '✓' : '1'}</span>
          </div>
          <div className={`step-line${step === 2 ? ' done' : ''}`} />
          <div className={`step-dot${step === 2 ? ' active' : ''}`}><span>2</span></div>
          <div className="step-labels">
            <span className={step === 1 ? 'current' : ''}>收件信息</span>
            <span className={step === 2 ? 'current' : ''}>心愿单</span>
          </div>
        </div>

        <form onSubmit={onSubmit}>
          {step === 1 ? (
            <>
              <p className="form-hint" style={{ marginBottom: 16 }}>
                抽签后，送你礼物的人会看到这些信息来寄礼物
              </p>
              <div className="form-group">
                <label className="form-label">收件人姓名 *</label>
                <input className="form-input" placeholder="真实姓名" value={receiverName} onChange={(e) => setReceiverName(e.target.value)} maxLength={120} />
              </div>
              <div className="form-group">
                <label className="form-label">联系电话 *</label>
                <input className="form-input" type="tel" placeholder="手机号" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={50} />
              </div>
              <div className="form-group">
                <label className="form-label">收件地址 *</label>
                <textarea className="form-textarea" placeholder="省市区 + 详细地址" value={address} onChange={(e) => setAddress(e.target.value)} maxLength={500} />
              </div>
              {error && <div className="form-error" style={{ marginBottom: 12 }}>{error}</div>}
              <div style={{ display: 'flex', gap: 8 }}>
                <button type="button" className="btn btn-secondary" onClick={onClose} style={{ flex: 1 }}>取消</button>
                <button type="button" className="btn btn-primary" onClick={goNext} style={{ flex: 1 }}>下一步</button>
              </div>
            </>
          ) : (
            <>
              <p className="form-hint" style={{ marginBottom: 16 }}>
                让送礼的人更懂你（全部选填，但填得越多礼物越合心意 🎁）
              </p>
              <div className="form-group">
                <label className="form-label">我喜欢的礼物</label>
                <input className="form-input" placeholder="例如：咖啡、书、手作" value={likes} onChange={(e) => setLikes(e.target.value)} maxLength={500} />
              </div>
              <div className="form-group">
                <label className="form-label">我不想要的</label>
                <input className="form-input" placeholder="例如：香水、毛绒玩具" value={dislikes} onChange={(e) => setDislikes(e.target.value)} maxLength={500} />
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <div className="form-group" style={{ flex: 1 }}>
                  <label className="form-label">尺码（选填）</label>
                  <input className="form-input" placeholder="如 M / 42 码" value={size} onChange={(e) => setSize(e.target.value)} maxLength={50} />
                </div>
                <div className="form-group" style={{ flex: 1 }}>
                  <label className="form-label">喜欢的颜色（选填）</label>
                  <input className="form-input" placeholder="如 莫兰迪色系" value={color} onChange={(e) => setColor(e.target.value)} maxLength={80} />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">心愿链接（选填，最多 3 个）</label>
                <input className="form-input" placeholder="淘宝/京东等商品链接，逗号分隔" value={wishLinks} onChange={(e) => setWishLinks(e.target.value)} maxLength={500} />
              </div>
              <div className="form-group">
                <label className="form-label">备注（选填）</label>
                <textarea className="form-textarea" placeholder="其他想说的话" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} />
              </div>
              {error && <div className="form-error" style={{ marginBottom: 12 }}>{error}</div>}
              <div style={{ display: 'flex', gap: 8 }}>
                <button type="button" className="btn btn-secondary" onClick={() => { setStep(1); setError('') }} style={{ flex: 1 }}>上一步</button>
                <button type="submit" className="btn btn-primary" disabled={submitting} style={{ flex: 1 }}>
                  {submitting ? '提交中…' : '确认加入'}
                </button>
              </div>
            </>
          )}
        </form>
      </div>
    </div>
  )
}

// ===== 我收到的礼物：晒图（评分 + 评价 + 照片 + 隐私形式） =====
// 晒图不阻塞（Luna 独到项）：privacy='text' 时只写评价也能晒出，礼物墙照常解锁；
// 'blur' 前端传原图但标记模糊，礼物墙 CSS 模糊展示、点击查看原图（后端不做图像处理）。
const PRIVACY_OPTIONS: { value: GiftPrivacy; label: string; hint: string }[] = [
  { value: 'photo', label: '📷 公开照片', hint: '照片直接展示在礼物墙' },
  { value: 'text', label: '📝 仅文字', hint: '不传照片，只写评价也能晒出' },
  { value: 'blur', label: '🌫️ 模糊照片', hint: '照片模糊展示，点击可查看原图' },
]

const PRIVACY_LABEL: Record<GiftPrivacy, string> = {
  photo: '📷 公开照片',
  text: '📝 仅文字',
  blur: '🌫️ 模糊照片',
}

function ReceivedGiftSection({ code }: { code: string }) {
  const { toast } = useToast()
  const [received, setReceived] = useState<ReceivedGift | null>(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  // 表单状态
  const [rating, setRating] = useState(0)
  const [review, setReview] = useState('')
  const [photoUrl, setPhotoUrl] = useState('')
  const [privacy, setPrivacy] = useState<GiftPrivacy>('photo')
  const [saving, setSaving] = useState(false)
  // 删除晒图：二次确认弹窗
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  // 已晒出状态下：模糊照片点击查看原图
  const [blurView, setBlurView] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.get<ReceivedGift | null>(`/events/${code}/received-gift`)
      setReceived(data)
      if (data) {
        setRating(data.giftPost.rating || 0)
        setReview(data.giftPost.review || '')
        setPhotoUrl(data.giftPost.photoUrl || '')
        setPrivacy(data.giftPost.privacy || 'photo')
      }
    } catch {
      setReceived(null) // 非参与者/无匹配：隐藏该区块
    } finally {
      setLoading(false)
    }
  }, [code])

  useEffect(() => {
    load()
  }, [load])

  const startEdit = () => {
    if (!received) return
    setRating(received.giftPost.rating || 0)
    setReview(received.giftPost.review || '')
    setPhotoUrl(received.giftPost.photoUrl || '')
    setPrivacy(received.giftPost.privacy || 'photo')
    setBlurView(false)
    setEditing(true)
  }

  const onDelete = async () => {
    if (!received) return
    setDeleting(true)
    try {
      await api.delete(`/events/${code}/received-gift?matchId=${received.matchId}`)
      toast('晒图已删除')
      setConfirmDelete(false)
      setEditing(false)
      load()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '删除失败', 'error')
    } finally {
      setDeleting(false)
    }
  }

  const submit = async () => {
    if (!received) return
    if (rating < 1 || rating > 5) {
      toast('请先给礼物评分 ⭐', 'error')
      return
    }
    if (privacy !== 'text' && !photoUrl.trim()) {
      toast('请上传一张照片（或选择「仅文字」模式）', 'error')
      return
    }
    setSaving(true)
    try {
      await api.put(`/events/${code}/received-gift`, {
        matchId: received.matchId,
        rating,
        review: review.trim(),
        photoUrl: photoUrl.trim(),
        privacy,
      })
      toast('晒图成功 🎉')
      setEditing(false)
      load()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '保存失败', 'error')
    } finally {
      setSaving(false)
    }
  }

  if (loading || !received) return null
  const giverName = received.giverDisplayName || received.giverName
  const posted = !!received.giftPost.receivedAt
  const curPrivacy: GiftPrivacy = received.giftPost.privacy || 'photo'

  return (
    <div className="gift-card" style={{ marginBottom: 16 }}>
      <h2 className="section-title">🎁 我收到的礼物</h2>
      <p style={{ marginTop: 8, fontSize: 14, color: 'var(--gift-text-secondary)' }}>
        {posted
          ? `来自 ${giverName} 的礼物，你已晒出（${PRIVACY_LABEL[curPrivacy]}）`
          : `来自 ${giverName} 的礼物 —— 晒出后，礼物墙就离解锁更近一步 🎀`}
      </p>

      {posted && !editing ? (
        <div style={{ marginTop: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <span className="gw-stars" aria-label={`评分 ${rating}/5`}>
              {[1, 2, 3, 4, 5].map((n) => (
                <span key={n} className={n <= (received.giftPost.rating || 0) ? 'gw-star on' : 'gw-star'}>★</span>
              ))}
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" className="btn btn-ghost btn-sm" style={{ width: 'auto' }} onClick={startEdit}>
                修改晒图
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                style={{ width: 'auto', color: 'var(--gift-error)' }}
                onClick={() => setConfirmDelete(true)}
              >
                删除晒图
              </button>
            </div>
          </div>
          {received.giftPost.review && (
            <p className="gw-review" style={{ marginTop: 8 }}>“{received.giftPost.review}”</p>
          )}
          {received.giftPost.photoUrl && (
            <div className="gw-photo-wrap" style={{ marginTop: 8 }}>
              <img
                className={`gw-photo${curPrivacy === 'blur' ? ' gw-photo-blur' : ''}${curPrivacy === 'blur' && blurView ? ' viewing' : ''}`}
                src={received.giftPost.photoUrl}
                alt={curPrivacy === 'blur' ? '模糊照片，点击查看原图' : '礼物照片'}
                loading="lazy"
                onClick={curPrivacy === 'blur' ? () => setBlurView((v) => !v) : undefined}
              />
              {curPrivacy === 'blur' && (
                <span className="gw-blur-hint">{blurView ? '👁 点击隐藏原图' : '🌫️ 模糊照片 · 点击查看原图'}</span>
              )}
            </div>
          )}
        </div>
      ) : (
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* 评分 */}
          <div>
            <div className="form-label">评分 *</div>
            <div className="gw-stars" style={{ fontSize: 28, cursor: 'pointer' }}>
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  className={`gw-star${n <= rating ? ' on' : ''}`}
                  style={{ background: 'none', border: 'none', fontSize: 28, padding: '0 4px', cursor: 'pointer' }}
                  onClick={() => setRating(n)}
                  aria-label={`${n} 星`}
                >
                  ★
                </button>
              ))}
            </div>
          </div>

          {/* 评价 */}
          <div>
            <label className="form-label">评价（选填）</label>
            <textarea
              className="form-textarea"
              placeholder="收到礼物想说点什么？"
              value={review}
              onChange={(e) => setReview(e.target.value)}
              maxLength={500}
              rows={3}
            />
          </div>

          {/* 隐私形式 */}
          <div>
            <div className="form-label">晒图形式</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {PRIVACY_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`privacy-option${privacy === opt.value ? ' active' : ''}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '10px 12px',
                    border: `1px solid ${privacy === opt.value ? 'var(--gift-brand)' : 'var(--gift-border)'}`,
                    borderRadius: 'var(--gift-radius-md)',
                    background: privacy === opt.value ? 'var(--gift-brand-light)' : 'var(--gift-card)',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="radio"
                    name="gift-privacy"
                    value={opt.value}
                    checked={privacy === opt.value}
                    onChange={() => setPrivacy(opt.value)}
                    style={{ accentColor: 'var(--gift-brand)' }}
                  />
                  <span style={{ fontWeight: privacy === opt.value ? 600 : 400 }}>{opt.label}</span>
                  <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--gift-text-secondary)' }}>{opt.hint}</span>
                </label>
              ))}
            </div>
          </div>

          {/* 照片：仅文字模式无需上传 */}
          {privacy !== 'text' ? (
            <div>
              <ImageUpload
                value={photoUrl}
                onChange={setPhotoUrl}
                label={privacy === 'blur' ? '上传照片（将模糊展示）' : '上传照片'}
                hint={privacy === 'blur' ? '照片会以模糊效果展示在礼物墙，其他人点击可查看原图' : undefined}
              />
            </div>
          ) : (
            <p className="form-hint" style={{ margin: 0 }}>📝 仅文字模式：无需上传照片，写好评价即可晒出</p>
          )}

          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="btn btn-secondary" style={{ flex: 1 }} onClick={() => { setEditing(false); load() }} disabled={saving}>
              取消
            </button>
            <button type="button" className="btn btn-primary" style={{ flex: 1 }} onClick={submit} disabled={saving}>
              {saving ? '提交中…' : posted ? '保存修改' : '晒出礼物 🎉'}
            </button>
          </div>
        </div>
      )}

      {confirmDelete && (
        <div className="modal-overlay" onClick={() => setConfirmDelete(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>删除晒图？</h3>
            <p style={{ marginTop: 8 }}>
              删除后你的评分、评价和照片会从礼物墙移除，礼物卡片将恢复未揭晓状态。此操作不可撤销。
            </p>
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setConfirmDelete(false)} disabled={deleting}>
                取消
              </button>
              <button
                className="btn btn-primary"
                style={{ flex: 1, background: 'var(--gift-error)' }}
                onClick={onDelete}
                disabled={deleting}
              >
                {deleting ? '删除中…' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ===== 送礼状态机进度条（Luna 独到项）：🛒 待购买 → 📦 已发货 → ✅ 已签收 → ✨ 已晒图 =====
const SHIPMENT_STEPS = [
  { key: 'purchase', icon: '🛒', label: '待购买' },
  { key: 'shipped', icon: '📦', label: '已发货' },
  { key: 'received', icon: '✅', label: '已签收' },
  { key: 'posted', icon: '✨', label: '已晒图' },
] as const

// 兜底推导：旧后端无 shipmentState 字段时，从现有字段推算同一状态机
function deriveShipmentState(myMatch: MyMatch): string {
  const { shipment, giftPost } = myMatch
  if (giftPost.review) return 'posted'
  if (giftPost.receivedAt) return 'received'
  if (shipment.trackingNumber || shipment.status !== 'pending') return 'shipped'
  return 'purchase'
}

function ShipmentProgress({ state }: { state: string }) {
  const currentIndex = SHIPMENT_STEPS.findIndex((s) => s.key === state)
  return (
    <div className="ship-progress" role="list" aria-label="送礼进度">
      {SHIPMENT_STEPS.map((s, i) => (
        <div className="ship-progress-step-wrap" key={s.key}>
          <div
            className={`ship-progress-step${i < currentIndex ? ' done' : ''}${i === currentIndex ? ' active' : ''}`}
          >
            <div className="ship-progress-dot" aria-hidden="true">
              {i < currentIndex ? '✓' : s.icon}
            </div>
            <div className="ship-progress-label">{s.label}</div>
          </div>
          {i < SHIPMENT_STEPS.length - 1 && (
            <div className={`ship-progress-line${i < currentIndex ? ' done' : ''}`} />
          )}
        </div>
      ))}
    </div>
  )
}

// ===== 活动流程步骤条（活动级）：📣 招募中 → 🎯 已截止待抽签 → 🎁 送礼进行中 → 🏆 已完结 =====
const FLOW_STEPS = [
  { key: 'recruiting', icon: '📣', label: '招募中' },
  { key: 'drawing', icon: '🎯', label: '已截止待抽签' },
  { key: 'active', icon: '🎁', label: '送礼进行中' },
  { key: 'completed', icon: '🏆', label: '已完结' },
] as const

// 当前用户在该阶段的一句行动指引（组织者/参与者视角区分）
function flowHint(state: string, opts: { isOwner: boolean; joined: boolean; participantCount: number }): string {
  switch (state) {
    case 'recruiting':
      if (opts.isOwner) return `招募中：分享邀请码让朋友加入（当前 ${opts.participantCount} 人）`
      return opts.joined ? '你已加入，等待组织者抽签' : '招募中：点击「加入这个活动」参与'
    case 'drawing':
      return opts.isOwner ? '报名已截止，点击「开始抽签」' : '报名已截止，等待组织者抽签'
    case 'active':
      return opts.joined ? '去完成你的送礼任务，收到礼物记得晒图' : '送礼进行中，看看大家的礼物墙'
    case 'completed':
      return '活动已完结，去礼物墙看看大家的分享'
    default:
      return ''
  }
}

function FlowSteps({
  state,
  isOwner,
  joined,
  participantCount,
}: {
  state: string
  isOwner: boolean
  joined: boolean
  participantCount: number
}) {
  // 未知状态兜底：定位到「送礼进行中」，避免步骤条空态
  const currentIndex = FLOW_STEPS.findIndex((s) => s.key === state)
  const idx = currentIndex === -1 ? 2 : currentIndex
  return (
    <div className="flow-steps" role="list" aria-label="活动流程">
      {FLOW_STEPS.map((s, i) => (
        <div className="flow-step-wrap" key={s.key}>
          <div className={`flow-step${i < idx ? ' done' : ''}${i === idx ? ' active' : ''}`}>
            <div className="flow-step-dot" aria-hidden="true">
              {i < idx ? '✓' : s.icon}
            </div>
            <div className="flow-step-label">{s.label}</div>
          </div>
          {i < FLOW_STEPS.length - 1 && (
            <div className={`flow-step-line${i < idx ? ' done' : ''}`} />
          )}
        </div>
      ))}
      <div className="flow-hint">{flowHint(state, { isOwner, joined, participantCount })}</div>
    </div>
  )
}

// ===== 发货区组件：物流状态 + 填单号 + 悄悄话 =====
function ShipmentSection({
  code,
  matchId,
  shipment,
  note,
  onUpdated,
}: {
  code: string
  matchId: number
  shipment: { status: string; carrier: string; trackingNumber: string; trackingSummary: string }
  note: string
  onUpdated: () => void
}) {
  const { toast } = useToast()
  const [carrier, setCarrier] = useState(shipment.carrier || '')
  const [trackingNumber, setTrackingNumber] = useState(shipment.trackingNumber || '')
  const [secretNote, setSecretNote] = useState(note || '')
  const [saving, setSaving] = useState(false)
  const [showForm, setShowForm] = useState(!shipment.trackingNumber)

  const saveShipment = async () => {
    if (!trackingNumber.trim()) {
      toast('请填写快递单号', 'error')
      return
    }
    setSaving(true)
    try {
      await api.put(`/events/${code}/shipment`, {
        matchId,
        carrier: carrier.trim(),
        trackingNumber: trackingNumber.trim(),
        status: 'shipped',
      })
      // 悄悄话单独保存（允许空）
      await api.put(`/events/${code}/note`, { matchId, note: secretNote.trim() })
      toast('发货信息已保存 🚚')
      setShowForm(false)
      onUpdated()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '保存失败', 'error')
    } finally {
      setSaving(false)
    }
  }

  const shipmentStatusLabel = () => {
    if (shipment.status === 'delivered') return '已送达'
    if (shipment.status === 'shipped') return '已发货'
    return '未发货'
  }

  return (
    <div style={{ marginTop: 16, borderTop: '1px solid var(--gift-border)', paddingTop: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <h3 style={{ fontSize: 16, fontWeight: 600 }}>🚚 发货进度</h3>
        <Badge tone={shipment.status === 'delivered' ? 'success' : shipment.status === 'shipped' ? 'info' : 'warning'}>
          {shipmentStatusLabel()}
        </Badge>
      </div>

      {shipment.trackingNumber && (
        <div style={{ fontSize: 14, color: 'var(--gift-text-secondary)', marginBottom: 8 }}>
          <p>单号：{shipment.trackingNumber}{shipment.carrier ? `（${shipment.carrier}）` : ''}</p>
          {shipment.trackingSummary && (
            <p style={{ marginTop: 4, color: 'var(--gift-text-primary)' }}>📦 {shipment.trackingSummary}</p>
          )}
        </div>
      )}

      {!showForm ? (
        <button className="btn btn-secondary btn-sm" style={{ width: 'auto' }} onClick={() => setShowForm(true)}>
          {shipment.trackingNumber ? '修改物流信息' : '填写快递单号'}
        </button>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              className="form-input"
              style={{ flex: 1 }}
              placeholder="快递公司（选填）"
              value={carrier}
              onChange={(e) => setCarrier(e.target.value)}
              maxLength={80}
            />
            <input
              className="form-input"
              style={{ flex: 2 }}
              placeholder="快递单号 *"
              value={trackingNumber}
              onChange={(e) => setTrackingNumber(e.target.value)}
              maxLength={120}
            />
          </div>
          <input
            className="form-input"
            placeholder="附一句悄悄话（选填）💌"
            value={secretNote}
            onChange={(e) => setSecretNote(e.target.value)}
            maxLength={500}
          />
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary btn-sm" style={{ flex: 1 }} onClick={() => setShowForm(false)}>
              取消
            </button>
            <button className="btn btn-primary btn-sm" style={{ flex: 1 }} onClick={saveShipment} disabled={saving}>
              {saving ? '保存中…' : '确认发货'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
