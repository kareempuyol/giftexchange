// 文案暂未接入 i18n（示范迁移仅 Header/登录页/Toast 公共文案）：后续按 i18n.ts 迁移指南接入
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError, EventInfo, EventPreview, GiftPrivacy, MemberStatus, Participant, MyMatch, ReceivedGift, User } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Badge from '../components/Badge'
import ImageUpload from '../components/ImageUpload'
import { useToast } from '../components/Toast'
import PosterModal, { PosterData } from '../components/PosterModal'
import Modal from '../components/Modal'
import SafeImage from '../components/SafeImage'
import { formatDeadline, formatMoney } from '../utils/format'
import { t, useLocale } from '../i18n'

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
  useLocale()

  const [event, setEvent] = useState<EventInfo | null>(null)
  const [preview, setPreview] = useState<EventPreview | null>(null)
  const [participants, setParticipants] = useState<Participant[]>([])
  const [myMatch, setMyMatch] = useState<MyMatch | null>(null)
  const [joined, setJoined] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [loadErrStatus, setLoadErrStatus] = useState(0)
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
    setLoadError('')
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
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t('加载活动失败，请稍后重试'))
      setLoadErrStatus(err instanceof ApiError ? err.status : 0)
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
      toast(t('抽签完成！'))
      setConfirmDraw(false)
      load()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : t('抽签失败'), 'error')
    } finally {
      setDrawing(false)
    }
  }

  const onRedraw = async () => {
    setRedrawing(true)
    try {
      await api.post(`/events/${code}/redraw`)
      toast(t('已重新抽签！请查看新的任务'))
      setConfirmRedraw(false)
      load()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : t('重新抽签失败'), 'error')
    } finally {
      setRedrawing(false)
    }
  }

  // 催办未完成成员：仅组织者视角，给未完成者（未填信息/未发货/未晒图）发站内提醒
  const onRemind = async () => {
    setReminding(true)
    try {
      const res = await api.post<{ reminded: number }>(`/events/${code}/remind`)
      toast(t('已提醒 {reminded} 人', { reminded: res.reminded }))
    } catch (err) {
      toast(err instanceof ApiError ? err.message : t('催办失败'), 'error')
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
      toast(t('邀请链接已复制！'))
    } catch {
      // 剪贴板不可用（如非 HTTPS）时退化为选中提示
      toast(t('邀请链接：{inviteUrl}', { inviteUrl }), 'info')
    }
  }

  // 复制短码本身
  const copyShortCode = async () => {
    const sc = event?.shortCode || ''
    try {
      await navigator.clipboard.writeText(sc)
      toast(t('邀请码 {sc} 已复制！', { sc }))
    } catch {
      toast(t('邀请码：{sc}', { sc }), 'info')
    }
  }

  // 归档活动：仅组织者、drawn 态；归档后从「我创建的」列表隐藏，进「已归档」（可恢复）
  const onArchive = async () => {
    setArchiving(true)
    try {
      await api.post(`/events/${code}/archive`)
      toast(t('活动已归档'))
      setConfirmArchive(false)
      navigate('/events')
    } catch (err) {
      toast(err instanceof ApiError ? err.message : t('归档失败'), 'error')
    } finally {
      setArchiving(false)
    }
  }

  // 重置邀请短码：旧码立即失效，刷新后显示新码
  const onResetShortCode = async () => {
    setResetting(true)
    try {
      await api.post(`/events/${code}/reset-short-code`)
      toast(t('邀请码已重置，旧邀请码已失效'))
      setConfirmResetCode(false)
      load()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : t('重置失败'), 'error')
    } finally {
      setResetting(false)
    }
  }

  if (loading) return <div className="page-loading"><span className="spinner" aria-hidden="true" />{t('加载中…')}</div>

  // 加载失败：404 给「活动不存在」友好页；其他错误给出说明 + 重试
  if (loadError) {
    const notFound = loadErrStatus === 404
    return (
      <div className="page-container" style={{ maxWidth: 760 }}>
        <div className="page-header">
          <h1 className="page-title">{t('活动详情')}</h1>
          <Link to="/events" className="btn btn-ghost btn-sm">{t('返回')}</Link>
        </div>
        <div className="empty-state gift-card">
          <div className="empty-title">{notFound ? t('活动不存在') : t('加载失败')}</div>
          <p className="empty-sub">
            {notFound ? t('活动不存在或已失效，链接可能有误') : loadError}
          </p>
          {notFound ? (
            <Link to="/events" className="btn btn-primary btn-sm" style={{ width: 'auto', marginTop: 12 }}>
              {t('回我的活动')}
            </Link>
          ) : (
            <button className="btn btn-secondary btn-sm" style={{ width: 'auto', marginTop: 12 }} onClick={load}>
              {t('重试')}
            </button>
          )}
        </div>
      </div>
    )
  }

  // 游客模式：邀请落地预览（不泄露收件人/发货等敏感信息）
  if (!user) {
    if (!preview) return <div className="page-loading"><span className="spinner" aria-hidden="true" />{t('加载中…')}</div>
    return (
      <div className="page-container" style={{ maxWidth: 760 }}>
        <div className="page-header">
          <h1 className="page-title">{preview.title}</h1>
          <Link to="/events" className="btn btn-ghost btn-sm">{t('返回')}</Link>
        </div>

        <div className="gift-card" style={{ marginBottom: 16 }}>
          {preview.coverImage && (
            <img
              src={preview.coverImage}
              alt={t('活动封面')}
              style={{ width: '100%', maxHeight: 240, objectFit: 'cover', borderRadius: 'var(--gift-radius-md)', marginBottom: 12 }}
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          )}
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <Badge tone={preview.status === 'open' ? 'success' : 'gold'}>
              {preview.status === 'open' ? t('报名中') : t('已抽签')}
            </Badge>
            {preview.isPublic ? <Badge tone="info">{t('公开活动')}</Badge> : <Badge tone="warning">{t('私密活动')}</Badge>}
          </div>

          {preview.note && <p style={{ color: 'var(--gift-text-secondary)', marginBottom: 12 }}>{preview.note}</p>}

          <div className="event-meta-grid">
            {preview.budget ? <div><span className="meta-label">{t('预算')}</span><span className="meta-value">{formatMoney(preview.budget)}</span></div> : null}
            <div><span className="meta-label">{t('参与人数')}</span><span className="meta-value">{t('{count} 人', { count: preview.participantCount })}</span></div>
            {preview.signUpDeadline ? (
              <div><span className="meta-label">{t('报名截止')}</span><span className="meta-value">{formatDeadline(preview.signUpDeadline)}</span></div>
            ) : null}
          </div>

          <p style={{ color: 'var(--gift-text-secondary)', margin: '16px 0' }}>
            {preview.status === 'open'
              ? t('朋友邀请你参加「{title}」🎁 登录后即可查看详情并加入', { title: preview.title })
              : t('这个活动已经开始啦，登录后看看大家交换了什么礼物吧')}
          </p>

          <Link to={`/login?from=${encodeURIComponent(`events/${code}`)}`} className="btn btn-primary">
            {t('登录后加入')}
          </Link>
          <div style={{ textAlign: 'center', marginTop: 12, fontSize: 'var(--gift-font-sm)' }}>
            <Link to={`/register?from=${encodeURIComponent(`events/${code}`)}`} style={{ color: 'var(--gift-brand)' }}>
              {t('没有账号？立即注册')}
            </Link>
          </div>
        </div>
      </div>
    )
  }

  if (!event) return <div className="page-container">{t('活动不存在')}</div>

  // 活动级流程状态（Task A）：由后端 detail 接口推导；旧后端缺失时按 status 兜底
  const flowState =
    (event as EventInfo & { flowState?: string }).flowState ||
    (event.status === 'open' ? 'recruiting' : 'active')
  // 提前算好供 t() 插值：未填完整收件信息的人数 / 预算参考文案
  const incompleteCount = participants.filter((p) => !p.contactComplete).length
  const budgetRef = formatMoney(event.budget)

  return (
    <div className="page-container page-container--wide">
      <div className="page-header">
        <h1 className="page-title">{event.title}</h1>
        <Link to="/events" className="btn btn-ghost btn-sm">{t('返回')}</Link>
      </div>

      <div className="detail-layout">
      <div className="detail-col-left">
      <div className="gift-card" style={{ marginBottom: 16, overflow: 'hidden' }}>
        {/* 活动封面（登录态也展示） */}
        {event.coverImage && (
          <div style={{ margin: '-16px -16px 12px' }}>
            <SafeImage
              src={event.coverImage}
              alt={t('活动封面')}
              style={{ width: '100%', height: 180, objectFit: 'cover', display: 'block' }}
            />
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Badge tone={event.status === 'open' ? 'success' : 'gold'}>
            {event.status === 'open' ? t('报名中') : t('已抽签')}
          </Badge>
          {event.isPublic ? <Badge tone="info">{t('公开活动')}</Badge> : <Badge tone="warning">{t('私密活动')}</Badge>}
          {isOwner && <Badge tone="gold">{t('我是组织者')}</Badge>}
        </div>

        {/* 邀请区：短码 + 复制链接 + 复制短码 */}
        {event.shortCode && (
          <div className="invite-box" style={{ flexWrap: 'wrap' }}>
            <div className="invite-info">
              <span className="invite-label">{t('邀请码')}</span>
              <button className="invite-code-btn" onClick={copyShortCode} title={t('点击复制邀请码')}>
                {event.shortCode} 📋
              </button>
            </div>
            <button
              className="btn btn-primary btn-sm"
              style={{ width: 'auto', flexShrink: 0 }}
              onClick={copyInviteLink}
            >
              {t('📋 复制邀请链接')}
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
              {t('🖼️ 邀请海报')}
            </button>
            {isOwner && (
              <button
                className="btn btn-ghost btn-sm"
                style={{ width: 'auto', flexShrink: 0 }}
                onClick={() => setConfirmResetCode(true)}
              >
                {t('🔄 重置邀请码')}
              </button>
            )}
          </div>
        )}

        {event.note && <p style={{ color: 'var(--gift-text-secondary)', marginBottom: 12 }}>{event.note}</p>}

        <div className="event-meta-grid">
          <div><span className="meta-label">{t('预算')}</span><span className="meta-value">{formatMoney(event.budget)}</span></div>
          <div><span className="meta-label">{t('参与人数')}</span><span className="meta-value">{event.participantCount}</span></div>
          {event.drawDate && (
            <div><span className="meta-label">{t('报名截止')}</span><span className="meta-value">{formatDeadline(event.drawDate)}</span></div>
          )}
          {event.maxParticipants && (
            <div><span className="meta-label">{t('人数上限')}</span><span className="meta-value">{event.maxParticipants}</span></div>
          )}
        </div>

        {/* 活动级流程步骤条（信息区之后，操作按钮之前） */}
        <FlowSteps
          state={flowState}
          isOwner={isOwner}
          joined={joined}
          participantCount={event.participantCount}
        />

        {!isOwner && !joined && event.status === 'open' && (
          <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={() => setShowJoinForm(true)}>
            {t('加入这个活动')}
          </button>
        )}
        {isOwner && !joined && (
          <p style={{ marginTop: 16, color: 'var(--gift-text-secondary)' }}>{t('你是组织者，活动已创建，无需加入')}</p>
        )}

        {isOwner && event.status === 'open' && (
          <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
            <Link to={`/events/${code}/dashboard`} className="btn btn-secondary" style={{ flex: 1 }}>{t('活动管理台')}</Link>
            <button
              className="btn btn-primary"
              style={{ flex: 1 }}
              onClick={() => setConfirmDraw(true)}
              disabled={event.participantCount < 2}
            >
              {event.participantCount < 2 ? t('至少 2 人才能抽签') : t('开始抽签')}
            </button>
          </div>
        )}

        {isOwner && event.status === 'drawn' && (
          <div style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <Link to={`/events/${code}/dashboard`} className="btn btn-secondary" style={{ flex: 1 }}>{t('活动管理台')}</Link>
              <button
                className="btn btn-secondary"
                style={{ flex: 1, color: 'var(--gift-warning-text)', borderColor: 'var(--gift-warning-text)' }}
                onClick={() => setConfirmRedraw(true)}
              >
                {t('重新抽签')}
              </button>
            </div>
            <button
              className="btn btn-secondary"
              style={{ marginTop: 8, width: '100%', color: 'var(--gift-error-text)', borderColor: 'var(--gift-error-text)' }}
              onClick={() => setConfirmArchive(true)}
            >
              {t('归档活动')}
            </button>
          </div>
        )}
      </div>
      </div>{/* detail-col-left */}

      <div className="detail-col-right">
      {confirmDraw && (
        <Modal title={t('确认抽签？')} onClose={() => setConfirmDraw(false)}>
          <p style={{ marginTop: 8 }}>
            <b>{t('当前 {count} 人参与。抽签后不可撤销，每个人将获得一个送礼对象。', { count: event.participantCount })}</b>
          </p>
          {event.excludedPairs.length > 0 && (
            <p style={{ marginTop: 8, fontSize: 14, color: 'var(--gift-warning-text)' }}>
              {t('⚠️ 已配置 {count} 组互避规则，抽签时会避开这些配对', { count: event.excludedPairs.length })}
            </p>
          )}
          <p style={{ marginTop: 8, fontSize: 14, color: 'var(--gift-text-secondary)' }}>
            {incompleteCount > 0 && t('提示：{count} 人未填完整收件信息，抽签后对方可能收不到礼物。', { count: incompleteCount })}
          </p>
          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <button className="btn btn-secondary" onClick={() => setConfirmDraw(false)}>{t('取消')}</button>
            <button className="btn btn-primary" onClick={onDraw} disabled={drawing}>
              {drawing ? t('抽签中…') : t('确认抽签')}
            </button>
          </div>
        </Modal>
      )}

      {confirmRedraw && (
        <Modal title={t('重新抽签？')} onClose={() => setConfirmRedraw(false)}>
          <p style={{ marginTop: 8 }}>
            {t('所有成员的任务将重置，已发货/已晒图的数据会清空，此操作不可撤销。')}
          </p>
          {event.excludedPairs.length > 0 && (
            <p style={{ marginTop: 8, fontSize: 14, color: 'var(--gift-warning-text)' }}>
              {t('⚠️ 已配置 {count} 组互避规则，重新抽签会继续避开这些配对', { count: event.excludedPairs.length })}
            </p>
          )}
          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setConfirmRedraw(false)} disabled={redrawing}>
              {t('取消')}
            </button>
            <button
              className="btn btn-primary"
              style={{ flex: 1, background: 'var(--gift-error)' }}
              onClick={onRedraw}
              disabled={redrawing}
            >
              {redrawing ? t('重抽中…') : t('确认重新抽签')}
            </button>
          </div>
        </Modal>
      )}

      {confirmArchive && (
        <Modal title={t('归档活动？')} onClose={() => setConfirmArchive(false)}>
          <p style={{ marginTop: 8 }}>
            {t('归档后活动将从「我创建的」列表隐藏，进入「已归档」。详情页、礼物墙、管理台数据不受影响，可随时恢复。')}
          </p>
          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setConfirmArchive(false)} disabled={archiving}>
              {t('取消')}
            </button>
            <button
              className="btn btn-primary"
              style={{ flex: 1, background: 'var(--gift-error)' }}
              onClick={onArchive}
              disabled={archiving}
            >
              {archiving ? t('归档中…') : t('确认归档')}
            </button>
          </div>
        </Modal>
      )}

      {confirmResetCode && (
        <Modal title={t('重置邀请码？')} onClose={() => setConfirmResetCode(false)}>
          <p style={{ marginTop: 8 }}>
            {t('旧邀请码将立即失效，已转发的旧邀请链接将无法再进入活动，此操作不可撤销。')}
          </p>
          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setConfirmResetCode(false)} disabled={resetting}>
              {t('取消')}
            </button>
            <button className="btn btn-primary" style={{ flex: 1 }} onClick={onResetShortCode} disabled={resetting}>
              {resetting ? t('重置中…') : t('确认重置')}
            </button>
          </div>
        </Modal>
      )}

      {joined && myMatch && event.status === 'drawn' && (
        <div className="gift-card" style={{ marginBottom: 16 }}>
          <h2 className="section-title">{t('🎯 我的送礼任务')}</h2>
          <p style={{ marginTop: 8, fontSize: 18 }}>
            <b style={{ color: 'var(--gift-brand)' }}>{t('我要送给 {name}', { name: myMatch.receiverDisplayName })}</b>
          </p>
          <div style={{ marginTop: 12, fontSize: 14, color: 'var(--gift-text-secondary)' }}>
            <p>{t('💰 预算参考：{budget}', { budget: budgetRef })}</p>
            {myMatch.preference.likes && <p>{t('❤️ 喜欢：{likes}', { likes: myMatch.preference.likes })}</p>}
            {myMatch.preference.dislikes && <p>{t('🚫 不喜欢：{dislikes}', { dislikes: myMatch.preference.dislikes })}</p>}
            {myMatch.preference.size && <p>{t('📏 尺码：{size}', { size: myMatch.preference.size })}</p>}
            {myMatch.preference.color && <p>{t('🎨 颜色：{color}', { color: myMatch.preference.color })}</p>}
            {myMatch.preference.wishLinks.length > 0 && (
              <p>
                {t('🎁 心愿链接：')}
                {myMatch.preference.wishLinks.map((link, i) => (
                  <a key={i} href={link} target="_blank" rel="noreferrer" style={{ marginLeft: 8 }}>
                    {t('心愿{i} ↗', { i: i + 1 })}
                  </a>
                ))}
              </p>
            )}
            {myMatch.preference.notes && <p>{t('📝 备注：{notes}', { notes: myMatch.preference.notes })}</p>}
            {/* 悄悄话：仅当收礼人已晒图后才揭晓（纯前端门控，receivedAt 非空 = 收礼人已晒图） */}
            {myMatch.note &&
              (myMatch.giftPost.receivedAt ? (
                <p>{t('💬 悄悄话：{note}', { note: myMatch.note })}</p>
              ) : (
                <p className="note-pending">{t('💬 悄悄话：收礼人晒图后揭晓 ✨')}</p>
              ))}
          </div>
          <div style={{ marginTop: 12, padding: 12, background: 'var(--gift-bg-muted)', borderRadius: 12 }}>
            <p><b>{t('收件人：')}</b>{myMatch.contact.receiverName}</p>
            <p><b>{t('电话：')}</b>{myMatch.contact.phone}</p>
            <p><b>{t('地址：')}</b>{myMatch.contact.address}</p>
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
              <h2 className="section-title">{t('🎁 礼物墙')}</h2>
              <p style={{ marginTop: 4, fontSize: 14, color: 'var(--gift-text-secondary)' }}>
                {t('看看大家都收到了什么礼物，给喜欢的点赞！')}
              </p>
            </div>
            <Link to={`/events/${code}/gift-wall`} className="btn btn-primary" style={{ flexShrink: 0, width: 'auto' }}>
              {t('去看看')}
            </Link>
          </div>
        </div>
      )}
      </div>{/* detail-col-right */}
      </div>{/* detail-layout */}

      <div className="gift-card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <h2 className="section-title" style={{ margin: 0 }}>{t('参与者（{count}）', { count: participants.length })}</h2>
          {isOwner && (
            <button
              className="btn btn-primary btn-sm"
              style={{ width: 'auto', flexShrink: 0 }}
              onClick={onRemind}
              disabled={reminding}
            >
              {reminding ? t('催办中…') : t('催办未完成成员')}
            </button>
          )}
        </div>
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {participants.length === 0 ? (
            <div className="empty-state" style={{ padding: 'var(--gift-space-xl) var(--gift-space-lg)' }}>
              <div className="empty-title" style={{ fontSize: 'var(--gift-font-md)' }}>{t('还没有人加入')}</div>
              <p className="empty-sub">
                {isOwner
                  ? t('分享邀请码或复制邀请链接，把朋友拉进来一起玩')
                  : t('等组织者邀请更多朋友后，就可以开始抽签啦')}
              </p>
              {isOwner && (
                <button className="btn btn-primary btn-sm" style={{ width: 'auto', marginTop: 12 }} onClick={copyInviteLink}>
                  {t('📋 复制邀请链接')}
                </button>
              )}
            </div>
          ) : (
            participants.map((p) => {
              const status = p.status ?? (p.contactComplete ? 'ready' : 'joined')
              const meta = MEMBER_STATUS_META[status]
              return (
                <div key={p.id} className="participant-row">
                  <span style={{ fontWeight: 500 }}>{p.displayName || p.username}</span>
                  <span style={{ display: 'flex', gap: 6 }}>
                    <Badge tone={meta.tone}>{t(meta.label)}</Badge>
                  </span>
                </div>
              )
            })
          )}
        </div>
      </div>

      {showJoinForm && (
        <JoinForm
          code={code}
          onClose={() => setShowJoinForm(false)}
          onJoined={() => {
            setShowJoinForm(false)
            load()
            toast(t('加入成功！'))
          }}
        />
      )}

      <PosterModal data={poster} onClose={() => setPoster(null)} />
    </div>
  )
}

