import { useEffect, useState, useCallback } from 'react'
import { Command } from 'cmdk'
import {
  MessageSquare,
  Database,
  FolderKanban,
  Workflow,
  Calendar,
  User,
  Search,
  Sun,
  Moon,
  Monitor,
  Plus,
  Mail,
  Hash,
  FileText,
  CalendarDays,
  CalendarRange,
  Clock,
  RefreshCw,
  Zap,
} from 'lucide-react'
import { useThemeStore } from '../../store/themeStore'

type Tab = 'chat' | 'pipelines' | 'projects' | 'workflows' | 'calendar' | 'profile'

interface CommandAction {
  id: string
  tab?: Tab
  action?: string
  data?: Record<string, unknown>
}

interface CommandMenuProps {
  onNavigate: (tab: Tab) => void
  onAction?: (action: CommandAction) => void
  activeTab: Tab
}

export default function CommandMenu({ onNavigate, onAction, activeTab }: CommandMenuProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const { theme, setTheme } = useThemeStore()

  // Toggle menu with Cmd+K or Ctrl+K
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
      if (e.key === 'Escape') {
        setOpen(false)
      }
    }

    document.addEventListener('keydown', down)
    return () => document.removeEventListener('keydown', down)
  }, [])

  const handleSelect = useCallback(
    (value: string) => {
      // Main navigation
      if (value.startsWith('nav-')) {
        const tab = value.replace('nav-', '') as Tab
        onNavigate(tab)
        setOpen(false)
        setSearch('')
        return
      }
      
      // Theme switching
      if (value.startsWith('theme-')) {
        const newTheme = value.replace('theme-', '') as 'light' | 'dark' | 'system'
        setTheme(newTheme)
        setOpen(false)
        setSearch('')
        return
      }

      // Pipeline subtabs
      if (value.startsWith('pipeline-')) {
        onNavigate('pipelines')
        const source = value.replace('pipeline-', '')
        onAction?.({ id: value, tab: 'pipelines', action: 'switch-source', data: { source } })
        setOpen(false)
        setSearch('')
        return
      }

      // Calendar views
      if (value.startsWith('calendar-')) {
        onNavigate('calendar')
        const view = value.replace('calendar-', '')
        onAction?.({ id: value, tab: 'calendar', action: 'switch-view', data: { view } })
        setOpen(false)
        setSearch('')
        return
      }

      // Quick actions
      if (value.startsWith('action-')) {
        const actionType = value.replace('action-', '')
        
        if (actionType === 'new-chat') {
          onNavigate('chat')
          onAction?.({ id: value, tab: 'chat', action: 'new-chat' })
        } else if (actionType === 'new-project') {
          onNavigate('projects')
          onAction?.({ id: value, tab: 'projects', action: 'new-project' })
        } else if (actionType === 'new-workflow') {
          onNavigate('workflows')
          onAction?.({ id: value, tab: 'workflows', action: 'new-workflow' })
        } else if (actionType === 'run-slack-pipeline') {
          onNavigate('pipelines')
          onAction?.({ id: value, tab: 'pipelines', action: 'run-pipeline', data: { source: 'slack' } })
        } else if (actionType === 'run-gmail-pipeline') {
          onNavigate('pipelines')
          onAction?.({ id: value, tab: 'pipelines', action: 'run-pipeline', data: { source: 'gmail' } })
        } else if (actionType === 'run-notion-pipeline') {
          onNavigate('pipelines')
          onAction?.({ id: value, tab: 'pipelines', action: 'run-pipeline', data: { source: 'notion' } })
        } else if (actionType === 'calendar-today') {
          onNavigate('calendar')
          onAction?.({ id: value, tab: 'calendar', action: 'go-today' })
        }
        
        setOpen(false)
        setSearch('')
        return
      }

      setSearch('')
    },
    [onNavigate, onAction, setTheme]
  )

  // Main navigation items
  const navItems = [
    { value: 'nav-chat', label: 'Chat', icon: MessageSquare, description: 'AI assistant chat', keywords: 'ai assistant conversation talk' },
    { value: 'nav-pipelines', label: 'Pipelines', icon: Database, description: 'Data sync pipelines', keywords: 'sync data import export slack gmail notion' },
    { value: 'nav-projects', label: 'Projects', icon: FolderKanban, description: 'Project management', keywords: 'manage organize folders' },
    { value: 'nav-workflows', label: 'Workflows', icon: Workflow, description: 'Automated workflows', keywords: 'automation schedule tasks' },
    { value: 'nav-calendar', label: 'Calendar', icon: Calendar, description: 'Calendar events', keywords: 'events meetings schedule' },
    { value: 'nav-profile', label: 'Profile', icon: User, description: 'User profile & settings', keywords: 'account settings preferences' },
  ]

  // Pipeline subtabs
  const pipelineItems = [
    { value: 'pipeline-slack', label: 'Slack Pipeline', icon: Hash, description: 'View & sync Slack data', keywords: 'slack messages channels' },
    { value: 'pipeline-gmail', label: 'Gmail Pipeline', icon: Mail, description: 'View & sync Gmail data', keywords: 'gmail email messages labels' },
    { value: 'pipeline-notion', label: 'Notion Pipeline', icon: FileText, description: 'View & sync Notion data', keywords: 'notion pages databases documents' },
  ]

  // Calendar views
  const calendarItems = [
    { value: 'calendar-day', label: 'Day View', icon: Clock, description: 'View today\'s events', keywords: 'today daily schedule' },
    { value: 'calendar-week', label: 'Week View', icon: CalendarDays, description: 'View this week', keywords: 'weekly schedule' },
    { value: 'calendar-month', label: 'Month View', icon: CalendarRange, description: 'View this month', keywords: 'monthly overview' },
  ]

  // Quick actions
  const actionItems = [
    { value: 'action-new-chat', label: 'New Chat', icon: Plus, description: 'Start a new conversation', keywords: 'create new chat conversation' },
    { value: 'action-new-project', label: 'New Project', icon: Plus, description: 'Create a new project', keywords: 'create new project' },
    { value: 'action-new-workflow', label: 'New Workflow', icon: Zap, description: 'Create a new workflow', keywords: 'create new workflow automation' },
    { value: 'action-run-slack-pipeline', label: 'Sync Slack', icon: RefreshCw, description: 'Run Slack pipeline', keywords: 'sync refresh slack data' },
    { value: 'action-run-gmail-pipeline', label: 'Sync Gmail', icon: RefreshCw, description: 'Run Gmail pipeline', keywords: 'sync refresh gmail email' },
    { value: 'action-run-notion-pipeline', label: 'Sync Notion', icon: RefreshCw, description: 'Run Notion pipeline', keywords: 'sync refresh notion pages' },
    { value: 'action-calendar-today', label: 'Go to Today', icon: Calendar, description: 'Jump to today in calendar', keywords: 'today now current' },
  ]

  // Theme items
  const themeItems = [
    { value: 'theme-light', label: 'Light Mode', icon: Sun, description: 'Switch to light theme', keywords: 'light bright white theme' },
    { value: 'theme-dark', label: 'Dark Mode', icon: Moon, description: 'Switch to dark theme', keywords: 'dark night black theme' },
    { value: 'theme-system', label: 'System Theme', icon: Monitor, description: 'Follow system preference', keywords: 'system auto automatic theme' },
  ]

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={() => setOpen(false)}
        aria-hidden="true"
      />

      {/* Command dialog */}
      <div className="absolute left-1/2 top-[15%] w-full max-w-xl -translate-x-1/2 px-4">
        <Command
          className="rounded-xl border border-border bg-popover text-popover-foreground shadow-2xl overflow-hidden"
          loop
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              setOpen(false)
            }
          }}
        >
          {/* Search input */}
          <div className="flex items-center border-b border-border px-4">
            <Search className="mr-2 h-4 w-4 shrink-0 text-muted-foreground" />
            <Command.Input
              value={search}
              onValueChange={setSearch}
              placeholder="Search pages, actions, or type a command..."
              className="flex h-12 w-full bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground"
              autoFocus
            />
            <kbd className="pointer-events-none ml-2 hidden h-5 select-none items-center gap-1 rounded border border-border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground sm:flex">
              ESC
            </kbd>
          </div>

          <Command.List className="max-h-[400px] overflow-y-auto p-2">
            <Command.Empty className="py-6 text-center text-sm text-muted-foreground">
              No results found.
            </Command.Empty>

            {/* Quick Actions */}
            <Command.Group heading="Quick Actions">
              {actionItems.map((item) => {
                const Icon = item.icon
                return (
                  <Command.Item
                    key={item.value}
                    value={`${item.value} ${item.label} ${item.keywords}`}
                    onSelect={() => handleSelect(item.value)}
                    className="relative flex cursor-pointer select-none items-center gap-3 rounded-lg px-3 py-2.5 text-sm outline-none aria-selected:bg-accent aria-selected:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/10">
                      <Icon className="h-4 w-4 text-primary" />
                    </div>
                    <div className="flex flex-col flex-1">
                      <span className="font-medium">{item.label}</span>
                      <span className="text-xs text-muted-foreground">{item.description}</span>
                    </div>
                  </Command.Item>
                )
              })}
            </Command.Group>

            {/* Navigation */}
            <Command.Group heading="Navigation">
              {navItems.map((item) => {
                const Icon = item.icon
                const isActive = item.value === `nav-${activeTab}`
                return (
                  <Command.Item
                    key={item.value}
                    value={`${item.value} ${item.label} ${item.keywords}`}
                    onSelect={() => handleSelect(item.value)}
                    className="relative flex cursor-pointer select-none items-center gap-3 rounded-lg px-3 py-2.5 text-sm outline-none aria-selected:bg-accent aria-selected:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted">
                      <Icon className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div className="flex flex-col flex-1">
                      <span className="font-medium">{item.label}</span>
                      <span className="text-xs text-muted-foreground">{item.description}</span>
                    </div>
                    {isActive && (
                      <span className="text-xs text-primary font-medium px-2 py-0.5 rounded bg-primary/10">Current</span>
                    )}
                  </Command.Item>
                )
              })}
            </Command.Group>

            {/* Pipeline Subtabs */}
            <Command.Group heading="Pipelines">
              {pipelineItems.map((item) => {
                const Icon = item.icon
                return (
                  <Command.Item
                    key={item.value}
                    value={`${item.value} ${item.label} ${item.keywords}`}
                    onSelect={() => handleSelect(item.value)}
                    className="relative flex cursor-pointer select-none items-center gap-3 rounded-lg px-3 py-2.5 text-sm outline-none aria-selected:bg-accent aria-selected:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted">
                      <Icon className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div className="flex flex-col flex-1">
                      <span className="font-medium">{item.label}</span>
                      <span className="text-xs text-muted-foreground">{item.description}</span>
                    </div>
                  </Command.Item>
                )
              })}
            </Command.Group>

            {/* Calendar Views */}
            <Command.Group heading="Calendar Views">
              {calendarItems.map((item) => {
                const Icon = item.icon
                return (
                  <Command.Item
                    key={item.value}
                    value={`${item.value} ${item.label} ${item.keywords}`}
                    onSelect={() => handleSelect(item.value)}
                    className="relative flex cursor-pointer select-none items-center gap-3 rounded-lg px-3 py-2.5 text-sm outline-none aria-selected:bg-accent aria-selected:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted">
                      <Icon className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div className="flex flex-col flex-1">
                      <span className="font-medium">{item.label}</span>
                      <span className="text-xs text-muted-foreground">{item.description}</span>
                    </div>
                  </Command.Item>
                )
              })}
            </Command.Group>

            {/* Theme */}
            <Command.Group heading="Appearance">
              {themeItems.map((item) => {
                const Icon = item.icon
                const isActive = item.value === `theme-${theme}`
                return (
                  <Command.Item
                    key={item.value}
                    value={`${item.value} ${item.label} ${item.keywords}`}
                    onSelect={() => handleSelect(item.value)}
                    className="relative flex cursor-pointer select-none items-center gap-3 rounded-lg px-3 py-2.5 text-sm outline-none aria-selected:bg-accent aria-selected:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted">
                      <Icon className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div className="flex flex-col flex-1">
                      <span className="font-medium">{item.label}</span>
                      <span className="text-xs text-muted-foreground">{item.description}</span>
                    </div>
                    {isActive && (
                      <span className="ml-auto flex h-5 w-5 items-center justify-center rounded-full bg-primary">
                        <span className="h-2 w-2 rounded-full bg-primary-foreground" />
                      </span>
                    )}
                  </Command.Item>
                )
              })}
            </Command.Group>
          </Command.List>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-border px-4 py-2 text-xs text-muted-foreground">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1">
                <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px]">↑</kbd>
                <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px]">↓</kbd>
                <span className="ml-1">Navigate</span>
              </div>
              <div className="flex items-center gap-1">
                <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px]">↵</kbd>
                <span className="ml-1">Select</span>
              </div>
              <div className="flex items-center gap-1">
                <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px]">esc</kbd>
                <span className="ml-1">Close</span>
              </div>
            </div>
          </div>
        </Command>
      </div>
    </div>
  )
}
