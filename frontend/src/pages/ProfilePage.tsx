import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useToast } from '../components/Toast'

interface Profile {
  id: number
  username: string
  email: string
  displayName: string
  avatarUrl?: string
  phone: string
  address: string
  receiverName: string
  giftPreference: string
  createdAt: string
}

/** 通知偏好（与后端 DEFAULT_PREFS 键一致：deadline/draw/giftReceived/remind） */
interface NotificationPrefs {
  deadline: boolean
  draw: boolean
  giftReceived: boolean
  remind: boolean
}

const PREF_ITEMS: { key: keyof NotificationPrefs; label: string; desc: string }[] = [
  { key: 'deadline', label: '截止提醒', desc: '报名截止前 48 小时 / 24 小时提醒组织者及时抽签' },
  { key: 'draw', label: '抽签结果', desc: '抽签完成或重置后，通知所有参与者查看新的送礼任务' },
  { key: 'giftReceived', label: '晒图提醒', desc: '礼物被晒图评价、礼物墙解锁时通知' },
  { key: 'remind', label: '催办动态', desc: '有人加入活动、礼物发货时通知' },
]

export default function ProfilePage() {
  const { toast } = useToast()

  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // 常用信息表单
  const [displayName, setDisplayName] = useState('')
  const [phone, setPhone] = useState('')
  const [address, setAddress] = useState('')
  const [receiverName, setReceiverName] = useState('')
  const [giftPreference, setGiftPreference] = useState('')

  // 改密码表单
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [changingPwd, setChangingPwd] = useState(false)

  // 通知偏好
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null)
  const [savingPrefs, setSavingPrefs] = useState(false)

  useEffect(() => {
    api
      .get<Profile>('/profile')
      .then((p) => {
        setProfile(p)
        setDisplayName(p.displayName)
        setPhone(p.phone)
        setAddress(p.address)
        setReceiverName(p.receiverName)
        setGiftPreference(p.giftPreference)
      })
      .catch((e) => toast(e instanceof ApiError ? e.message : '加载失败', 'error'))
      .finally(() => setLoading(false))
    api
      .get<NotificationPrefs>('/notifications/preferences')
      .then(setPrefs)
      .catch((e) => toast(e instanceof ApiError ? e.message : '偏好加载失败', 'error'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const savePrefs = async () => {
    if (!prefs) return
    setSavingPrefs(true)
    try {
      const updated = await api.put<NotificationPrefs>('/notifications/preferences', prefs)
      setPrefs(updated)
      toast('通知偏好已保存 ✅')
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '保存失败', 'error')
    } finally {
      setSavingPrefs(false)
    }
  }

  const saveProfile = async () => {
    setSaving(true)
    try {
      const updated = await api.put<Profile>('/profile', {
        displayName,
        phone,
        address,
        receiverName,
        giftPreference,
      })
      setProfile(updated)
      toast('个人资料已保存 ✅')
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '保存失败', 'error')
    } finally {
      setSaving(false)
    }
  }

  const changePassword = async () => {
    if (newPassword !== confirmPassword) {
      toast('两次输入的新密码不一致', 'error')
      return
    }
    setChangingPwd(true)
    try {
      await api.put('/profile/password', { oldPassword, newPassword })
      toast('密码已修改 ✅ 下次登录请使用新密码')
      setOldPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '修改失败', 'error')
    } finally {
      setChangingPwd(false)
    }
  }

  if (loading) return <div className="page-loading">加载中…</div>

  return (
    <div className="page-container" style={{ maxWidth: 640 }}>
      <div className="page-header">
        <h1 className="page-title">个人资料</h1>
        <Link to="/events" className="btn btn-ghost btn-sm">返回</Link>
      </div>

      {/* 基本信息（只读） */}
      <div className="gift-card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 }}>
          <div style={{
            width: 56, height: 56, borderRadius: '50%', background: 'var(--gift-brand-light)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, flexShrink: 0,
          }}>
            {profile?.avatarUrl ? (
              <img src={profile.avatarUrl} alt="头像" style={{ width: 56, height: 56, borderRadius: '50%', objectFit: 'cover' }} />
            ) : '👤'}
          </div>
          <div>
            <div style={{ fontWeight: 'bold', fontSize: 18 }}>{profile?.displayName}</div>
            <div style={{ color: 'var(--gift-text-secondary)', fontSize: 14 }}>@{profile?.username} · {profile?.email}</div>
          </div>
        </div>
        <div style={{ fontSize: 13, color: 'var(--gift-text-secondary)' }}>
          注册于 {profile?.createdAt ? new Date(profile.createdAt).toLocaleDateString('zh-CN') : '—'}
        </div>
      </div>

      {/* 常用信息（可编辑，加入活动时可预填） */}
      <div className="gift-card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginBottom: 16 }}>常用信息</h3>
        <p style={{ fontSize: 13, color: 'var(--gift-text-secondary)', marginBottom: 16 }}>
          保存后，加入新活动时会自动帮你填好收件信息 ✨
        </p>
        <div className="form-group">
          <label className="form-label">昵称</label>
          <input className="form-input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={120} />
        </div>
        <div className="form-group">
          <label className="form-label">手机号</label>
          <input className="form-input" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={50} placeholder="收礼人电话" />
        </div>
        <div className="form-group">
          <label className="form-label">常用收件人</label>
          <input className="form-input" value={receiverName} onChange={(e) => setReceiverName(e.target.value)} maxLength={50} placeholder="收礼人姓名" />
        </div>
        <div className="form-group">
          <label className="form-label">常用地址</label>
          <textarea className="form-textarea" value={address} onChange={(e) => setAddress(e.target.value)} maxLength={500} placeholder="收礼地址" style={{ minHeight: 60 }} />
        </div>
        <div className="form-group">
          <label className="form-label">礼物偏好</label>
          <textarea className="form-textarea" value={giftPreference} onChange={(e) => setGiftPreference(e.target.value)} maxLength={500} placeholder="喜欢什么 / 不喜欢什么 / 尺码颜色等" style={{ minHeight: 60 }} />
        </div>
        <button className="btn btn-primary" onClick={saveProfile} disabled={saving}>
          {saving ? '保存中…' : '保存资料'}
        </button>
      </div>

      {/* 通知偏好 */}
      <div className="gift-card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginBottom: 4 }}>通知偏好</h3>
        <p style={{ fontSize: 13, color: 'var(--gift-text-secondary)', marginBottom: 8 }}>
          关闭后不再接收对应类型的通知（已收通知保留，铃铛里仍可查看）
        </p>
        {prefs ? (
          <div>
            {PREF_ITEMS.map(item => (
              <label
                key={item.key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 12,
                  padding: '12px 0',
                  borderBottom: '1px solid var(--gift-border)',
                  cursor: 'pointer',
                }}
              >
                <div>
                  <div style={{ fontSize: 14 }}>{item.label}</div>
                  <div style={{ fontSize: 12, color: 'var(--gift-text-secondary)' }}>{item.desc}</div>
                </div>
                <input
                  type="checkbox"
                  checked={prefs[item.key]}
                  onChange={(e) => setPrefs(prev => prev ? { ...prev, [item.key]: e.target.checked } : prev)}
                  style={{ width: 40, height: 22, accentColor: 'var(--gift-brand)', cursor: 'pointer', flexShrink: 0 }}
                  aria-label={item.label}
                />
              </label>
            ))}
            <button className="btn btn-secondary" onClick={savePrefs} disabled={savingPrefs} style={{ marginTop: 16 }}>
              {savingPrefs ? '保存中…' : '保存偏好'}
            </button>
          </div>
        ) : (
          <div className="page-loading">加载中…</div>
        )}
      </div>

      {/* 修改密码 */}
      <div className="gift-card">
        <h3 style={{ marginBottom: 16 }}>修改密码</h3>
        <div className="form-group">
          <label className="form-label">当前密码</label>
          <input className="form-input" type="password" value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} placeholder="输入当前密码" />
        </div>
        <div className="form-group">
          <label className="form-label">新密码</label>
          <input className="form-input" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="至少 6 位，含字母和数字" />
        </div>
        <div className="form-group">
          <label className="form-label">确认新密码</label>
          <input className="form-input" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="再次输入新密码" />
        </div>
        <button className="btn btn-secondary" onClick={changePassword} disabled={changingPwd}>
          {changingPwd ? '修改中…' : '修改密码'}
        </button>
      </div>
    </div>
  )
}
