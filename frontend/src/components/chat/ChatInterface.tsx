import { useState } from 'react'
import { useChatStore } from '../../store/chatStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import MessageList from './MessageList'
import MessageInput from './MessageInput'
import SourcesSidebar from './SourcesSidebar'
import { Bot, Menu, X } from 'lucide-react'

export default function ChatInterface() {
  const { messages, streamingMessage, sources, isStreaming } = useChatStore()
  const { sendMessage, isConnected } = useWebSocket()
  const [showSources, setShowSources] = useState(true)
  
  const handleSendMessage = (content: string) => {
    // Add user message immediately
    useChatStore.getState().addMessage({
      role: 'user',
      content,
    })
    
    // Send to WebSocket
    sendMessage(content)
  }
  
  return (
    <div className="flex h-full flex-col bg-gray-50">
      {/* Header */}
      <header className="border-b bg-white px-6 py-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600">
              <Bot className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-gray-900">
                Workforce AI Agent
              </h1>
              <p className="text-sm text-gray-500">
                {isConnected ? (
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-green-500" />
                    Connected
                  </span>
                ) : (
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-red-500" />
                    Disconnected
                  </span>
                )}
              </p>
            </div>
          </div>
          
          <button
            onClick={() => setShowSources(!showSources)}
            className="rounded-lg p-2 hover:bg-gray-100 lg:hidden"
          >
            {showSources ? (
              <X className="h-5 w-5" />
            ) : (
              <Menu className="h-5 w-5" />
            )}
          </button>
        </div>
      </header>
      
      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Chat messages */}
        <div className="flex flex-1 flex-col">
          <div className="flex-1 overflow-y-auto">
            <MessageList
              messages={messages}
              streamingMessage={streamingMessage}
              isStreaming={isStreaming}
            />
          </div>
          
          <div className="border-t bg-white p-4">
            <MessageInput
              onSendMessage={handleSendMessage}
              disabled={isStreaming || !isConnected}
            />
          </div>
        </div>
        
        {/* Sources sidebar */}
        <aside
          className={`w-80 border-l bg-white transition-all ${
            showSources ? 'block' : 'hidden lg:block'
          }`}
        >
          <SourcesSidebar sources={sources} />
        </aside>
      </div>
    </div>
  )
}
