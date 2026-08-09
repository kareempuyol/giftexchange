import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api, ApiError, EventInfo } from '../api/client'
import { useToast } from '../components/Toast'
import ImageUpload from '../components/ImageUpload'
import { t, useLocale } from '../i18n'

export default function CreateEventPage() {
  const navigate = useNavigate()
  useLocale() // 订阅语言切换：setLocale 后重渲染
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
  // 「再开一局」带入的成员名单（含 userId，供互避规则解析）
  const [draftMembers, setDraftMembers] = useState<{ username: string; userId: number; displayName?: string }[]>([])
  // 互避规则输入（每行一对用户名）
  const [rulesText, setRulesText] = useState('')

  // 读取「再开一局」草稿（GiftWallPage 写入）或 URL 预填
  useEffect(() => {
    try {
      const draft = localStorage.getItem('gift_draft')
      if (draft) {
        const d = JSON.parse(draft)
        if (d.title) setTitle(d.title)
        if (d.note) setNote(d.note)
        if (d.budget) setBudget(String(d.budget))
        // 「复制活动」草稿扩展字段：公开性/可见性/人数上限/互避规则文本
        if (typeof d.isPublic === 'boolean') setIsPublic(d.isPublic)
        if (typeof d.matchVisibility === 'string') setMatchVisibility(d.matchVisibility)
        if (d.maxParticipants != null && d.maxParticipants !== '') setMaxParticipants(String(d.maxParticipants))
        if (typeof d.rulesText === 'string' && d.rulesText) setRulesText(d.rulesText)
        if (Array.isArray(d.members)) {
          // 兼容纯字符串名单与 {username, userId} 对象名单
          const members: { username: string; userId: number; displayName?: string }[] = []
          for (const m of d.members) {
            if (typeof m === 'string') {
              if (m) members.push({ username: m, userId: 0 })
            } else if (m && typeof m === 'object' && 'username' in m && typeof m.username === 'string' && m.username) {
              members.push({
                username: m.username,
                userId: 'userId' in m && typeof m.userId === 'number' ? m.userId : 0,
                displayName: 'displayName' in m && typeof m.displayName === 'string' ? m.displayName : undefined,
              })
            }
          }
          setDraftMembers(members)
        }
        localStorage.removeItem('gift_draft')
      }
    } catch {
      /* 忽略损坏草稿 */
    }
  }, [])

  // 解析互避规则文本：每行「用户名1, 用户名2」，返回配对列表或格式错误
  const parseRules = (): { pairs: string[][]; error: string } => {
    const pairs: string[][] = []
    const lines = rulesText.split('\n')
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim()
      if (!line) continue
      const names = line
        .split(/[,，、]/)
        .map((s) => s.trim())
        .filter(Boolean)
      if (names.length !== 2) {
        return { pairs: [], error: t('第 {n} 行格式应为「用户名1, 用户名2」', { n: i + 1 }) }
      }
      pairs.push(names)
    }
    return { pairs, error: '' }
  }

  // 季节模板
  const templates = [
    { icon: '🎄', name: t('圣诞交换'), title: t('圣诞礼物交换'), note: t('今年圣诞，我们把心意藏在礼物里 🎁'), budget: '200', days: t('12月20日') },
    { icon: '🎂', name: t('生日惊喜'), title: t('生日惊喜派对'), note: t('给寿星的礼物盲盒，大家一起宠 TA 🎂'), budget: '150', days: t('生日前一周') },
    { icon: '🎉', name: t('新年聚会'), title: t('新年礼物互赠'), note: t('新年新气象，互相送份小确幸 🧧'), budget: '100', days: t('元旦前三天') },
  ]

  const applyTemplate = (tpl: (typeof templates)[number]) => {
    setTitle(tpl.title)
    setNote(tpl.note)
    setBudget(tpl.budget)
    setDrawDate('')
    toast(t('已应用「{name}」模板，可再调整', { name: tpl.name }))
  }

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) {
      setError(t('请填写活动名称'))
      return
    }

    // 预算：负数或非数字直接拦截（type=number 的 min 不阻止手输）
    const budgetNum = budget === '' ? 0 : Number(budget)
    if (budget !== '' && (!Number.isFinite(budgetNum) || budgetNum < 0)) {
      setError(t('预算不能为负数或无效数字'))
      return
    }

    // 报名截止：不能早于当前时间
    if (drawDate) {
      const d = new Date(drawDate)
      if (Number.isNaN(d.getTime())) {
        setError(t('报名截止日期格式无效'))
        return
      }
      if (d.getTime() <= Date.now()) {
        setError(t('报名截止日期不能早于现在'))
        return
      }
    }

    // 人数上限：填写时至少 2 人
    if (maxParticipants !== '') {
      const maxNum = Number(maxParticipants)
      if (!Number.isFinite(maxNum) || maxNum < 2) {
        setError(t('人数上限至少为 2 人'))
        return
      }
      if (maxNum > 999) {
        setError(t('人数上限不能超过 999'))
        return
      }
    }

    // 互避规则：解析 → 数量预警 → 用户名解析为 userId（成员名单来自「再开一局」草稿）
    const parsed = parseRules()
    if (parsed.error) {
      setError(parsed.error)
      return
    }
    const rulePairs = parsed.pairs
    let excludedPairs: number[][] = []
    if (rulePairs.length > 0) {
      // 预期成员数：优先带入名单，其次人数上限；已知时提前预警（后端抽签 400 兜底）
      const expected =
        draftMembers.length > 0 ? draftMembers.length : maxParticipants ? Number(maxParticipants) : 0
      if (expected > 0 && rulePairs.length >= Math.ceil(expected / 2)) {
        setError(t('互避规则过多可能导致无法抽签（计划 {expected} 人、已配置 {count} 组），请减少规则数量', { expected, count: rulePairs.length }))
        return
      }
      if (draftMembers.length === 0) {
        setError(t('互避规则需与成员用户名对应。请使用「再开一局」带入成员名单后配置，或创建活动邀请成员后再配置'))
        return
      }
      // 用户名 → userId（username 优先，displayName 兜底）
      const uidByName = new Map<string, number>()
      for (const m of draftMembers) {
        if (m.userId > 0 && !uidByName.has(m.username)) uidByName.set(m.username, m.userId)
        if (m.displayName && m.userId > 0 && !uidByName.has(m.displayName)) uidByName.set(m.displayName, m.userId)
      }
      const unknown = new Set<string>()
      for (const [a, b] of rulePairs) {
        const ua = uidByName.get(a)
        const ub = uidByName.get(b)
        if (!ua || !ub) {
          if (!ua) unknown.add(a)
          if (!ub) unknown.add(b)
          continue
        }
        if (ua !== ub) excludedPairs.push([ua, ub])
      }
      if (unknown.size > 0) {
        const unknownNames = [...unknown].join(t('、'))
        setError(t('无法识别的成员用户名：{names}，请与名单保持一致', { names: unknownNames }))
        return
      }
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
        ...(excludedPairs.length > 0 ? { excludedPairs } : {}),
      })
      toast(t('活动创建成功！'))
      navigate(`/events/${ev.code}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('创建失败，请稍后重试'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page-container" style={{ maxWidth: 560 }}>
      <div className="page-header">
        <h1 className="page-title">{t('创建活动')}</h1>
        <Link to="/events" className="btn btn-ghost btn-sm">{t('返回')}</Link>
      </div>

      <form className="gift-card" onSubmit={onSubmit}>
        {/* 季节模板快捷栏 */}
        <div style={{ marginBottom: 20 }}>
          <div className="form-label">{t('从模板创建')}</div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {templates.map((tpl) => (
              <button
                key={tpl.name}
                type="button"
                className="btn btn-secondary btn-sm"
                style={{ width: 'auto', flex: '1 1 auto', minWidth: 100 }}
                onClick={() => applyTemplate(tpl)}
              >
                {tpl.icon} {t(tpl.name)}
              </button>
            ))}
          </div>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="ev-title">{t('活动名称 *')}</label>
          <input
            id="ev-title"
            className="form-input"
            placeholder={t('例如：圣诞礼物互赠')}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={100}
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="ev-note">{t('活动说明')}</label>
          <textarea
            id="ev-note"
            className="form-textarea"
            placeholder={t('写点规则或想说的话（选填）')}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={500}
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="ev-budget">{t('预算上限（元）')}</label>
          <input
            id="ev-budget"
            className="form-input"
            type="number"
            min={0}
            placeholder="100"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
          />
          <div className="form-hint">{t('给参与者一个送礼金额参考')}</div>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="ev-draw-date">{t('报名截止日期')}</label>
          <input
            id="ev-draw-date"
            className="form-input"
            type="datetime-local"
            value={drawDate}
            onChange={(e) => setDrawDate(e.target.value)}
          />
          <div className="form-hint">{t('选填，截止后由你手动抽签')}</div>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="ev-max">{t('人数上限')}</label>
          <input
            id="ev-max"
            className="form-input"
            type="number"
            min={2}
            max={999}
            placeholder={t('不限')}
            value={maxParticipants}
            onChange={(e) => setMaxParticipants(e.target.value)}
          />
        </div>

        {draftMembers.length > 0 && (
          <div className="form-group">
            <label className="form-label" htmlFor="ev-members">{t('成员名单（每行一个用户名）')}</label>
            <textarea
              id="ev-members"
              className="form-textarea"
              readOnly
              value={draftMembers.map((m) => m.username).join('\n')}
              style={{ background: 'var(--gift-bg-muted)' }}
            />
            <div className="form-hint">{t('来自上期活动，不会自动加入新活动，方便你复制邀请名单')}</div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ width: 'auto', marginTop: 8 }}
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(draftMembers.map((m) => m.username).join('\n'))
                  toast(t('成员名单已复制'))
                } catch {
                  toast(t('复制失败，请手动选择复制'), 'error')
                }
              }}
            >
              {t('📋 复制名单')}
            </button>
          </div>
        )}

        <div className="form-group">
          <label className="form-label">{t('谁可以看到这个活动')}</label>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              className={`btn btn-secondary btn-sm${isPublic ? ' tab-active' : ''}`}
              style={{ width: 'auto' }}
              onClick={() => setIsPublic(true)}
            >
              {t('公开（所有人可见）')}
            </button>
            <button
              type="button"
              className={`btn btn-secondary btn-sm${!isPublic ? ' tab-active' : ''}`}
              style={{ width: 'auto' }}
              onClick={() => setIsPublic(false)}
            >
              {t('私密（仅凭链接）')}
            </button>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">{t('抽签结果可见性')}</label>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              className={`btn btn-secondary btn-sm${matchVisibility === 'private' ? ' tab-active' : ''}`}
              style={{ width: 'auto' }}
              onClick={() => setMatchVisibility('private')}
            >
              {t('仅个人可见（推荐）')}
            </button>
            <button
              type="button"
              className={`btn btn-secondary btn-sm${matchVisibility === 'public' ? ' tab-active' : ''}`}
              style={{ width: 'auto' }}
              onClick={() => setMatchVisibility('public')}
            >
              {t('所有人可见')}
            </button>
          </div>
          <div className="form-hint">{t('仅个人可见时，每个人只能看到自己送谁')}</div>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="ev-rules">{t('互避规则（选填）')}</label>
          <div style={{ fontSize: 'var(--gift-font-xs)', color: 'var(--gift-text-secondary)', marginBottom: 8 }}>
            {t('互避 = 这两人不会互送礼物（如情侣/夫妻）')}
          </div>
          <textarea
            id="ev-rules"
            className="form-textarea"
            placeholder={t('每行一对，用逗号分隔用户名\n例如：小明, 小红')}
            value={rulesText}
            onChange={(e) => setRulesText(e.target.value)}
            maxLength={500}
          />
          <div className="form-hint">{t('规则按用户名填写；从「再开一局」带入成员名单时提交即生效，抽签时自动避开这些配对')}</div>
        </div>

        <div className="form-group">
          <label className="form-label">{t('封面图片')}</label>
          <ImageUpload
            value={coverImage}
            onChange={setCoverImage}
            hint={t('选填，支持 png / jpg / jpeg / gif / webp，最大 5MB')}
          />
        </div>

        {error && <div className="form-error" role="alert" style={{ marginBottom: 12 }}>{error}</div>}

        <button className="btn btn-primary" type="submit" disabled={submitting}>
          {submitting ? t('创建中…') : t('创建活动')}
        </button>
      </form>
    </div>
  )
}
