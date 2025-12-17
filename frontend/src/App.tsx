import { useEffect, useState } from 'react'
import ChatInterface from './components/chat/ChatInterface'
import PipelinesInterface from './components/pipelines/PipelinesInterface'
import ProjectsInterface from './components/projects/ProjectsInterface'
import WorkflowsInterface from './components/workflows/WorkflowsInterfaceV2'
import SignInView from './components/auth/SignInView'
import ProfileInterface from './components/auth/ProfileInterface'
import CalendarInterface from './components/calendar/CalendarInterface'
import CommandMenu from './components/common/CommandMenu'
import ThemeToggle from './components/common/ThemeToggle'
import { useAuthStore } from './store/authStore'
import { useThemeStore } from './store/themeStore'
import { Search } from 'lucide-react'

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
  const { theme } = useThemeStore()

  // Initialize theme on mount
  useEffect(() => {
    const root = document.documentElement
    const getSystemTheme = () => window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    const effectiveTheme = theme === 'system' ? getSystemTheme() : theme
    if (effectiveTheme === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
  }, [theme])

  // Track which tabs have been mounted (once mounted, stay mounted)
  const [mountedTabs, setMountedTabs] = useState<Set<Tab>>(() => new Set([activeTab]))

  // Mount tab when it becomes active
  useEffect(() => {
    setMountedTabs((prev) => {
      if (prev.has(activeTab)) return prev
      return new Set([...prev, activeTab])
    })
  }, [activeTab])

  // Progressively load other tabs in the background after initial render
  useEffect(() => {
    const allTabs: Tab[] = ['chat', 'pipelines', 'projects', 'workflows', 'calendar', 'profile']
    let cancelled = false
    let timeoutId: ReturnType<typeof setTimeout>

    const loadNextTab = (index: number) => {
      if (cancelled || index >= allTabs.length) return
      const tab = allTabs[index]
      setMountedTabs((prev) => {
        if (prev.has(tab)) return prev
        return new Set([...prev, tab])
      })
      // Stagger loading by 500ms to avoid blocking the UI
      timeoutId = setTimeout(() => loadNextTab(index + 1), 500)
    }

    // Start progressive loading after a short delay to let the active tab settle
    timeoutId = setTimeout(() => loadNextTab(0), 1000)

    return () => {
      cancelled = true
      clearTimeout(timeoutId)
    }
  }, [])

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
      <CommandMenu onNavigate={setActiveTab} activeTab={activeTab} />

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

          {/* Divider */}
          <div className="h-4 w-px bg-border mx-1" />

          {/* Search button */}
          <button
            type="button"
            onClick={() => {
              const event = new KeyboardEvent('keydown', { key: 'k', metaKey: true })
              document.dispatchEvent(event)
            }}
            className="flex items-center gap-2 rounded-md px-2 py-1 text-xs border border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            title="Search (⌘K)"
          >
            <Search className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Search</span>
            <kbd className="hidden sm:inline-flex h-5 items-center gap-0.5 rounded border border-border bg-muted px-1.5 font-mono text-[10px] font-medium">
              ⌘K
            </kbd>
          </button>

          {/* Theme toggle */}
          <ThemeToggle />
        </nav>
      </header>

      <main className="flex-1 overflow-hidden">
        {mountedTabs.has('chat') && (
          <div className={activeTab === 'chat' ? 'h-full' : 'hidden'}>
            <ChatInterface />
          </div>
        )}
        {mountedTabs.has('pipelines') && (
          <div className={activeTab === 'pipelines' ? 'h-full' : 'hidden'}>
            <PipelinesInterface />
          </div>
        )}
        {mountedTabs.has('projects') && (
          <div className={activeTab === 'projects' ? 'h-full' : 'hidden'}>
            <ProjectsInterface />
          </div>
        )}
        {mountedTabs.has('workflows') && (
          <div className={activeTab === 'workflows' ? 'h-full' : 'hidden'}>
            <WorkflowsInterface />
          </div>
        )}
        {mountedTabs.has('calendar') && (
          <div className={activeTab === 'calendar' ? 'h-full' : 'hidden'}>
            <CalendarInterface />
          </div>
        )}
        {mountedTabs.has('profile') && (
          <div className={activeTab === 'profile' ? 'h-full' : 'hidden'}>
            <ProfileInterface />
          </div>
        )}
      </main>
    </div>
  )
}

export default App
