import { useEffect, useState, memo } from 'react'
import { Message as MessageType, useChatStore } from '../../store/chatStore'
import { Bot, Copy, ThumbsUp, ThumbsDown } from 'lucide-react'
import { cn } from '../../lib/utils'
import { ChatContainerRoot, ChatContainerContent, ChatContainerScrollAnchor } from '../prompt-kit/ChatContainer'
import { Message, MessageAvatar, MessageContent, MessageActions, MessageAction } from '../prompt-kit/Message'
import { DotsLoader } from '../prompt-kit/Loader'
import { Reasoning, ReasoningTrigger, ReasoningContent } from '../prompt-kit/Reasoning'
import { Source, SourceTrigger, SourceContent } from '../prompt-kit/Source'

interface MessageListProps {
  messages: MessageType[]
  streamingMessage?: string
  isStreaming?: boolean
  onSendMessage?: (content: string) => void
}

export default function MessageList({
  messages,
  streamingMessage,
  isStreaming,
  onSendMessage,
}: MessageListProps) {
  const { currentReasoningSteps } = useChatStore()
  const MAX_VISIBLE_MESSAGES = 60

  const totalMessages = messages.length
  const [showAllMessages, setShowAllMessages] = useState(false)

  const visibleMessages =
    showAllMessages || totalMessages <= MAX_VISIBLE_MESSAGES
      ? messages
      : messages.slice(totalMessages - MAX_VISIBLE_MESSAGES)
  
  if (messages.length === 0 && !streamingMessage) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="text-center max-w-md">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600">
            <Bot className="h-10 w-10 text-white" />
          </div>
          <h2 className="text-2xl font-bold text-foreground mb-2">
            Hi! I'm your Workforce AI Agent
          </h2>
          <p className="text-muted-foreground">
            I can help you with Slack, Gmail, and Notion. Ask me anything!
          </p>
        </div>
      </div>
    )
  }
  
  return (
    <ChatContainerRoot className="flex-1">
      <ChatContainerContent className="mx-auto w-full max-w-3xl space-y-12 px-4 py-12">
        {!showAllMessages && totalMessages > MAX_VISIBLE_MESSAGES && (
          <div className="flex justify-center">
            <button
              type="button"
              className="rounded-full border border-border bg-background/60 px-4 py-1 text-xs text-muted-foreground hover:bg-background"
              onClick={() => setShowAllMessages(true)}
            >
              Show older messages ({totalMessages - visibleMessages.length} hidden)
            </button>
          </div>
        )}

        {visibleMessages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            onSendMessage={onSendMessage}
          />
        ))}
        
        {streamingMessage && (
          <Message className="justify-start">
            <MessageAvatar fallback="AI" className="bg-blue-600" />
            <div className="flex w-full min-w-0 flex-1 flex-col gap-2">
              <MessageContent markdown className="text-foreground prose prose-sm max-w-[85%] sm:max-w-[75%]">
                {streamingMessage}
              </MessageContent>
              {isStreaming && <DotsLoader size="sm" />}

              {currentReasoningSteps && currentReasoningSteps.length > 0 && (() => {
                const steps = currentReasoningSteps.filter((s) => !s.startsWith('Reasoning Summary'))
                const summary = currentReasoningSteps.find((s) => s.startsWith('Reasoning Summary'))

                return (
                  <Reasoning isStreaming={!!isStreaming} className="mt-2">
                    <ReasoningContent className="space-y-2 whitespace-pre-wrap">
                      {steps.length > 0 && (
                        <div className="space-y-1">
                          <div className="mb-1 font-semibold">Thinking steps</div>
                          {steps.map((step, idx) => (
                            <div key={idx} className="flex gap-2">
                              <span className="mt-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-medium text-primary">
                                {idx + 1}
                              </span>
                              <span>{step}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {summary && (
                        <div className="border-t border-border pt-2 text-xs">
                          <div className="mb-1 font-semibold">Reasoning summary</div>
                          <div className="text-muted-foreground whitespace-pre-wrap">
                            {summary.replace(/^Reasoning Summary:?\s*/i, '')}
                          </div>
                        </div>
                      )}
                    </ReasoningContent>
                  </Reasoning>
                )
              })()}
            </div>
          </Message>
        )}
        
        <ChatContainerScrollAnchor />
      </ChatContainerContent>
    </ChatContainerRoot>
  )
}

const MessageBubble = memo(function MessageBubble({
  message,
  onSendMessage,
}: {
  message: MessageType
  onSendMessage?: (content: string) => void
}) {
  const isUser = message.role === 'user'
  const [showDetails, setShowDetails] = useState(false)
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null)
  const [copied, setCopied] = useState(false)

  const reasoningSteps = message.reasoningSteps || []
  const thinkingSteps = reasoningSteps.filter((s) => !s.startsWith('Reasoning Summary'))
  const reasoningSummary = reasoningSteps.find((s) => s.startsWith('Reasoning Summary'))

  const safetyGuardrailText = 'Safety guardrail: refusing to execute'
  const hasSafetyGuardrail = !isUser && typeof message.content === 'string' && message.content.includes(safetyGuardrailText)

  const handleCopy = () => {
    if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard
        .writeText(message.content)
        .then(() => setCopied(true))
        .catch(() => setCopied(false))
    }
  }

  useEffect(() => {
    if (!copied) return
    const timeout = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(timeout)
  }, [copied])
  
  return (
    <Message className={cn(isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && <MessageAvatar fallback="AI" className="bg-blue-600" />}
      
      <div className={cn('flex w-full min-w-0 flex-1 flex-col gap-2', isUser && 'items-end')}>
        {isUser ? (
          <div className="rounded-3xl px-5 py-2.5 max-w-[85%] whitespace-pre-wrap sm:max-w-[75%] bg-primary text-primary-foreground">
            {message.content}
          </div>
        ) : (
          <MessageContent markdown className="max-w-[85%] sm:max-w-[75%]">
            {message.content}
          </MessageContent>
        )}

        {!isUser && ((reasoningSteps.length ?? 0) > 0 || (message.sources?.length ?? 0) > 0) && (
          <Reasoning
            open={showDetails}
            onOpenChange={setShowDetails}
            className="space-y-2"
          >
            {reasoningSteps.length > 0 && (
              <ReasoningTrigger
                className="mt-1"
                onClick={() => setShowDetails((prev) => !prev)}
              >
                <span>{showDetails ? 'Hide thinking' : 'Show thinking'}</span>
              </ReasoningTrigger>
            )}

            {showDetails && (
              <ReasoningContent className="mt-1 space-y-2 whitespace-pre-wrap">
                {thinkingSteps.length > 0 && (
                  <div className="space-y-1">
                    {thinkingSteps.map((step, idx) => (
                      <div key={idx} className="flex gap-2">
                        <span className="mt-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-medium text-primary">
                          {idx + 1}
                        </span>
                        <span>{step}</span>
                      </div>
                    ))}
                  </div>
                )}

                {reasoningSummary && (
                  <div className="border-t border-border pt-2 text-xs">
                    <div className="mb-1 font-semibold">Reasoning summary</div>
                    <div className="text-muted-foreground whitespace-pre-wrap">
                      {reasoningSummary.replace(/^Reasoning Summary:?\s*/i, '')}
                    </div>
                  </div>
                )}

                {message.sources && message.sources.length > 0 && (
                  <div className="mt-2 grid gap-2 text-xs">
                    {message.sources.map((source, idx) => {
                      const labelParts: string[] = []
                      if (source.type === 'slack') {
                        labelParts.push('Slack')
                        if (source.metadata.channel) labelParts.push(`#${source.metadata.channel}`)
                        if (source.metadata.user) labelParts.push(source.metadata.user)
                      } else if (source.type === 'gmail') {
                        labelParts.push('Gmail')
                        if (source.metadata.from) labelParts.push(source.metadata.from)
                        if (source.metadata.subject) labelParts.push(source.metadata.subject)
                      } else if (source.type === 'notion') {
                        labelParts.push('Notion')
                        if ((source.metadata as any).title) {
                          labelParts.push((source.metadata as any).title as string)
                        }
                      }
                      const label = labelParts.join(' · ') || source.type

                      return (
                        <Source key={idx} className="items-start gap-2">
                          <SourceTrigger label={`S${idx + 1}`} />
                          <SourceContent
                            title={label}
                            description={source.text}
                          />
                        </Source>
                      )
                    })}
                  </div>
                )}
              </ReasoningContent>
            )}
          </Reasoning>
        )}

        {!isUser && (
          <MessageActions className="-ml-2.5">
            <MessageAction tooltip="Copy response" onClick={handleCopy}>
              <Copy className={cn('h-3.5 w-3.5', copied && 'text-green-500')} />
            </MessageAction>
            <MessageAction
              tooltip="Helpful"
              onClick={() => setFeedback('up')}
            >
              <ThumbsUp className={cn('h-3.5 w-3.5', feedback === 'up' && 'fill-current text-green-500')} />
            </MessageAction>
            <MessageAction
              tooltip="Not helpful"
              onClick={() => setFeedback('down')}
            >
              <ThumbsDown className={cn('h-3.5 w-3.5', feedback === 'down' && 'fill-current text-red-500')} />
            </MessageAction>
          </MessageActions>
        )}

        {!isUser && hasSafetyGuardrail && onSendMessage && (
          <div className="mt-2 inline-flex flex-wrap items-center gap-2 rounded-md border border-yellow-300 bg-yellow-50 px-3 py-2 text-xs text-yellow-900">
            <span className="font-semibold">Action requires confirmation.</span>
            <button
              type="button"
              className="rounded bg-yellow-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-yellow-700"
              onClick={() =>
                onSendMessage(
                  'You have my explicit confirmation to proceed with the previously described action. '
                  + 'Please call the same tool again with confirmed=true and then continue.'
                )
              }
            >
              Confirm action
            </button>
          </div>
        )}
      </div>
      
      {isUser && <MessageAvatar fallback="You" className="bg-gray-600" />}
    </Message>
  )
})
