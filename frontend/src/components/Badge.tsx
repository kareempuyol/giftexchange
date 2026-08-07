import { ReactNode } from 'react'

interface BadgeProps {
  children: ReactNode
  tone?: 'success' | 'warning' | 'error' | 'info' | 'gold'
}

export default function Badge({ children, tone = 'info' }: BadgeProps) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}
