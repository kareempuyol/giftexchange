import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api, ApiError, EventInfo } from '../api/client'
import { useToast } from '../components/Toast'
import ImageUpload from '../components/ImageUpload'

export default function CreateEventPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [title, setTitle] = useState('')
  const [note, setNote] = useState('')
  const [budget, setBudget] = useState('100')
  const [drawDate, setDrawDate] = useState('')
  const [maxParticipants, setMaxParticipants] = useState('')
  const [isPublic, setIsPublic] = useState(true)
  const [matchVisibility, setMatchVisibility] = useState<'private' | 'public'>('private')
  const [coverImage, setCoverImage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) {
      setError('请填写活动名称')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const ev = await api.post<EventInfo>('/events', {
        title: title.trim(),
        note: note.trim(),
        budget: Number(budget) || 0,
        drawDate: drawDate ? new Date(drawDate).toISOString() : '',
        maxParticipants: maxParticipants ? Number(maxParticipants) : null,
        isPublic,
        matchVisibility,
        ...(coverImage ? { coverImage } : {}),
      })
      toast('活动创建成功！')
      navigate(`/events/${ev.code}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '创建失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page-container" style={{ maxWidth: 560 }}>
      <div className="page-header">
        <h1 className="page-title">创建活动</h1>
        <Link to="/events" className="btn btn-ghost btn-sm">返回</Link>
      </div>

      <form className="gift-card" onSubmit={onSubmit}>
        <div className="form-group">
          <label className="form-label">活动名称 *</label>
          <input
            className="form-input"
            placeholder="例如：圣诞礼物互赠"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={100}
          />
        </div>

        <div className="form-group">
          <label className="form-label">活动说明</label>
          <textarea
            className="form-textarea"
            placeholder="写点规则或想说的话（选填）"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={500}
          />
        </div>

        <div className="form-group">
          <label className="form-label">预算上限（元）</label>
          <input
            className="form-input"
            type="number"
            min={0}
            placeholder="100"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
          />
          <div className="form-hint">给参与者一个送礼金额参考</div>
        </div>

        <div className="form-group">
          <label className="form-label">报名截止日期</label>
          <input
            className="form-input"
            type="datetime-local"
            value={drawDate}
            onChange={(e) => setDrawDate(e.target.value)}
          />
          <div className="form-hint">选填，截止后由你手动抽签</div>
        </div>

        <div className="form-group">
          <label className="form-label">人数上限</label>
          <input
            className="form-input"
            type="number"
            min={2}
            max={999}
            placeholder="不限"
            value={maxParticipants}
            onChange={(e) => setMaxParticipants(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">谁可以看到这个活动</label>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              className={`btn btn-secondary btn-sm${isPublic ? ' tab-active' : ''}`}
              style={{ width: 'auto' }}
              onClick={() => setIsPublic(true)}
            >
              公开（所有人可见）
            </button>
            <button
              type="button"
              className={`btn btn-secondary btn-sm${!isPublic ? ' tab-active' : ''}`}
              style={{ width: 'auto' }}
              onClick={() => setIsPublic(false)}
            >
              私密（仅凭链接）
            </button>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">抽签结果可见性</label>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              className={`btn btn-secondary btn-sm${matchVisibility === 'private' ? ' tab-active' : ''}`}
              style={{ width: 'auto' }}
              onClick={() => setMatchVisibility('private')}
            >
              仅个人可见（推荐）
            </button>
            <button
              type="button"
              className={`btn btn-secondary btn-sm${matchVisibility === 'public' ? ' tab-active' : ''}`}
              style={{ width: 'auto' }}
              onClick={() => setMatchVisibility('public')}
            >
              所有人可见
            </button>
          </div>
          <div className="form-hint">仅个人可见时，每个人只能看到自己送谁</div>
        </div>

        <div className="form-group">
          <label className="form-label">封面图片</label>
          <ImageUpload
            value={coverImage}
            onChange={setCoverImage}
            hint="选填，支持 png / jpg / jpeg / gif / webp，最大 5MB"
          />
        </div>

        {error && <div className="form-error" style={{ marginBottom: 12 }}>{error}</div>}

        <button className="btn btn-primary" type="submit" disabled={submitting}>
          {submitting ? '创建中…' : '创建活动'}
        </button>
      </form>
    </div>
  )
}
