import { useEffect, useState } from 'react'
import ChatInterface from './components/chat/ChatInterface'
import PipelinesInterface from './components/pipelines/PipelinesInterface'
import ProjectsInterface from './components/projects/ProjectsInterface'
import WorkflowsInterface from './components/workflows/WorkflowsInterface'
import SignInView from './components/auth/SignInView'
import ProfileInterface from './components/auth/ProfileInterface'
import CalendarInterface from './components/calendar/CalendarInterface'
import { useAuthStore } from './store/authStore'

function App() {
  type Tab = 'chat' | 'pipelines' | 'projects' | 'workflows' | 'calendar' | 'profile'

  const [activeTab, setActiveTab] = useState<Tab>(() => {
    if (typeof window === 'undefined') return 'chat'
    const stored = window.localStorage.getItem('workforce-active-tab')
    if (
      stored === 'pipelines' ||
      stored === 'projects' ||
      stored === 'chat' ||
      stored === 'workflows' ||
      stored === 'calendar' ||
      stored === 'profile'
    ) {
      return stored as Tab
    }
    return 'chat'
  })

  const { user, loading, fetchMe } = useAuthStore()

  useEffect(() => {
    fetchMe()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('workforce-active-tab', activeTab)
    }
  }, [activeTab])

  if (loading) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Loading your workspace…</p>
      </div>
    )
  }

  if (!user) {
    return <SignInView />
  }

  return (
    <div className="h-screen w-full flex flex-col bg-background">
      <header className="border-b border-border bg-card px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-foreground">Workforce AI Agent</span>
          <span className="text-[11px] text-muted-foreground">Chat, Pipelines, Projects & Workflows</span>
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
          <button
            type="button"
            onClick={() => setActiveTab('projects')}
            className={`rounded-md px-3 py-1 font-medium border text-xs ${
              activeTab === 'projects'
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-background text-foreground border-border hover:bg-muted'
            }`}
          >
            Projects
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('workflows')}
            className={`rounded-md px-3 py-1 font-medium border text-xs ${
              activeTab === 'workflows'
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-background text-foreground border-border hover:bg-muted'
            }`}
          >
            Workflows
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('calendar')}
            className={`rounded-md px-3 py-1 font-medium border text-xs ${
              activeTab === 'calendar'
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-background text-foreground border-border hover:bg-muted'
            }`}
          >
            Calendar
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('profile')}
            className={`rounded-md px-3 py-1 font-medium border text-xs ${
              activeTab === 'profile'
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-background text-foreground border-border hover:bg-muted'
            }`}
          >
            Profile
          </button>
        </nav>
      </header>

      <main className="flex-1 overflow-hidden">
        <div className={activeTab === 'chat' ? 'h-full block' : 'h-full hidden'}>
          <ChatInterface />
        </div>
        <div className={activeTab === 'pipelines' ? 'h-full block' : 'h-full hidden'}>
          <PipelinesInterface />
        </div>
        <div className={activeTab === 'projects' ? 'h-full block' : 'h-full hidden'}>
          <ProjectsInterface />
        </div>
        <div className={activeTab === 'workflows' ? 'h-full block' : 'h-full hidden'}>
          <WorkflowsInterface />
        </div>
        <div className={activeTab === 'calendar' ? 'h-full block' : 'h-full hidden'}>
          <CalendarInterface />
        </div>
        <div className={activeTab === 'profile' ? 'h-full block' : 'h-full hidden'}>
          <ProfileInterface />
        </div>
      </main>
    </div>
  )
}

export default App
