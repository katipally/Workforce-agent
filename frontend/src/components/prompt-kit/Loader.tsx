import { cn } from '../../lib/utils'

interface LoaderProps {
  variant?: 'dots' | 'pulse' | 'circular'
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export function DotsLoader({ size = 'md', className }: Omit<LoaderProps, 'variant'>) {
  const sizeClasses = {
    sm: 'h-1 w-1',
    md: 'h-1.5 w-1.5',
    lg: 'h-2 w-2'
  }

  const delays = ['[animation-delay:0s]', '[animation-delay:0.15s]', '[animation-delay:0.3s]']

  return (
    <div className={cn('flex items-center gap-1', className)}>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className={cn(
            'bg-foreground rounded-full animate-pulse [animation-duration:1s]',
            sizeClasses[size],
            delays[i]
          )}
        />
      ))}
    </div>
  )
}

export function Loader({ variant = 'dots', size = 'md', className }: LoaderProps) {
  if (variant === 'dots') {
    return <DotsLoader size={size} className={className} />
  }

  if (variant === 'circular') {
    const sizeClasses = {
      sm: 'h-4 w-4',
      md: 'h-5 w-5',
      lg: 'h-6 w-6'
    }

    return (
      <div className={cn('inline-block', className)}>
        <div className={cn('border-2 border-current border-t-transparent rounded-full animate-spin', sizeClasses[size])} />
      </div>
    )
  }

  return <DotsLoader size={size} className={className} />
}
