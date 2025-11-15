import { ReactNode } from 'react'
import { cn } from '../../lib/utils'
import { Markdown } from './Markdown'

interface MessageProps {
  children: ReactNode
  className?: string
}

export function Message({ children, className }: MessageProps) {
  return (
    <div className={cn('flex gap-4 py-6', className)}>
      {children}
    </div>
  )
}

interface MessageAvatarProps {
  src?: string
  alt?: string
  fallback: string
  className?: string
}

export function MessageAvatar({ src, alt, fallback, className }: MessageAvatarProps) {
  return (
    <div className={cn('flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-medium', className)}>
      {src ? (
        <img src={src} alt={alt} className="h-full w-full rounded-full object-cover" />
      ) : (
        fallback
      )}
    </div>
  )
}

interface MessageContentProps {
  children: ReactNode
  markdown?: boolean
  className?: string
}

export function MessageContent({ children, markdown = false, className }: MessageContentProps) {
  if (markdown && typeof children === 'string') {
    return (
      <div className={cn('text-foreground prose prose-sm max-w-full break-words', className)}>
        <Markdown>{children}</Markdown>
      </div>
    )
  }

  return (
    <div className={cn('text-foreground whitespace-pre-wrap break-words', className)}>
      {children}
    </div>
  )
}

interface MessageActionsProps {
  children: ReactNode
  className?: string
}

export function MessageActions({ children, className }: MessageActionsProps) {
  return (
    <div className={cn('flex items-center gap-1 mt-2', className)}>
      {children}
    </div>
  )
}

interface MessageActionProps {
  children: ReactNode
  tooltip?: string
  className?: string
  onClick?: () => void
}

export function MessageAction({ children, tooltip, className, onClick }: MessageActionProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={tooltip}
      className={cn(
        'inline-flex h-7 w-7 items-center justify-center rounded-full hover:bg-muted transition-colors',
        className
      )}
    >
      {children}
    </button>
  )
}
