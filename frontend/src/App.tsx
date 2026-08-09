// 文案暂未接入 i18n（示范迁移仅 Header/登录页/Toast 公共文案）：后续按 i18n.ts 迁移指南接入
import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { ToastProvider } from './components/Toast'
import ErrorBoundary from './components/ErrorBoundary'
import Header from './components/Header'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import EventsPage from './pages/EventsPage'
// 非首屏页面按路由分包（React.lazy）：详情页含海报/qrcode 依赖，首屏不加载
const EventDetailPage = lazy(() => import('./pages/EventDetailPage'))
const CreateEventPage = lazy(() => import('./pages/CreateEventPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const GiftWallPage = lazy(() => import('./pages/GiftWallPage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))

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
        {/* App 级错误边界：任何页面渲染崩溃都不白屏 */}
        <ErrorBoundary>
          <Suspense fallback={<div className="page-loading"><span className="spinner" aria-hidden="true" />加载中…</div>}>
            <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/events" element={<RequireAuth><Layout><EventsPage /></Layout></RequireAuth>} />
            <Route path="/events/new" element={<RequireAuth><Layout><CreateEventPage /></Layout></RequireAuth>} />
            {/* 活动详情级错误边界：详情页渲染崩溃不影响全局（如数据异常） */}
            <Route path="/events/:code" element={<Layout><ErrorBoundary><EventDetailPage /></ErrorBoundary></Layout>} />
            <Route path="/events/:code/dashboard" element={<RequireAuth><Layout><DashboardPage /></Layout></RequireAuth>} />
            <Route path="/events/:code/gift-wall" element={<RequireAuth><Layout><GiftWallPage /></Layout></RequireAuth>} />
            <Route path="/profile" element={<RequireAuth><Layout><ProfilePage /></Layout></RequireAuth>} />
            <Route path="/" element={<Navigate to="/events" replace />} />
            <Route path="*" element={<Navigate to="/events" replace />} />
          </Routes>
          </Suspense>
        </ErrorBoundary>
      </ToastProvider>
    </AuthProvider>
  )
}
