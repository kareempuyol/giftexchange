import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { api, User, getToken, setToken } from '../api/client'

interface AuthState {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<void>
  logout: () => void
  /** 局部更新当前用户（如个人中心改昵称/头像后同步 Header） */
  updateUser: (patch: Partial<User>) => void
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  login: async () => {},
  register: async () => {},
  logout: () => {},
  updateUser: () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = getToken()
    if (!token) {
      setLoading(false)
      return
    }
    api.get<User>('/auth/me')
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [])

  // 服务端 401（token 失效/账号注销/会话过期）：置空 user → RequireAuth 自动跳登录（带 from 回跳）
  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener('gift:unauthorized', onUnauthorized)
    return () => window.removeEventListener('gift:unauthorized', onUnauthorized)
  }, [])

  // 登录/会话恢复后预取下一跳路由 chunk：/events 是主入口（登录/注册/刷新直落），
  // 详情页是列表点击第一去向——趁用户浏览列表时提前下载，点开即渲染
  useEffect(() => {
    if (!user) return
    Promise.all([
      import('../pages/EventsPage'),
      import('../pages/EventDetailPage'),
    ]).catch(() => {
      /* 预取失败静默：懒加载路径兜底 */
    })
  }, [user])

  const login = async (username: string, password: string) => {
    const data = await api.post<{ token: string; user: User }>('/auth/login', { username, password })
    setToken(data.token)
    setUser(data.user)
  }

  const register = async (username: string, email: string, password: string) => {
    const data = await api.post<{ token: string; user: User }>('/auth/register', { username, email, password })
    setToken(data.token)
    setUser(data.user)
  }

  const logout = () => {
    setToken(null)
    setUser(null)
  }

  const updateUser = (patch: Partial<User>) => {
    setUser((prev) => (prev ? { ...prev, ...patch } : prev))
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, updateUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
