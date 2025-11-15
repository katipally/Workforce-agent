import { ReactNode, useRef, KeyboardEvent, useEffect } from 'react'
import { cn } from '../../lib/utils'

interface PromptInputProps {
  value: string
  onValueChange: (value: string) => void
  onSubmit: () => void
  isLoading?: boolean
  children: ReactNode
  className?: string
}

export function PromptInput({
  value: _value,
  onValueChange: _onValueChange,
  onSubmit,
  isLoading = false,
  children,
  className
}: PromptInputProps) {
  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!isLoading) {
      onSubmit()
    }
  }

  return (
    <form onSubmit={handleSubmit} className={cn('relative', className)}>
      {children}
    </form>
  )
}

interface PromptInputTextareaProps {
  placeholder?: string
  disabled?: boolean
  className?: string
}

export function PromptInputTextarea({ placeholder, disabled, className }: PromptInputTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleInput = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      const form = textareaRef.current?.closest('form')
      if (form) {
        const submitEvent = new Event('submit', { cancelable: true, bubbles: true })
        form.dispatchEvent(submitEvent)
      }
    }
  }

  useEffect(() => {
    handleInput()
  }, [])

  return (
    <textarea
      ref={textareaRef}
      placeholder={placeholder}
      disabled={disabled}
      onInput={handleInput}
      onKeyDown={handleKeyDown}
      rows={1}
      className={cn(
        'w-full resize-none bg-transparent px-4 py-3 text-sm placeholder:text-muted-foreground focus:outline-none disabled:cursor-not-allowed disabled:opacity-50',
        'min-h-[44px] max-h-[200px]',
        className
      )}
    />
  )
}

interface PromptInputActionsProps {
  children: ReactNode
  className?: string
}

export function PromptInputActions({ children, className }: PromptInputActionsProps) {
  return (
    <div className={cn('flex items-center justify-between gap-2', className)}>
      {children}
    </div>
  )
}

interface PromptInputActionProps {
  children: ReactNode
  tooltip?: string
  className?: string
}

export function PromptInputAction({ children, tooltip, className }: PromptInputActionProps) {
  return (
    <div title={tooltip} className={cn('', className)}>
      {children}
    </div>
  )
}
