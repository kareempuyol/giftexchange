import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { ToastProvider } from './components/Toast'
import Header from './components/Header'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import EventsPage from './pages/EventsPage'
import EventDetailPage from './pages/EventDetailPage'
import CreateEventPage from './pages/CreateEventPage'
import DashboardPage from './pages/DashboardPage'
import GiftWallPage from './pages/GiftWallPage'
import ProfilePage from './pages/ProfilePage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="page-loading">加载中…</div>
  if (!user) {
    // 保留目标路径，登录/注册后跳回（支持邀请链接直达）
    const target = location.pathname + location.search
    return <Navigate to={`/login?from=${encodeURIComponent(target.slice(1))}`} replace />
  }
  return <>{children}</>
}

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Header />
      <main className="app-main">{children}</main>
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/events" element={<RequireAuth><Layout><EventsPage /></Layout></RequireAuth>} />
          <Route path="/events/new" element={<RequireAuth><Layout><CreateEventPage /></Layout></RequireAuth>} />
          <Route path="/events/:code" element={<Layout><EventDetailPage /></Layout>} />
          <Route path="/events/:code/dashboard" element={<RequireAuth><Layout><DashboardPage /></Layout></RequireAuth>} />
          <Route path="/events/:code/gift-wall" element={<RequireAuth><Layout><GiftWallPage /></Layout></RequireAuth>} />
          <Route path="/profile" element={<RequireAuth><Layout><ProfilePage /></Layout></RequireAuth>} />
          <Route path="/" element={<Navigate to="/events" replace />} />
          <Route path="*" element={<Navigate to="/events" replace />} />
        </Routes>
      </ToastProvider>
    </AuthProvider>
  )
}
