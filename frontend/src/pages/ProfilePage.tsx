import { useEffect, useRef, useState } from 'react'
import { t, useLocale } from '../i18n'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useToast } from '../components/Toast'
import { useAuth } from '../auth/AuthContext'
import SafeImage from '../components/SafeImage'
import Modal from '../components/Modal'

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
  const locale = useLocale()
  const { toast } = useToast()
  const { logout, updateUser, user } = useAuth()
  const navigate = useNavigate()

  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [avatarUrl, setAvatarUrl] = useState('')
  const [avatarUploading, setAvatarUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

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

  // 数据导出 / 注销账号
  const [exporting, setExporting] = useState(false)
  const [showDeactivate, setShowDeactivate] = useState(false)
  const [deactivatePassword, setDeactivatePassword] = useState('')
  const [deactivating, setDeactivating] = useState(false)

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
        setAvatarUrl(p.avatarUrl || '')
      })
      .catch((e) => toast(e instanceof ApiError ? e.message : t('加载失败'), 'error'))
      .finally(() => setLoading(false))
    api
      .get<NotificationPrefs>('/notifications/preferences')
      .then(setPrefs)
      .catch((e) => toast(e instanceof ApiError ? e.message : t('偏好加载失败'), 'error'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const savePrefs = async () => {
    if (!prefs) return
    setSavingPrefs(true)
    try {
      const updated = await api.put<NotificationPrefs>('/notifications/preferences', prefs)
      setPrefs(updated)
      toast(t('通知偏好已保存 ✅'))
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t('保存失败'), 'error')
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
        avatarUrl: avatarUrl,
      })
      setProfile(updated)
      // 同步 Header（昵称/头像即时生效）
      updateUser({ displayName: updated.displayName, avatarUrl: updated.avatarUrl })
      toast(t('个人资料已保存 ✅'))
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t('保存失败'), 'error')
    } finally {
      setSaving(false)
    }
  }

  // 头像上传（先传后引用：/api/upload → 相对 URL → 存 profile）
  const uploadAvatar = async (file: File) => {
    if (!file.type.startsWith('image/')) {
      toast(t('请选择图片文件'), 'error')
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      toast(t('图片不能超过 5MB'), 'error')
      return
    }
    setAvatarUploading(true)
    try {
      const res = await api.upload<{ url: string }>('/upload', file)
      const url = res.url
      setAvatarUrl(url)
      // 立即保存到头像字段
      const updated = await api.put<Profile>('/profile', {
        displayName,
        phone,
        address,
        receiverName,
        giftPreference,
        avatarUrl: url,
      })
      setProfile(updated)
      updateUser({ displayName: updated.displayName, avatarUrl: updated.avatarUrl })
      toast(t('头像已更新 ✨'))
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t('头像上传失败'), 'error')
    } finally {
      setAvatarUploading(false)
    }
  }

  const exportData = async () => {
    setExporting(true)
    try {
      const data = await api.get<Record<string, unknown>>('/auth/export-data')
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `gift-exchange-data-${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      toast(t('数据已导出 ✅'))
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t('导出失败'), 'error')
    } finally {
      setExporting(false)
    }
  }

  const deactivateAccount = async () => {
    if (!deactivatePassword) return
    setDeactivating(true)
    try {
      await api.post('/auth/deactivate', { password: deactivatePassword })
      logout()
      toast(t('账号已注销'))
      navigate('/login', { replace: true })
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t('注销失败'), 'error')
    } finally {
      setDeactivating(false)
    }
  }

  const changePassword = async () => {
    if (newPassword !== confirmPassword) {
      toast(t('两次输入的新密码不一致'), 'error')
      return
    }
    // P2：新密码不能与用户名相同（与后端 change_password 校验一致）
    if (user?.username && newPassword.toLowerCase() === user.username.toLowerCase()) {
      toast(t('新密码不能与用户名相同'), 'error')
      return
    }
    setChangingPwd(true)
    try {
      await api.put('/profile/password', { oldPassword, newPassword })
      toast(t('密码已修改 ✅ 下次登录请使用新密码'))
      setOldPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t('修改失败'), 'error')
    } finally {
      setChangingPwd(false)
    }
  }

  const joinedDate = profile?.createdAt ? new Date(profile.createdAt).toLocaleDateString(locale === 'en' ? 'en-US' : 'zh-CN') : '—'

  if (loading) return <div className="page-loading">{t('加载中…')}</div>

  return (
    <div className="page-container" style={{ maxWidth: 640 }}>
      <div className="page-header">
        <h1 className="page-title">{t('个人资料')}</h1>
        <Link to="/events" className="btn btn-ghost btn-sm">{t('返回')}</Link>
      </div>

      {/* 基本信息（只读 + 头像可上传） */}
      <div className="gift-card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 }}>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={avatarUploading}
            title={t('点击更换头像')}
            aria-label={t('更换头像')}
            style={{
              width: 56, height: 56, borderRadius: '50%', background: 'var(--gift-brand-light)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24,
              flexShrink: 0, cursor: 'pointer', border: '2px dashed var(--gift-brand)', padding: 0,
              overflow: 'hidden',
            }}
          >
            {(avatarUrl || profile?.avatarUrl) ? (
              <SafeImage src={avatarUrl || profile?.avatarUrl} alt={t('头像')} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : avatarUploading ? (
              <span style={{ fontSize: 13, color: 'var(--gift-brand)' }}>{t('上传中…')}</span>
            ) : (
              <span style={{ fontSize: 22 }}>👤</span>
            )}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) uploadAvatar(f)
              e.target.value = ''
            }}
          />
          <div>
            <div style={{ fontWeight: 'bold', fontSize: 18 }}>{profile?.displayName}</div>
            <div style={{ color: 'var(--gift-text-secondary)', fontSize: 14 }}>@{profile?.username} · {profile?.email}</div>
            <div style={{ fontSize: 12, color: 'var(--gift-brand)', marginTop: 4 }}>{t('点击头像更换 ✏️')}</div>
          </div>
        </div>
        <div style={{ fontSize: 13, color: 'var(--gift-text-secondary)' }}>
          {t('注册于 {date}', { date: joinedDate })}
        </div>
      </div>

      {/* 常用信息（可编辑，加入活动时可预填） */}
      <div className="gift-card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginBottom: 16 }}>{t('常用信息')}</h3>
        <p style={{ fontSize: 13, color: 'var(--gift-text-secondary)', marginBottom: 16 }}>
          {t('保存后，加入新活动时会自动帮你填好收件信息 ✨')}
        </p>
        <div className="form-group">
          <label className="form-label" htmlFor="profile-name">{t('昵称')}</label>
          <input id="profile-name" className="form-input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={120} />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="profile-phone">{t('手机号')}</label>
          <input id="profile-phone" className="form-input" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={50} placeholder={t('手机号')} />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="profile-receiver">{t('常用收件人')}</label>
          <input id="profile-receiver" className="form-input" value={receiverName} onChange={(e) => setReceiverName(e.target.value)} maxLength={50} placeholder={t('收礼人姓名')} />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="profile-address">{t('常用地址')}</label>
          <textarea id="profile-address" className="form-textarea" value={address} onChange={(e) => setAddress(e.target.value)} maxLength={500} placeholder={t('收礼地址')} style={{ minHeight: 60 }} />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="profile-preference">{t('礼物偏好')}</label>
          <textarea id="profile-preference" className="form-textarea" value={giftPreference} onChange={(e) => setGiftPreference(e.target.value)} maxLength={500} placeholder={t('喜欢什么 / 不喜欢什么 / 尺码颜色等')} style={{ minHeight: 60 }} />
        </div>
        <button className="btn btn-primary" onClick={saveProfile} disabled={saving}>
          {saving ? t('保存中…') : t('保存资料')}
        </button>
      </div>

      {/* 通知偏好 */}
      <div className="gift-card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginBottom: 4 }}>{t('通知偏好')}</h3>
        <p style={{ fontSize: 13, color: 'var(--gift-text-secondary)', marginBottom: 8 }}>
          {t('关闭后不再接收对应类型的通知（已收通知保留，铃铛里仍可查看）')}
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
                  <div style={{ fontSize: 14 }}>{t(item.label)}</div>
                  <div style={{ fontSize: 12, color: 'var(--gift-text-secondary)' }}>{t(item.desc)}</div>
                </div>
                <input
                  type="checkbox"
                  checked={prefs[item.key]}
                  onChange={(e) => setPrefs(prev => prev ? { ...prev, [item.key]: e.target.checked } : prev)}
                  style={{ width: 40, height: 22, accentColor: 'var(--gift-brand)', cursor: 'pointer', flexShrink: 0 }}
                  aria-label={t(item.label)}
                />
              </label>
            ))}
            <button className="btn btn-secondary" onClick={savePrefs} disabled={savingPrefs} style={{ marginTop: 16 }}>
              {savingPrefs ? t('保存中…') : t('保存偏好')}
            </button>
          </div>
        ) : (
          <div className="page-loading">{t('加载中…')}</div>
        )}
      </div>

      {/* 修改密码 */}
      <div className="gift-card">
        <h3 style={{ marginBottom: 16 }}>{t('修改密码')}</h3>
        <div className="form-group">
          <label className="form-label" htmlFor="profile-old-pwd">{t('当前密码')}</label>
          <input id="profile-old-pwd" className="form-input" type="password" value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} placeholder={t('输入当前密码')} autoComplete="current-password" />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="profile-new-pwd">{t('新密码')}</label>
          <input id="profile-new-pwd" className="form-input" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder={t('至少 6 位，含字母和数字')} autoComplete="new-password" />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="profile-confirm-pwd">{t('确认新密码')}</label>
          <input id="profile-confirm-pwd" className="form-input" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder={t('再次输入新密码')} autoComplete="new-password" />
        </div>
        <button className="btn btn-secondary" onClick={changePassword} disabled={changingPwd}>
          {changingPwd ? t('修改中…') : t('修改密码')}
        </button>
      </div>

      {/* 数据导出 / 注销账号 */}
      <div className="gift-card" style={{ marginTop: 16 }}>
        <h3 style={{ marginBottom: 12 }}>{t('数据与账户')}</h3>
        <button className="btn btn-secondary" onClick={exportData} disabled={exporting} style={{ width: '100%' }}>
          {exporting ? t('导出中…') : t('数据导出')}
        </button>
        <p style={{ fontSize: 13, color: 'var(--gift-text-secondary)', margin: '8px 0 16px' }}>
          {t('下载 JSON 文件：个人资料、我创建/参与的活动、晒图记录（各截取最近 100 条）')}
        </p>
        <button
          className="btn btn-ghost"
          onClick={() => setShowDeactivate(true)}
          style={{ width: '100%', color: 'var(--gift-error-text)', borderColor: 'var(--gift-error-text)' }}
        >
          {t('注销账号')}
        </button>
      </div>

      {showDeactivate && (
        <Modal title={t('注销账号？')} onClose={() => setShowDeactivate(false)}>
          <p style={{ marginTop: 8, fontSize: 13, color: 'var(--gift-text-secondary)' }}>
            {t('注销后账号将无法登录，收件地址等个人资料会被清除；活动与礼物墙数据会保留但不再关联你的身份。此操作不可撤销。')}
          </p>
          <div className="form-group" style={{ marginTop: 16 }}>
            <label className="form-label" htmlFor="deactivate-pwd">{t('输入密码确认')}</label>
            <input
              id="deactivate-pwd"
              className="form-input"
              type="password"
              value={deactivatePassword}
              onChange={(e) => setDeactivatePassword(e.target.value)}
              placeholder={t('当前登录密码')}
              autoComplete="current-password"
            />
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 20 }}>
            <button className="btn btn-ghost" style={{ flex: 1 }} onClick={() => setShowDeactivate(false)}>
              {t('取消')}
            </button>
            <button
              className="btn btn-primary"
              style={{ flex: 1, background: 'var(--gift-error)' }}
              onClick={deactivateAccount}
              disabled={deactivating || !deactivatePassword}
            >
              {deactivating ? t('注销中…') : t('确认注销')}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}
