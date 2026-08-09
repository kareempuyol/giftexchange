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
