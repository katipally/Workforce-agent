import { useEffect, useRef, ReactNode } from 'react'
import { cn } from '../../lib/utils'

interface ChatContainerRootProps {
  children: ReactNode
  className?: string
}

export function ChatContainerRoot({ children, className }: ChatContainerRootProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const isAtBottomRef = useRef(true)
  
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container
      const distanceFromBottom = scrollHeight - scrollTop - clientHeight
      isAtBottomRef.current = distanceFromBottom < 50
    }

    container.addEventListener('scroll', handleScroll)
    return () => container.removeEventListener('scroll', handleScroll)
  }, [])

  useEffect(() => {
    const container = containerRef.current
    if (!container || !isAtBottomRef.current) return

    const scrollToBottom = () => {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth'
      })
    }

    const observer = new ResizeObserver(() => {
      if (isAtBottomRef.current) {
        scrollToBottom()
      }
    })

    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  return (
    <div
      ref={containerRef}
      className={cn('overflow-y-auto', className)}
    >
      {children}
    </div>
  )
}

interface ChatContainerContentProps {
  children: ReactNode
  className?: string
}

export function ChatContainerContent({ children, className }: ChatContainerContentProps) {
  return (
    <div className={cn('space-y-0', className)}>
      {children}
    </div>
  )
}

export function ChatContainerScrollAnchor() {
  const anchorRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    anchorRef.current?.scrollIntoView({ behavior: 'smooth' })
  })

  return <div ref={anchorRef} className="h-px w-full" />
}
