/**
 * API 客户端 —— 封装 fetch，统一处理 token 与错误
 * 未来小程序迁移：此模块替换为 wx.request 适配层即可
 */
const TOKEN_KEY = 'gift_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export interface ApiResult<T = any> {
  code: number
  data: T
  message: string
}

export class ApiError extends Error {
  code: number
  status: number
  constructor(message: string, code: number, status: number) {
    super(message)
    this.code = code
    this.status = status
  }
}

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const resp = await fetch(`/api${path}`, { ...options, headers })
  let body: ApiResult<T>
  try {
    body = await resp.json()
  } catch {
    throw new ApiError(`服务响应异常 (${resp.status})`, -1, resp.status)
  }

  if (body.code !== 0) {
    // 401 时清理 token（会话过期）
    if (resp.status === 401) setToken(null)
    throw new ApiError(body.message || '请求失败', body.code, resp.status)
  }
  return body.data
}

export const api = {
  get: <T = any>(path: string) => request<T>(path),
  post: <T = any>(path: string, data?: any) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(data ?? {}) }),
  put: <T = any>(path: string, data?: any) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(data ?? {}) }),
  patch: <T = any>(path: string, data?: any) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(data ?? {}) }),
  delete: <T = any>(path: string) => request<T>(path, { method: 'DELETE' }),
  /** 图片上传：multipart/form-data，字段名 file。返回 { url }（相对 URL） */
  upload: async <T = UploadResult>(path: string, file: File): Promise<T> => {
    const form = new FormData()
    form.append('file', file)
    const headers: Record<string, string> = {}
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
    // 注意：不设置 Content-Type，让浏览器自动带 multipart boundary
    const resp = await fetch(`/api${path}`, { method: 'POST', body: form, headers })
    let body: ApiResult<T>
    try {
      body = await resp.json()
    } catch {
      throw new ApiError(`服务响应异常 (${resp.status})`, -1, resp.status)
    }
    if (body.code !== 0) {
      if (resp.status === 401) setToken(null)
      throw new ApiError(body.message || '上传失败', body.code, resp.status)
    }
    return body.data
  },
}

// ===== 类型定义（与后端 API 对齐） =====
/** POST /api/upload 返回：图片相对 URL（先传后引用） */
export interface UploadResult {
  url: string
}

export interface User {
  id: number
  username: string
  email: string
  displayName: string
  avatarUrl?: string
  isAdmin: boolean
  phone?: string
  address?: string
  receiverName?: string
  giftPreference?: string
  createdAt: string
}

export interface EventInfo {
  code: string
  shortCode: string
  title: string
  budget: number
  note: string
  drawDate: string
  status: 'open' | 'drawn'
  matchVisibility: 'private' | 'public'
  ownerId: number
  ownerName: string
  participantCount: number
  coverImage?: string
  isPublic: boolean
  maxParticipants?: number | null
  excludedPairs: number[][]
  createdAt: string
  updatedAt: string
}

export interface EventPreview {
  code: string
  shortCode: string
  title: string
  note?: string
  budget?: number
  signUpDeadline?: string
  status: string
  coverImage?: string
  participantCount: number
  isPublic: boolean
}

export interface Participant {
  id: number
  userId: number
  username: string
  displayName: string
  avatarUrl?: string
  nickname: string
  contactComplete: boolean
  preferenceComplete: boolean
  joinedAt: string
}

export type ShipmentState = 'purchase' | 'shipped' | 'received' | 'posted'

export interface MyMatch {
  matchId: number
  receiverId: number
  receiverName: string
  receiverDisplayName: string
  note: string
  shipmentState: ShipmentState
  shipment: Shipment
  giftPost: GiftPost
  contact: {
    receiverName: string
    phone: string
    address: string
  }
  preference: {
    likes: string
    dislikes: string
    notes: string
    size: string
    color: string
    wishLinks: string[]
  }
}

export interface Shipment {
  status: 'pending' | 'shipped' | 'delivered'
  carrier: string
  trackingNumber: string
  shippedAt: string
  trackingUpdatedAt: string
  trackingSummary: string
}

export type GiftPrivacy = 'photo' | 'text' | 'blur'

export interface GiftPost {
  receivedAt: string
  rating: number | null
  review: string
  photoUrl: string
  /** 晒图隐私：photo=公开照片 / text=仅文字 / blur=模糊照片（后端旧数据缺省视为 photo） */
  privacy?: GiftPrivacy
}

export interface GiftWallProgress {
  posted: number
  total: number
  unlocked: boolean
  remaining: number
}

export interface GiftWallItem {
  matchId: number
  giverName: string
  receiverName: string
  giftPost: GiftPost
  /** item 级隐私（后端同步返回，兼容旧缓存时以 giftPost.privacy 优先） */
  privacy?: GiftPrivacy
  likeCount: number
  likedByMe: boolean
}

export interface GiftWall {
  unlocked: boolean
  posted: number
  total: number
  title: string
  note?: string
  budget?: number
  progress: GiftWallProgress
  items: GiftWallItem[]
}

/** GET /api/events/<code>/received-gift 返回：我作为收礼人收到的礼物 */
export interface ReceivedGift {
  matchId: number
  giverId: number
  giverName: string
  giverDisplayName: string
  note: string
  shipment: Shipment
  giftPost: GiftPost
}

export interface NotificationItem {
  id: number
  eventCode: string
  matchId: number | null
  type: string
  title: string
  message: string
  read: boolean
  createdAt: string
}
