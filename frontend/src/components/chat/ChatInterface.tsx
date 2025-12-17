import { useEffect, useState } from 'react'
import { useChatStore } from '../../store/chatStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import MessageList from './MessageList'
import MessageInput from './MessageInput'
import ChatHistorySidebar from './ChatHistorySidebar'
import QuickActions from './QuickActions'
import { Bot, History, Sparkles } from 'lucide-react'
import { API_BASE_URL } from '../../lib/api'

type ConnectorStatus = {
  status: 'connected' | 'disconnected' | 'degraded' | string
  detail?: string
}

type ChatConnectorHealth = {
  overall_status: 'connected' | 'disconnected' | 'degraded' | string
  slack: ConnectorStatus
  gmail: ConnectorStatus
  notion: ConnectorStatus
}

export default function ChatInterface() {
  const { messages, streamingMessage, isStreaming, currentSessionId, sessionSourcePrefs, toggleSourcePreference } = useChatStore()
  const { sendMessage, isConnected, connectionStatus } = useWebSocket()
  const [connectorHealth, setConnectorHealth] = useState<ChatConnectorHealth | null>(null)
  const [showHistory, setShowHistory] = useState(() => {
    if (typeof window === 'undefined') return true
    const raw = window.localStorage.getItem('workforce-chat-show-history')
    return raw === 'false' ? false : true
  })
  const [showQuickActions, setShowQuickActions] = useState(() => {
    if (typeof window === 'undefined') return true
    const raw = window.localStorage.getItem('workforce-chat-show-quick-actions')
    return raw === 'false' ? false : true
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem('workforce-chat-show-history', String(showHistory))
  }, [showHistory])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem('workforce-chat-show-quick-actions', String(showQuickActions))
  }, [showQuickActions])
  
  useEffect(() => {
    const fetchConnectorHealth = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/chat/connectors/status`, {
          credentials: 'include',
        })
        if (!res.ok) return
        const data = (await res.json()) as ChatConnectorHealth
        setConnectorHealth(data)
      } catch {
        // Best-effort; header will just show WebSocket status on failure.
      }
    }

    // Fetch on mount and whenever WebSocket connection state changes
    fetchConnectorHealth()
  }, [isConnected, connectionStatus])
  
  const currentSourcePrefs = sessionSourcePrefs[currentSessionId] || {
    slack: true,
    gmail: true,
    notion: true,
  }

  const handleSendMessage = async (content: string, files?: File[]) => {
    const currentSessionId = useChatStore.getState().currentSessionId
    let fullMessage = content
    let uploadedFiles: any[] = []
    
    if (files && files.length > 0) {
      try {
        const formData = new FormData()
        files.forEach(file => formData.append('files', file))
        formData.append('session_id', currentSessionId)
        
        const response = await fetch(`${API_BASE_URL}/api/files/upload`, {
          method: 'POST',
          body: formData,
          credentials: 'include',
        })
        
        if (response.ok) {
          const data = await response.json()
          uploadedFiles = data.files
          
          const fileInfo = uploadedFiles.map(f => 
            `${f.filename} (${(f.file_size / 1024).toFixed(1)}KB)`
          ).join(', ')
          fullMessage += `\n\n📎 Uploaded: ${fileInfo}`
        } else {
          const error = await response.json()
          fullMessage += `\n\n⚠️ File upload failed: ${error.detail}`
        }
      } catch (error) {
        console.error('File upload error:', error)
        fullMessage += `\n\n⚠️ File upload error: ${error}`
      }
    }
    
    useChatStore.getState().addMessage({
      role: 'user',
      content: fullMessage,
    })
    
    if (messages.length === 0) {
      setShowQuickActions(false)
    }
    
    let messageToSend = content
    if (uploadedFiles.length > 0) {
      messageToSend += `\n\nFiles uploaded: ${uploadedFiles.map(f => f.stored_filename).join(', ')}`
    }
    sendMessage(messageToSend)
  }

  const handleRerunLastQuestion = () => {
    const state = useChatStore.getState()
    const sessionMessages = state.sessionMessages[currentSessionId] || []
    const lastUserMessage = [...sessionMessages].reverse().find((m) => m.role === 'user')
    if (!lastUserMessage) return
    void handleSendMessage(lastUserMessage.content)
  }

  const handleQuickAction = (prompt: string) => {
    handleSendMessage(prompt)
  }
  
  return (
    <div className="flex h-full bg-background">
      {/* History sidebar */}
      <aside
        className={`w-64 border-r border-border bg-secondary transition-all ${
          showHistory ? 'block' : 'hidden lg:block'
        }`}
      >
        <ChatHistorySidebar />
      </aside>
      
      {/* Main chat area */}
      <div className="flex flex-1 flex-col">
        {/* Header */}
        <header className="border-b border-border bg-card px-6 py-4 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setShowHistory(!showHistory)}
                className="rounded-lg p-2 hover:bg-muted lg:hidden"
                title="Toggle chat history"
                aria-label="Toggle chat history"
              >
                <History className="h-5 w-5" />
              </button>
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600">
                <Bot className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-semibold text-foreground flex items-center gap-2">
                  Workforce AI Agent
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300">
                    <Sparkles className="h-3 w-3" />
                    GPT-5 nano
                  </span>
                </h1>
                <div className="text-sm text-muted-foreground space-y-1 mt-0.5">
                  <div className="flex items-center gap-2">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        isConnected ? 'bg-green-500' : connectionStatus === 'connecting' ? 'bg-yellow-500' : 'bg-red-500'
                      }`}
                    />
                    <span>
                      {isConnected
                        ? 'Chat connection: Connected'
                        : connectionStatus === 'connecting'
                          ? 'Chat connection: Connecting…'
                          : 'Chat connection: Disconnected'}
                    </span>
                  </div>
                  {connectorHealth && (
                    <div className="flex flex-wrap items-center gap-3 text-xs">
                      <span className="flex items-center gap-1">
                        <span
                          className={`h-2 w-2 rounded-full ${
                            connectorHealth.slack.status === 'connected' ? 'bg-green-500' : 'bg-yellow-500'
                          }`}
                        />
                        <span>
                          Slack: {connectorHealth.slack.status === 'connected' ? 'Connected' : 'Disconnected'}
                        </span>
                      </span>
                      <span className="flex items-center gap-1">
                        <span
                          className={`h-2 w-2 rounded-full ${
                            connectorHealth.gmail.status === 'connected' ? 'bg-green-500' : 'bg-yellow-500'
                          }`}
                        />
                        <span>
                          Gmail: {connectorHealth.gmail.status === 'connected' ? 'Connected' : 'Disconnected'}
                        </span>
                      </span>
                      <span className="flex items-center gap-1">
                        <span
                          className={`h-2 w-2 rounded-full ${
                            connectorHealth.notion.status === 'connected' ? 'bg-green-500' : 'bg-yellow-500'
                          }`}
                        />
                        <span>
                          Notion: {connectorHealth.notion.status === 'connected' ? 'Connected' : 'Disconnected'}
                        </span>
                      </span>
                    </div>
                  )}
                  <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
                    <span className="text-muted-foreground/80">Sources in this chat:</span>
                    <button
                      type="button"
                      onClick={() => toggleSourcePreference('slack')}
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors ${
                        currentSourcePrefs.slack
                          ? 'border-blue-500 bg-blue-500/10 text-blue-500'
                          : 'border-border bg-background text-muted-foreground'
                      }`}
                    >
                      Slack
                    </button>
                    <button
                      type="button"
                      onClick={() => toggleSourcePreference('gmail')}
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors ${
                        currentSourcePrefs.gmail
                          ? 'border-emerald-500 bg-emerald-500/10 text-emerald-500'
                          : 'border-border bg-background text-muted-foreground'
                      }`}
                    >
                      Gmail
                    </button>
                    <button
                      type="button"
                      onClick={() => toggleSourcePreference('notion')}
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors ${
                        currentSourcePrefs.notion
                          ? 'border-purple-500 bg-purple-500/10 text-purple-500'
                          : 'border-border bg-background text-muted-foreground'
                      }`}
                    >
                      Notion
                    </button>
                    <button
                      type="button"
                      onClick={handleRerunLastQuestion}
                      disabled={isStreaming || !messages.some((m) => m.role === 'user')}
                      className="ml-1 inline-flex items-center rounded-full border border-border bg-background px-2 py-0.5 text-[11px] font-medium text-foreground hover:bg-muted disabled:opacity-50"
                    >
                      Re-run last question with these sources
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </header>
        
        {/* Chat content */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {messages.length === 0 && showQuickActions && !streamingMessage ? (
            <div className="flex items-center justify-center h-full p-8">
              <div className="max-w-3xl w-full">
                <div className="text-center mb-8">
                  <div className="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 mb-4">
                    <Bot className="h-10 w-10 text-white" />
                  </div>
                  <h2 className="text-2xl font-bold text-foreground mb-2">
                    Hi! I'm your Workforce AI Agent
                  </h2>
                  <p className="text-muted-foreground">
                    I can help you with Slack, Gmail, and Notion. Try a quick action or ask me anything!
                  </p>
                </div>
                <QuickActions onActionClick={handleQuickAction} />
              </div>
            </div>
          ) : (
            <MessageList
              messages={messages}
              streamingMessage={streamingMessage}
              isStreaming={isStreaming}
              onSendMessage={(content: string) => handleSendMessage(content)}
            />
          )}
        </div>
        
        {/* Input area */}
        <div className="border-t border-border bg-card p-4">
          <div className="mx-auto w-full max-w-3xl">
            <MessageInput
              onSendMessage={handleSendMessage}
              disabled={isStreaming || !isConnected}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
