import { useState } from 'react'
import ChatInterface from './components/chat/ChatInterface'
import PipelinesInterface from './components/pipelines/PipelinesInterface'

function App() {
  const [activeTab, setActiveTab] = useState<'chat' | 'pipelines'>('chat')

  return (
    <div className="h-screen w-full flex flex-col bg-background">
      <header className="border-b border-border bg-card px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-foreground">Workforce AI Agent</span>
          <span className="text-[11px] text-muted-foreground">Chat & Pipelines</span>
        </div>
        <nav className="flex items-center gap-2 text-xs">
          <button
            type="button"
            onClick={() => setActiveTab('chat')}
            className={`rounded-md px-3 py-1 font-medium border text-xs ${
              activeTab === 'chat'
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-background text-foreground border-border hover:bg-muted'
            }`}
          >
            Chat
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('pipelines')}
            className={`rounded-md px-3 py-1 font-medium border text-xs ${
              activeTab === 'pipelines'
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-background text-foreground border-border hover:bg-muted'
            }`}
          >
            Pipelines
          </button>
        </nav>
      </header>

      <main className="flex-1 overflow-hidden">
        {activeTab === 'chat' ? <ChatInterface /> : <PipelinesInterface />}
      </main>
    </div>
  )
}

export default App
