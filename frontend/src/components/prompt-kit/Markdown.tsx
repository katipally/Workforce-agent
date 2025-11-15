import { cn } from '../../lib/utils'

interface MarkdownProps {
  children: string
  className?: string
}

export function Markdown({ children, className }: MarkdownProps) {
  // Simple markdown-like formatting for now
  // In production, you'd use react-markdown + remark-gfm
  const formattedText = children
    .split('\n')
    .map((line, idx) => {
      // Code blocks
      if (line.startsWith('```')) {
        return null
      }
      
      // Headings
      if (line.startsWith('### ')) {
        return <h3 key={idx} className="text-base font-semibold mt-4 mb-2">{line.slice(4)}</h3>
      }
      if (line.startsWith('## ')) {
        return <h2 key={idx} className="text-lg font-semibold mt-4 mb-2">{line.slice(3)}</h2>
      }
      if (line.startsWith('# ')) {
        return <h1 key={idx} className="text-xl font-bold mt-4 mb-2">{line.slice(2)}</h1>
      }
      
      // Lists
      if (line.startsWith('- ') || line.startsWith('* ')) {
        return <li key={idx} className="ml-4">{line.slice(2)}</li>
      }
      
      // Paragraphs
      if (line.trim()) {
        return <p key={idx} className="mb-2">{line}</p>
      }
      
      return <br key={idx} />
    })

  return (
    <div className={cn('prose prose-sm max-w-none', className)}>
      {formattedText}
    </div>
  )
}
