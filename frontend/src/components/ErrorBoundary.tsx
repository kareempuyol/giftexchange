import { Component, ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
  /** 子级渲染崩溃时的兜底提示（默认通用文案） */
  fallback?: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
}

/**
 * 渲染错误边界：子组件渲染崩溃时不白屏，显示「页面出错了」+ 刷新按钮。
 * 用法：App 级包裹整个路由树 + 活动详情页单独包裹。
 */
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: unknown) {
    // 上报到控制台便于排查；不打断用户（已由 fallback UI 接管）
    console.error('[ErrorBoundary] render error:', error)
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="error-boundary" role="alert">
            <div className="error-boundary-icon">😵</div>
            <div className="error-boundary-title">页面出错了</div>
            <p className="error-boundary-desc">渲染时遇到了一点问题，刷新重试即可</p>
            <button
              type="button"
              className="btn btn-primary"
              style={{ width: 'auto', padding: '0 32px' }}
              onClick={() => {
                this.setState({ hasError: false })
                window.location.reload()
              }}
            >
              刷新重试
            </button>
          </div>
        )
      )
    }
    return this.props.children
  }
}
