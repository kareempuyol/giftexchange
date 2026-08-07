import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, EventInfo } from '../api/client'
import Badge from '../components/Badge'

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

export default function DashboardPage() {
  const { code = '' } = useParams()
  const [event, setEvent] = useState<EventInfo | null>(null)
  const [rows, setRows] = useState<DashboardParticipant[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [ev, data] = await Promise.all([
          api.get<EventInfo>(`/events/${code}`),
          api.get<{ participants: DashboardParticipant[] }>(`/events/${code}/dashboard`),
        ])
        setEvent(ev)
        setRows(data.participants)
      } catch {
        // 非组织者无法查看
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [code])

  if (loading) return <div className="page-loading">加载中…</div>
  if (!event) return <div className="page-container">无权限或活动不存在</div>

  const shipped = rows.filter((r) => r.shipmentStatus !== 'pending').length
  const received = rows.filter((r) => r.received).length
  const posted = rows.filter((r) => r.postedGift).length

  return (
    <div className="page-container" style={{ maxWidth: 860 }}>
      <div className="page-header">
        <h1 className="page-title">活动管理台</h1>
        <Link to={`/events/${code}`} className="btn btn-ghost btn-sm">返回活动</Link>
      </div>

      <div className="dash-stats">
        <div className="stat-card"><div className="stat-num">{rows.length}</div><div className="stat-label">参与人数</div></div>
        <div className="stat-card"><div className="stat-num">{shipped}</div><div className="stat-label">已发货</div></div>
        <div className="stat-card"><div className="stat-num">{received}</div><div className="stat-label">已收货</div></div>
        <div className="stat-card"><div className="stat-num">{posted}</div><div className="stat-label">已晒图</div></div>
      </div>

      <div className="gift-card">
        <h2 className="section-title" style={{ marginBottom: 12 }}>进度明细</h2>
        <table className="dash-table">
          <thead>
            <tr>
              <th>参与者</th>
              <th>信息</th>
              <th>发货</th>
              <th>收货</th>
              <th>晒图</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.participantId}>
                <td style={{ fontWeight: 500 }}>{r.displayName}</td>
                <td>
                  {r.contactComplete && r.preferenceComplete ? (
                    <Badge tone="success">齐全</Badge>
                  ) : (
                    <Badge tone="warning">
                      {!r.contactComplete ? '缺收件信息' : ''}{!r.contactComplete && !r.preferenceComplete ? '、' : ''}{!r.preferenceComplete ? '缺偏好' : ''}
                    </Badge>
                  )}
                </td>
                <td>
                  {r.shipmentStatus === 'pending' ? (
                    <Badge tone="warning">未发货</Badge>
                  ) : r.shipmentStatus === 'shipped' ? (
                    <Badge tone="info">已发货{r.hasTracking ? ' ✓' : ''}</Badge>
                  ) : (
                    <Badge tone="success">已送达</Badge>
                  )}
                </td>
                <td>{r.received ? <Badge tone="success">已收货</Badge> : <Badge tone="warning">—</Badge>}</td>
                <td>{r.postedGift ? <Badge tone="gold">已晒</Badge> : <Badge tone="warning">—</Badge>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
