/**
 * API 客户端 —— 封装 fetch，统一处理 token 与错误
 * 未来小程序迁移：此模块替换为 wx.request 适配层即可
 */
import { t } from '../i18n'

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

// 请求硬超时 15s：服务端挂起/网络黑洞时前端不无限等待（AbortController 实现）
const REQUEST_TIMEOUT_MS = 15000

/** fetch + 超时取消：内部 15s 定时器 + 透传外部 signal（外部取消一并 abort）。 */
async function fetchWithTimeout(path: string, options: RequestInit = {}): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  const { signal } = options
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', () => controller.abort(), { once: true })
  }
  try {
    return await fetch(`/api${path}`, { ...options, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

/** 网络层错误统一翻译：超时/外部取消/断网 → 可操作提示（i18n 公共文案）。 */
function networkError(err: unknown, options?: RequestInit): ApiError {
  if (err instanceof DOMException && err.name === 'AbortError') {
    return new ApiError(options?.signal?.aborted ? t('请求已取消') : t('请求超时，请稍后重试'), -1, 0)
  }
  return new ApiError(t('网络连接失败，请检查网络后重试'), -1, 0)
}

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const method = (options.method || 'GET').toUpperCase()
  let resp: Response
  try {
    resp = await fetchWithTimeout(path, { ...options, headers })
  } catch (err) {
    // 幂等 GET：网络层失败（断网/超时）自动重试一次；写操作不重试（避免重复副作用）
    if (method === 'GET') {
      try {
        resp = await fetchWithTimeout(path, { ...options, headers })
      } catch (err2) {
        throw networkError(err2, options)
      }
    } else {
      throw networkError(err, options)
    }
  }
  let body: ApiResult<T>
  try {
    body = await resp.json()
  } catch {
    throw new ApiError(t('服务响应异常 ({status})', { status: resp.status }), -1, resp.status)
  }

  if (body.code !== 0) {
    // 401 时清理 token 并广播会话失效（AuthContext 监听后置空 user → RequireAuth 跳登录）
    if (resp.status === 401) {
      setToken(null)
      window.dispatchEvent(new CustomEvent('gift:unauthorized'))
    }
    throw new ApiError(body.message || t('请求失败'), body.code, resp.status)
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
    let resp: Response
    try {
      resp = await fetchWithTimeout(path, { method: 'POST', body: form, headers })
    } catch (err) {
      // 网络层错误（断网/超时/跨域等）→ 统一中文提示；上传不自动重试（大文件重复上传浪费流量）
      throw networkError(err)
    }
    let body: ApiResult<T>
    try {
      body = await resp.json()
    } catch {
      throw new ApiError(t('服务响应异常 ({status})', { status: resp.status }), -1, resp.status)
    }
    if (body.code !== 0) {
      if (resp.status === 401) {
        setToken(null)
        window.dispatchEvent(new CustomEvent('gift:unauthorized'))
      }
      throw new ApiError(body.message || t('上传失败'), body.code, resp.status)
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
  /** 个人心愿单：想要什么礼物（v12，展示给送礼人需 wishlistVisible） */
  wishlist?: string
  wishlistVisible?: boolean
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
  archived: boolean
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

export type MemberStatus = 'joined' | 'ready' | 'shipped' | 'posted'

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
  status?: MemberStatus
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
  /** 收礼人个人心愿单（仅当其开启展示时返回，v12） */
  receiverWishlist?: string
}

export interface Shipment {
  status: 'pending' | 'shipped' | 'delivered'
  carrier: string
  trackingNumber: string
  shippedAt: string
  trackingUpdatedAt: string
  trackingSummary: string
  /** 物流查询失败（可手动刷新重试）时为 true */
  trackingRefreshable: boolean
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
  /** 邀请短码（分享文案按钮依赖，v12+） */
  shortCode?: string
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