function JoinForm({ code, onClose, onJoined }: { code: string; onClose: () => void; onJoined: () => void }) {
  const { toast } = useToast()
  useLocale()
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
  const [prefilled, setPrefilled] = useState(false)

  // 资料预填：个人中心已保存的收件人/电话/地址/偏好自动带入（仅填空字段，不覆盖用户手输）
  useEffect(() => {
    let cancelled = false
    api
      .get<User>('/profile')
      .then((p) => {
        if (cancelled) return
        if (p.receiverName) setReceiverName(p.receiverName)
        if (p.phone) setPhone(p.phone)
        if (p.address) setAddress(p.address)
        if (p.giftPreference) setLikes(p.giftPreference)
        if (p.receiverName || p.phone || p.address || p.giftPreference) setPrefilled(true)
      })
      .catch(() => {
        /* 预填失败静默：表单保持空值 */
      })
    return () => {
      cancelled = true
    }
  }, [])

  // 第一步校验通过才进第二步
  const goNext = () => {
    if (!receiverName || !phone || !address) {
      setError(t('请填写收件人姓名、电话和地址（必填）'))
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
      setError(err instanceof ApiError ? err.message : t('加入失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal title={t('加入活动')} onClose={onClose} maxWidth={520}>
      {/* 步骤指示器 */}
      <div className="step-indicator">
        <div className={`step-dot${step === 1 ? ' active' : ''}${step === 2 ? ' done' : ''}`}>
          <span>{step === 2 ? '✓' : '1'}</span>
        </div>
        <div className={`step-line${step === 2 ? ' done' : ''}`} />
        <div className={`step-dot${step === 2 ? ' active' : ''}`}><span>2</span></div>
        <div className="step-labels">
          <span className={step === 1 ? 'current' : ''} aria-current={step === 1 ? 'step' : undefined}>{t('收件信息')}</span>
          <span className={step === 2 ? 'current' : ''} aria-current={step === 2 ? 'step' : undefined}>{t('心愿单')}</span>
        </div>
      </div>

        <form onSubmit={onSubmit}>
          {step === 1 ? (
            <>
              {prefilled && (
                <p className="form-hint" style={{ marginBottom: 8, color: 'var(--gift-brand)' }}>
                  {t('📋 已从个人资料自动填入，可修改')}
                </p>
              )}
              <p className="form-hint" style={{ marginBottom: 16 }}>
                {t('抽签后，送你礼物的人会看到这些信息来寄礼物')}
              </p>
              <div className="form-group">
                <label className="form-label" htmlFor="join-receiver">{t('收件人姓名 *')}</label>
                <input id="join-receiver" className="form-input" placeholder={t('真实姓名')} value={receiverName} onChange={(e) => setReceiverName(e.target.value)} maxLength={120} aria-describedby={error ? 'join-error' : undefined} />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="join-phone">{t('联系电话 *')}</label>
                <input id="join-phone" className="form-input" type="tel" placeholder={t('手机号')} value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={50} aria-describedby={error ? 'join-error' : undefined} />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="join-address">{t('收件地址 *')}</label>
                <textarea id="join-address" className="form-textarea" placeholder={t('省市区 + 详细地址')} value={address} onChange={(e) => setAddress(e.target.value)} maxLength={500} aria-describedby={error ? 'join-error' : undefined} />
              </div>
              {error && <div id="join-error" className="form-error" role="alert" style={{ marginBottom: 12 }}>{error}</div>}
              <div style={{ display: 'flex', gap: 8 }}>
                <button type="button" className="btn btn-secondary" onClick={onClose} style={{ flex: 1 }}>{t('取消')}</button>
                <button type="button" className="btn btn-primary" onClick={goNext} style={{ flex: 1 }}>{t('下一步')}</button>
              </div>
            </>
          ) : (
            <>
              <p className="form-hint" style={{ marginBottom: 16 }}>
                {t('让送礼的人更懂你（全部选填，但填得越多礼物越合心意 🎁）')}
              </p>
              <div className="form-group">
                <label className="form-label" htmlFor="join-likes">{t('我喜欢的礼物')}</label>
                <input id="join-likes" className="form-input" placeholder={t('例如：咖啡、书、手作')} value={likes} onChange={(e) => setLikes(e.target.value)} maxLength={500} />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="join-dislikes">{t('我不想要的')}</label>
                <input id="join-dislikes" className="form-input" placeholder={t('例如：香水、毛绒玩具')} value={dislikes} onChange={(e) => setDislikes(e.target.value)} maxLength={500} />
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <div className="form-group" style={{ flex: 1 }}>
                  <label className="form-label" htmlFor="join-size">{t('尺码（选填）')}</label>
                  <input id="join-size" className="form-input" placeholder={t('如 M / 42 码')} value={size} onChange={(e) => setSize(e.target.value)} maxLength={50} />
                </div>
                <div className="form-group" style={{ flex: 1 }}>
                  <label className="form-label" htmlFor="join-color">{t('喜欢的颜色（选填）')}</label>
                  <input id="join-color" className="form-input" placeholder={t('如 莫兰迪色系')} value={color} onChange={(e) => setColor(e.target.value)} maxLength={80} />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="join-wishlinks">{t('心愿链接（选填，最多 3 个）')}</label>
                <input id="join-wishlinks" className="form-input" placeholder={t('淘宝/京东等商品链接，逗号分隔')} value={wishLinks} onChange={(e) => setWishLinks(e.target.value)} maxLength={500} />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="join-notes">{t('备注（选填）')}</label>
                <textarea id="join-notes" className="form-textarea" placeholder={t('其他想说的话')} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} />
              </div>
              {error && <div id="join-error" className="form-error" role="alert" style={{ marginBottom: 12 }}>{error}</div>}
              <div style={{ display: 'flex', gap: 8 }}>
                <button type="button" className="btn btn-secondary" onClick={() => { setStep(1); setError('') }} style={{ flex: 1 }}>{t('上一步')}</button>
                <button type="submit" className="btn btn-primary" disabled={submitting} style={{ flex: 1 }}>
                  {submitting ? t('提交中…') : t('确认加入')}
                </button>
              </div>
            </>
          )}
        </form>
    </Modal>
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
  useLocale()
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
      toast(t('晒图已删除'))
      setConfirmDelete(false)
      setEditing(false)
      load()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : t('删除失败'), 'error')
    } finally {
      setDeleting(false)
    }
  }

  const submit = async () => {
    if (!received) return
    if (rating < 1 || rating > 5) {
      toast(t('请先给礼物评分 ⭐'), 'error')
      return
    }
    if (!review.trim()) {
      toast(t('请填写评价内容'), 'error')
      return
    }
    if (privacy !== 'text' && !photoUrl.trim()) {
      toast(t('请上传一张照片（或选择「仅文字」模式）'), 'error')
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
      toast(t('晒图成功 🎉'))
      setEditing(false)
      load()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : t('保存失败'), 'error')
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
      <h2 className="section-title">{t('🎁 我收到的礼物')}</h2>
      <p style={{ marginTop: 8, fontSize: 14, color: 'var(--gift-text-secondary)' }}>
        {posted
          ? t('来自 {giverName} 的礼物，你已晒出（{privacy}）', { giverName, privacy: t(PRIVACY_LABEL[curPrivacy]) })
          : t('来自 {giverName} 的礼物 —— 晒出后，礼物墙就离解锁更近一步 🎀', { giverName })}
      </p>

      {posted && !editing ? (
        <div style={{ marginTop: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <span className="gw-stars" aria-label={t('评分 {rating}/5', { rating })}>
              {[1, 2, 3, 4, 5].map((n) => (
                <span key={n} className={n <= (received.giftPost.rating || 0) ? 'gw-star on' : 'gw-star'}>★</span>
              ))}
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" className="btn btn-ghost btn-sm" style={{ width: 'auto' }} onClick={startEdit}>
                {t('修改晒图')}
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                style={{ width: 'auto', color: 'var(--gift-error-text)' }}
                onClick={() => setConfirmDelete(true)}
              >
                {t('删除晒图')}
              </button>
            </div>
          </div>
          {received.giftPost.review && (
            <p className="gw-review" style={{ marginTop: 8 }}>“{received.giftPost.review}”</p>
          )}
          {received.giftPost.photoUrl && (
            <div className="gw-photo-wrap" style={{ marginTop: 8 }}>
              <SafeImage
                className={`gw-photo${curPrivacy === 'blur' ? ' gw-photo-blur' : ''}${curPrivacy === 'blur' && blurView ? ' viewing' : ''}`}
                src={received.giftPost.photoUrl}
                alt={curPrivacy === 'blur' ? t('模糊照片，点击查看原图') : t('礼物照片')}
                loading="lazy"
                onClick={curPrivacy === 'blur' ? () => setBlurView((v) => !v) : undefined}
              />
              {curPrivacy === 'blur' && (
                <span className="gw-blur-hint">{blurView ? t('👁 点击隐藏原图') : t('🌫️ 模糊照片 · 点击查看原图')}</span>
              )}
            </div>
          )}
        </div>
      ) : (
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* 评分 */}
          <div>
            <div className="form-label">{t('评分 *')}</div>
            <div className="gw-stars" style={{ fontSize: 28, cursor: 'pointer' }}>
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  className={`gw-star${n <= rating ? ' on' : ''}`}
                  style={{ background: 'none', border: 'none', fontSize: 28, padding: '0 4px', cursor: 'pointer', minWidth: 40, minHeight: 40 }}
                  onClick={() => setRating(n)}
                  aria-label={t('{n} 星', { n })}
                >
                  ★
                </button>
              ))}
            </div>
          </div>

          {/* 评价 */}
          <div>
            <label className="form-label" htmlFor="received-review">{t('评价（选填）')}</label>
            <textarea
              id="received-review"
              className="form-textarea"
              placeholder={t('收到礼物想说点什么？')}
              value={review}
              onChange={(e) => setReview(e.target.value)}
              maxLength={500}
              rows={3}
            />
          </div>

          {/* 隐私形式 */}
          <div>
            <div className="form-label">{t('晒图形式')}</div>
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
                  <span style={{ fontWeight: privacy === opt.value ? 600 : 400 }}>{t(opt.label)}</span>
                  <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--gift-text-secondary)' }}>{t(opt.hint)}</span>
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
                label={privacy === 'blur' ? t('上传照片（将模糊展示）') : t('上传照片')}
                hint={privacy === 'blur' ? t('照片会以模糊效果展示在礼物墙，其他人点击可查看原图') : undefined}
              />
            </div>
          ) : (
            <p className="form-hint" style={{ margin: 0 }}>{t('📝 仅文字模式：无需上传照片，写好评价即可晒出')}</p>
          )}

          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="btn btn-secondary" style={{ flex: 1 }} onClick={() => { setEditing(false); load() }} disabled={saving}>
              {t('取消')}
            </button>
            <button type="button" className="btn btn-primary" style={{ flex: 1 }} onClick={submit} disabled={saving}>
              {saving ? t('提交中…') : posted ? t('保存修改') : t('晒出礼物 🎉')}
            </button>
          </div>
        </div>
      )}

      {confirmDelete && (
        <Modal title={t('删除晒图？')} onClose={() => setConfirmDelete(false)}>
          <p style={{ marginTop: 8 }}>
            {t('删除后你的评分、评价和照片会从礼物墙移除，礼物卡片将恢复未揭晓状态。此操作不可撤销。')}
          </p>
          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setConfirmDelete(false)} disabled={deleting}>
              {t('取消')}
            </button>
            <button
              className="btn btn-primary"
              style={{ flex: 1, background: 'var(--gift-error)' }}
              onClick={onDelete}
              disabled={deleting}
            >
              {deleting ? t('删除中…') : t('确认删除')}
            </button>
          </div>
        </Modal>
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
  useLocale()
  const currentIndex = SHIPMENT_STEPS.findIndex((s) => s.key === state)
  return (
    <div className="ship-progress" role="list" aria-label={t('送礼进度')}>
      {SHIPMENT_STEPS.map((s, i) => (
        <div className="ship-progress-step-wrap" key={s.key}>
          <div
            className={`ship-progress-step${i < currentIndex ? ' done' : ''}${i === currentIndex ? ' active' : ''}`}
            aria-current={i === currentIndex ? 'step' : undefined}
          >
            <div className="ship-progress-dot" aria-hidden="true">
              {i < currentIndex ? '✓' : s.icon}
            </div>
            <div className="ship-progress-label">{t(s.label)}</div>
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
      if (opts.isOwner) return t('招募中：分享邀请码让朋友加入（当前 {count} 人）', { count: opts.participantCount })
      return opts.joined ? t('你已加入，等待组织者抽签') : t('报名截止前加入，即可参与抽签')
    case 'drawing':
      return opts.isOwner ? t('报名已截止，点击「开始抽签」') : t('报名已截止，等待组织者抽签')
    case 'active':
      return opts.joined ? t('去完成你的送礼任务，收到礼物记得晒图') : t('送礼进行中，看看大家的礼物墙')
    case 'completed':
      return t('活动已完结，去礼物墙看看大家的分享')
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
  useLocale()
  // 未知状态兜底：定位到「送礼进行中」，避免步骤条空态
  const currentIndex = FLOW_STEPS.findIndex((s) => s.key === state)
  const idx = currentIndex === -1 ? 2 : currentIndex
  return (
    <div className="flow-steps" role="list" aria-label={t('活动流程')}>
      {FLOW_STEPS.map((s, i) => (
        <div className="flow-step-wrap" key={s.key}>
          <div
            className={`flow-step${i < idx ? ' done' : ''}${i === idx ? ' active' : ''}`}
            aria-current={i === idx ? 'step' : undefined}
          >
            <div className="flow-step-dot" aria-hidden="true">
              {i < idx ? '✓' : s.icon}
            </div>
            <div className="flow-step-label">{t(s.label)}</div>
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
  shipment: { status: string; carrier: string; trackingNumber: string; trackingSummary: string; trackingRefreshable?: boolean }
  note: string
  onUpdated: () => void
}) {
  const { toast } = useToast()
  useLocale()
  const [carrier, setCarrier] = useState(shipment.carrier || '')
  const [trackingNumber, setTrackingNumber] = useState(shipment.trackingNumber || '')
  const [secretNote, setSecretNote] = useState(note || '')
  const [saving, setSaving] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [showForm, setShowForm] = useState(!shipment.trackingNumber)

  // 物流查询失败后的手动刷新：重新外呼 KDNiao（不改发货状态、不重复通知）
  const refreshTracking = async () => {
    setRefreshing(true)
    try {
      // 返回的 trackingRefreshable 表示仍处于失败态：据此给真实反馈，避免「已刷新」误导
      const res = await api.post<{ trackingRefreshable: boolean }>(`/events/${code}/shipment/refresh`, { matchId })
      toast(res.trackingRefreshable ? t('物流查询仍失败，请稍后再试') : t('物流信息已刷新'), res.trackingRefreshable ? 'error' : undefined)
      onUpdated()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : t('刷新失败，请稍后重试'), 'error')
    } finally {
      setRefreshing(false)
    }
  }

  const saveShipment = async () => {
    if (!trackingNumber.trim()) {
      toast(t('请填写快递单号'), 'error')
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
      toast(t('发货信息已保存 🚚'))
      setShowForm(false)
      onUpdated()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : t('保存失败'), 'error')
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
        <h3 style={{ fontSize: 16, fontWeight: 600 }}>{t('🚚 发货进度')}</h3>
        <Badge tone={shipment.status === 'delivered' ? 'success' : shipment.status === 'shipped' ? 'info' : 'warning'}>
          {t(shipmentStatusLabel())}
        </Badge>
      </div>

      {shipment.trackingNumber && (
        <div style={{ fontSize: 14, color: 'var(--gift-text-secondary)', marginBottom: 8 }}>
          <p>{t('单号：')}{shipment.trackingNumber}{shipment.carrier ? t('（{carrier}）', { carrier: shipment.carrier }) : ''}</p>
          {shipment.trackingSummary && (
            <p style={{ marginTop: 4, color: 'var(--gift-text-primary)' }}>📦 {shipment.trackingSummary}</p>
          )}
          {shipment.trackingRefreshable && (
            <button
              className="btn btn-ghost btn-sm"
              style={{ width: 'auto', marginTop: 6 }}
              onClick={refreshTracking}
              disabled={refreshing}
            >
              {refreshing ? t('刷新中…') : t('🔄 刷新物流信息')}
            </button>
          )}
        </div>
      )}

      {!showForm ? (
        <button className="btn btn-secondary btn-sm" style={{ width: 'auto' }} onClick={() => setShowForm(true)}>
          {shipment.trackingNumber ? t('修改物流信息') : t('填写快递单号')}
        </button>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <input
              className="form-input"
              style={{ flex: '1 1 160px' }}
              placeholder={t('快递公司（选填）')}
              aria-label={t('快递公司（选填）')}
              value={carrier}
              onChange={(e) => setCarrier(e.target.value)}
              maxLength={80}
            />
            <input
              className="form-input"
              style={{ flex: '2 1 160px' }}
              placeholder={t('快递单号 *')}
              aria-label={t('快递单号（必填）')}
              value={trackingNumber}
              onChange={(e) => setTrackingNumber(e.target.value)}
              maxLength={120}
            />
          </div>
          <input
            className="form-input"
            placeholder={t('附一句悄悄话（选填）💌')}
            aria-label={t('附一句悄悄话（选填）')}
            value={secretNote}
            onChange={(e) => setSecretNote(e.target.value)}
            maxLength={500}
          />
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary btn-sm" style={{ flex: 1 }} onClick={() => setShowForm(false)}>
              {t('取消')}
            </button>
            <button className="btn btn-primary btn-sm" style={{ flex: 1 }} onClick={saveShipment} disabled={saving}>
              {saving ? t('保存中…') : t('确认发货')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
