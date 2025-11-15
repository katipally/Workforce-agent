import { ReactNode, useState, useEffect, useRef, ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'
import { ChevronRight } from 'lucide-react'

interface ReasoningProps {
  children: ReactNode
  isStreaming?: boolean
  open?: boolean
  onOpenChange?: (open: boolean) => void
  className?: string
}

export function Reasoning({
  children,
  isStreaming = false,
  open: controlledOpen,
  onOpenChange,
  className
}: ReasoningProps) {
  const [internalOpen, setInternalOpen] = useState(true)
  const isControlled = controlledOpen !== undefined

  const isOpen = isControlled ? controlledOpen : internalOpen
  const prevIsStreamingRef = useRef(isStreaming)

  // Auto-close when streaming ends
  useEffect(() => {
    const prevIsStreaming = prevIsStreamingRef.current
    prevIsStreamingRef.current = isStreaming

    // Only auto-close when we transition from streaming -> not streaming
    if (prevIsStreaming && !isStreaming && isOpen) {
      setTimeout(() => {
        if (isControlled) {
          onOpenChange?.(false)
        } else {
          setInternalOpen(false)
        }
      }, 300)
    }
  }, [isStreaming, isOpen, isControlled, onOpenChange])

  return (
    <div className={cn('', className)}>
      {children}
    </div>
  )
}

interface ReasoningTriggerProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode
  className?: string
}

export function ReasoningTrigger({ children, className, ...props }: ReasoningTriggerProps) {
  return (
    <button
      type="button"
      {...props}
      className={cn(
        'inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground hover:bg-muted/80 transition-colors',
        className
      )}
    >
      <ChevronRight className="h-3 w-3" />
      {children}
    </button>
  )
}

interface ReasoningContentProps {
  children: ReactNode
  markdown?: boolean
  className?: string
}

export function ReasoningContent({ children, markdown: _markdown = false, className }: ReasoningContentProps) {
  return (
    <div className={cn('mt-2 border-l-2 border-muted pl-3 text-xs text-muted-foreground', className)}>
      {children}
    </div>
  )
}
