import { useEffect, useRef } from 'react'
import { Message } from '../../store/chatStore'
import { Bot, User, Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'

interface MessageListProps {
  messages: Message[]
  streamingMessage?: string
  isStreaming?: boolean
}

export default function MessageList({
  messages,
  streamingMessage,
  isStreaming,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  
  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingMessage])
  
  if (messages.length === 0 && !streamingMessage) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="text-center">
          <Bot className="mx-auto h-16 w-16 text-gray-300" />
          <h2 className="mt-4 text-xl font-semibold text-gray-700">
            Welcome to Workforce AI Agent
          </h2>
          <p className="mt-2 text-gray-500">
            Ask me anything about your Slack messages, Gmail, or Notion data.
          </p>
          <div className="mt-6 space-y-2 text-left">
            <p className="text-sm text-gray-600">Try asking:</p>
            <ul className="space-y-1 text-sm text-gray-500">
              <li>• "What did Sarah say about the Q4 deadline?"</li>
              <li>• "Find emails from john@company.com this week"</li>
              <li>• "Summarize messages in #engineering channel"</li>
            </ul>
          </div>
        </div>
      </div>
    )
  }
  
  return (
    <div className="space-y-6 p-6">
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
      
      {streamingMessage && (
        <div className="flex gap-4">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-blue-600">
            <Bot className="h-6 w-6 text-white" />
          </div>
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-gray-900">AI Assistant</span>
              {isStreaming && (
                <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
              )}
            </div>
            <div className="prose prose-sm max-w-none">
              <p className="whitespace-pre-wrap text-gray-700">
                {streamingMessage}
              </p>
            </div>
          </div>
        </div>
      )}
      
      <div ref={bottomRef} />
    </div>
  )
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'
  
  return (
    <div className={cn('flex gap-4', isUser && 'justify-end')}>
      {!isUser && (
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-blue-600">
          <Bot className="h-6 w-6 text-white" />
        </div>
      )}
      
      <div className={cn('flex-1 space-y-2', isUser && 'flex flex-col items-end')}>
        <div className="flex items-center gap-2">
          <span className="font-semibold text-gray-900">
            {isUser ? 'You' : 'AI Assistant'}
          </span>
          <span className="text-xs text-gray-500">
            {message.timestamp.toLocaleTimeString()}
          </span>
        </div>
        
        <div
          className={cn(
            'rounded-lg px-4 py-3',
            isUser
              ? 'bg-blue-600 text-white'
              : 'bg-white text-gray-700 shadow-sm'
          )}
        >
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
        
        {message.sources && message.sources.length > 0 && (
          <div className="text-xs text-gray-500">
            {message.sources.length} source{message.sources.length > 1 ? 's' : ''}
          </div>
        )}
      </div>
      
      {isUser && (
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-gray-600">
          <User className="h-6 w-6 text-white" />
        </div>
      )}
    </div>
  )
}
