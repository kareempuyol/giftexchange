// 文案暂未接入 i18n（示范迁移仅 Header/登录页/Toast 公共文案）：后续按 i18n.ts 迁移指南接入
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, EventInfo } from '../api/client'
import Badge from '../components/Badge'
import { t, useLocale } from '../i18n'

interface DashboardParticipant {
  participantId: number
  userId: number
  displayName: string
  avatarUrl?: string
  contactComplete: boolean
  preferenceComplete: boolean
  hasMatch: boolean
  shipmentStatus: 'pending' | 'shipped' | 'delivered'
  hasTracking: boolean
  received: boolean
  postedGift: boolean
}

interface DashboardReminder {
  type: 'shipment' | 'gift' | 'draw'
  message: string
}

interface DashboardData {
  participants: DashboardParticipant[]
  pendingShipments: number
  unpostedGifts: number
  reminders: DashboardReminder[]
}

const REMINDER_TONE: Record<DashboardReminder['type'], 'success' | 'warning' | 'error' | 'info' | 'gold'> = {
  shipment: 'warning',
  gift: 'info',
  draw: 'error',
}

const REMINDER_LABEL: Record<DashboardReminder['type'], string> = {
  shipment: '待发货',
  gift: '待晒图',
  draw: '待抽签',
}

export default function DashboardPage() {
  const { code = '' } = useParams()
  useLocale() // 订阅语言切换：setLocale 后重渲染
  const [event, setEvent] = useState<EventInfo | null>(null)
  const [rows, setRows] = useState<DashboardParticipant[]>([])
  const [pendingShipments, setPendingShipments] = useState(0)
  const [unpostedGifts, setUnpostedGifts] = useState(0)
  const [reminders, setReminders] = useState<DashboardReminder[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  const load = async () => {
    setLoading(true)
    setLoadError('')
    try {
      const [ev, data] = await Promise.all([
        api.get<EventInfo>(`/events/${code}`),
        api.get<DashboardData>(`/events/${code}/dashboard`),
      ])
      setEvent(ev)
      setRows(data.participants)
      setPendingShipments(data.pendingShipments ?? 0)
      setUnpostedGifts(data.unpostedGifts ?? 0)
      setReminders(data.reminders ?? [])
    } catch (err) {
      // 可能是非组织者，也可能是网络/服务异常：统一给错误说明 + 重试
      setLoadError(err instanceof Error ? err.message : t('加载失败，请稍后重试'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code])

  if (loading) return <div className="page-loading"><span className="spinner" aria-hidden="true" />{t('加载中…')}</div>
  if (loadError || !event)
    return (
      <div className="page-container" style={{ maxWidth: 860 }}>
        <div className="page-header">
          <h1 className="page-title">{t('活动管理台')}</h1>
          <Link to={`/events/${code}`} className="btn btn-ghost btn-sm">{t('返回活动')}</Link>
        </div>
        <div className="empty-state gift-card">
          <div className="empty-title">{t('无法查看管理台')}</div>
          <p className="empty-sub">{loadError || t('无权限或活动不存在')}</p>
          <button className="btn btn-secondary btn-sm" style={{ width: 'auto', marginTop: 12 }} onClick={load}>
            {t('重试')}
          </button>
        </div>
      </div>
    )

  const shipped = rows.filter((r) => r.shipmentStatus !== 'pending').length
  const received = rows.filter((r) => r.received).length
  const posted = rows.filter((r) => r.postedGift).length

  return (
    <div className="page-container" style={{ maxWidth: 860 }}>
      <div className="page-header">
        <h1 className="page-title">{t('活动管理台')}</h1>
        <Link to={`/events/${code}`} className="btn btn-ghost btn-sm">{t('返回活动')}</Link>
      </div>

      {reminders.length > 0 && (
        <div className="dash-reminders">
          {reminders.map((r) => (
            <div key={r.type} className="reminder-card">
              <Badge tone={REMINDER_TONE[r.type]}>{t(REMINDER_LABEL[r.type])}</Badge>
              <span className="reminder-message">{r.message}</span>
            </div>
          ))}
        </div>
      )}

      <div className="dash-stats">
        <div className="stat-card"><div className="stat-num">{rows.length}</div><div className="stat-label">{t('参与人数')}</div></div>
        <div className="stat-card"><div className="stat-num">{shipped}</div><div className="stat-label">{t('已发货')}</div></div>
        <div className="stat-card"><div className="stat-num">{received}</div><div className="stat-label">{t('已收货')}</div></div>
        <div className="stat-card"><div className="stat-num">{posted}</div><div className="stat-label">{t('已晒图')}</div></div>
        <div className="stat-card"><div className="stat-num warn">{pendingShipments}</div><div className="stat-label">{t('待发货')}</div></div>
        <div className="stat-card"><div className="stat-num warn">{unpostedGifts}</div><div className="stat-label">{t('待晒图')}</div></div>
      </div>

      <div className="gift-card">
        <h2 className="section-title" style={{ marginBottom: 12 }}>{t('进度明细')}</h2>
        {rows.length === 0 ? (
          <div className="empty-state" style={{ padding: 'var(--gift-space-xl)' }}>
            <div className="empty-title" style={{ fontSize: 'var(--gift-font-md)' }}>{t('还没有参与者')}</div>
            <p className="empty-sub">{t('邀请朋友加入后，这里会显示每个人的进度')}</p>
            <Link to={`/events/${code}`} className="btn btn-secondary btn-sm" style={{ width: 'auto', marginTop: 12 }}>
              {t('去复制邀请链接')}
            </Link>
          </div>
        ) : (
        <div className="dash-table-wrap">
        <table className="dash-table">
          <thead>
            <tr>
              <th scope="col">{t('参与者')}</th>
              <th scope="col">{t('信息')}</th>
              <th scope="col">{t('发货')}</th>
              <th scope="col">{t('收货')}</th>
              <th scope="col">{t('晒图')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.participantId}>
                <td style={{ fontWeight: 500 }}>{r.displayName}</td>
                <td>
                  {r.contactComplete && r.preferenceComplete ? (
                    <Badge tone="success">{t('齐全')}</Badge>
                  ) : (
                    <Badge tone="warning">
                      {!r.contactComplete ? t('缺收件信息') : ''}{!r.contactComplete && !r.preferenceComplete ? t('、') : ''}{!r.preferenceComplete ? t('缺偏好') : ''}
                    </Badge>
                  )}
                </td>
                <td>
                  {r.shipmentStatus === 'pending' ? (
                    <Badge tone="warning">{t('未发货')}</Badge>
                  ) : r.shipmentStatus === 'shipped' ? (
                    <Badge tone="info">{t('已发货{check}', { check: r.hasTracking ? ' ✓' : '' })}</Badge>
                  ) : (
                    <Badge tone="success">{t('已送达')}</Badge>
                  )}
                </td>
                <td>{r.received ? <Badge tone="success">{t('已收货')}</Badge> : <Badge tone="warning">—</Badge>}</td>
                <td>{r.postedGift ? <Badge tone="gold">{t('已晒')}</Badge> : <Badge tone="warning">—</Badge>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        )}
      </div>
    </div>
  )
}
