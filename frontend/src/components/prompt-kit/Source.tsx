import { ReactNode } from 'react'
import { cn } from '../../lib/utils'

interface SourceProps {
  children: ReactNode
  href?: string
  className?: string
}

export function Source({ children, href: _href, className }: SourceProps) {
  return (
    <div className={cn('inline-flex items-center gap-1', className)}>
      {children}
    </div>
  )
}

interface SourceTriggerProps {
  label?: string | number
  showFavicon?: boolean
  className?: string
}

export function SourceTrigger({ label, showFavicon: _showFavicon, className }: SourceTriggerProps) {
  return (
    <button
      type="button"
      className={cn(
        'inline-flex h-6 min-w-[24px] items-center justify-center rounded-full border border-border bg-background px-2 text-xs font-medium text-foreground hover:bg-muted transition-colors',
        className
      )}
    >
      {label}
    </button>
  )
}

interface SourceContentProps {
  title: string
  description?: string
  className?: string
}

export function SourceContent({ title, description, className }: SourceContentProps) {
  return (
    <div className={cn('rounded-md border border-border bg-card p-3 text-xs shadow-sm', className)}>
      <div className="font-medium text-card-foreground">{title}</div>
      {description && (
        <div className="mt-1 text-muted-foreground line-clamp-2">{description}</div>
      )}
    </div>
  )
}
