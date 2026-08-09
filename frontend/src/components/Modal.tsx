import { ReactNode, useEffect, useRef } from 'react'

interface ModalProps {
  /** 弹窗标题（h3 + aria-labelledby） */
  title: string
  /** 关闭回调：ESC / 点击遮罩 / 关闭按钮触发 */
  onClose: () => void
  children: ReactNode
  maxWidth?: number
}

let modalId = 0

/**
 * 通用弹窗（a11y）：
 * - role="dialog" aria-modal="true" aria-labelledby 指向标题
 * - ESC 关闭；打开时聚焦首个可聚焦元素，关闭时回焦到触发元素
 * - Tab 焦点圈定在弹窗内（简单焦点陷阱）
 */
export default function Modal({ title, onClose, children, maxWidth }: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const titleId = useRef(`modal-title-${++modalId}`)
  const prevFocus = useRef<HTMLElement | null>(null)

  useEffect(() => {
    prevFocus.current = document.activeElement as HTMLElement | null
    const el = dialogRef.current
    const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    const focusables = Array.from(el?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])
    if (focusables.length > 0) focusables[0].focus()
    else el?.focus()

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      // Tab 焦点圈定
      if (e.key === 'Tab' && el) {
        const list = Array.from(el.querySelectorAll<HTMLElement>(FOCUSABLE))
        if (list.length === 0) return
        const first = list[0]
        const last = list[list.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      const prev = prevFocus.current
      if (prev && prev !== document.body && prev.isConnected) {
        prev.focus?.()
      } else {
        // 自动打开的弹窗（触发元素已卸载/无触发元素）：回焦到页面标题，避免焦点丢失
        const h1 = document.querySelector('h1')
        if (h1) {
          h1.setAttribute('tabindex', '-1')
          h1.focus()
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        ref={dialogRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId.current}
        tabIndex={-1}
        style={maxWidth ? { maxWidth } : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id={titleId.current}>{title}</h3>
        {children}
      </div>
    </div>
  )
}
