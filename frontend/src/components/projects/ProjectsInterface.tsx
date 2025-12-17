import { useEffect, useRef, useState } from 'react'
import { API_BASE_URL } from '../../lib/api'
import { SearchableSelect } from '../common/SearchableSelect'
import { Pencil, Trash2 } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

interface ProjectSummary {
  id: string
  name: string
  description?: string | null
  status: string
  summary?: string | null
  main_goal?: string | null
  current_status_summary?: string | null
  important_notes?: string | null
  last_project_sync_at?: string | null
  last_summary_generated_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

interface ProjectSourcesGrouped {
  slack_channels: ProjectSourceItem[]
  gmail_labels: ProjectSourceItem[]
  notion_pages: ProjectSourceItem[]
}

interface ProjectDetail extends ProjectSummary {
  sources: ProjectSourcesGrouped
}

interface ProjectSourceItem {
  source_type: string
  source_id: string
  display_name?: string | null
}

interface SlackChannelOption {
  channel_id: string
  name: string
  is_private?: boolean
  is_archived?: boolean
}

interface GmailLabelOption {
  id: string
  name: string
  type?: string
}

interface NotionPageOption {
  id: string
  title: string
  children?: NotionPageOption[]
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at?: string | null
  sources?: any[]
}

async function fetchJSON<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })
  if (!res.ok) {
    let detail = ''
    try {
      const text = await res.text()
      detail = text ? `: ${text.slice(0, 200)}` : ''
    } catch {
      // ignore
    }

    throw new Error(`Request failed: ${res.status}${detail}`)
  }
  return res.json() as Promise<T>
}

function flattenNotionPages(pages: NotionPageOption[]): NotionPageOption[] {
  const result: NotionPageOption[] = []
  const walk = (nodes: NotionPageOption[]) => {
    for (const node of nodes) {
      result.push({ id: node.id, title: node.title })
      if (node.children && node.children.length > 0) {
        walk(node.children)
      }
    }
  }
  walk(pages)
  return result
}

export default function ProjectsInterface() {
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [selectedProject, setSelectedProject] = useState<ProjectDetail | null>(null)

  const [slackChannels, setSlackChannels] = useState<SlackChannelOption[]>([])
  const [gmailLabels, setGmailLabels] = useState<GmailLabelOption[]>([])
  const [notionPages, setNotionPages] = useState<NotionPageOption[]>([])

  const [slackToAdd, setSlackToAdd] = useState<string>('')
  const [gmailToAdd, setGmailToAdd] = useState<string>('')
  const [notionToAdd, setNotionToAdd] = useState<string>('')

  const [syncState, setSyncState] = useState<
    Record<string, { slack: string | null; gmail: string | null; notion: string | null }>
  >({})

  const [syncing, setSyncing] = useState(false)

  const [projectSyncRunId, setProjectSyncRunId] = useState<string | null>(null)
  const [projectSyncStatus, setProjectSyncStatus] = useState<string | null>(null)
  const [projectSyncStage, setProjectSyncStage] = useState<string | null>(null)
  const [projectSyncProgress, setProjectSyncProgress] = useState<number | null>(null)

  const [projectSummaryRunId, setProjectSummaryRunId] = useState<string | null>(null)
  const [projectSummaryStatus, setProjectSummaryStatus] = useState<string | null>(null)
  const [projectSummaryStage, setProjectSummaryStage] = useState<string | null>(null)
  const [projectSummaryProgress, setProjectSummaryProgress] = useState<number | null>(null)

  const projectSyncRunIdRef = useRef<string | null>(null)
  const projectSummaryRunIdRef = useRef<string | null>(null)

  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [createProjectOpen, setCreateProjectOpen] = useState(false)
  const [createProjectName, setCreateProjectName] = useState('')

  const [renameProjectOpen, setRenameProjectOpen] = useState(false)
  const [renameProjectId, setRenameProjectId] = useState<string | null>(null)
  const [renameProjectName, setRenameProjectName] = useState('')
  const [deleteProjectTargetId, setDeleteProjectTargetId] = useState<string | null>(null)

  const flashError = (message: string) => {
    setError(message)
    window.setTimeout(() => setError(null), 6000)
  }

  const handleStartRenameProject = (project: ProjectSummary) => {
    setRenameProjectId(project.id)
    setRenameProjectName(project.name || '')
    setRenameProjectOpen(true)
  }

  const handleConfirmRenameProject = async () => {
    const projectId = renameProjectId
    const name = renameProjectName.trim()
    if (!projectId) return
    if (!name) {
      flashError('Project name is required')
      return
    }

    try {
      const updated = await fetchJSON<ProjectSummary>(`${API_BASE_URL}/api/projects/${projectId}`, {
        method: 'PUT',
        body: JSON.stringify({ name }),
      })

      setProjects((prev) => prev.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)))
      setSelectedProject((prev) => (prev && prev.id === updated.id ? { ...prev, name: updated.name } : prev))
      setRenameProjectOpen(false)
      setRenameProjectId(null)
    } catch (e: any) {
      flashError(e.message || 'Failed to rename project')
    }
  }

  const handleDeleteProject = async (projectId: string) => {
    try {
      await fetchJSON(`${API_BASE_URL}/api/projects/${projectId}`, { method: 'DELETE' })
      setProjects((prev) => {
        const next = prev.filter((p) => p.id !== projectId)
        if (selectedProjectId === projectId) {
          setSelectedProjectId(next.length > 0 ? next[0].id : null)
          setSelectedProject(null)
          setChatMessages([])
        }
        return next
      })
      setSyncState((prev) => {
        const next = { ...prev }
        delete next[projectId]
        return next
      })
    } catch (e: any) {
      flashError(e.message || 'Failed to delete project')
    }
  }

  const pollProjectSyncRun = async (runId: string) => {
    projectSyncRunIdRef.current = runId
    while (projectSyncRunIdRef.current === runId) {
      const run = await fetchJSON<any>(`${API_BASE_URL}/api/projects/sync/status/${runId}`)
      if (projectSyncRunIdRef.current !== runId) return run
      const stats = run.stats || {}
      setProjectSyncStatus(run.status || null)
      setProjectSyncStage(stats.stage || null)
      setProjectSyncProgress(typeof stats.progress === 'number' ? stats.progress : null)

      if (['completed', 'failed', 'cancelled'].includes(run.status)) {
        return run
      }
      await new Promise((resolve) => setTimeout(resolve, 2000))
    }
    return null
  }

  const pollProjectSummaryRun = async (runId: string) => {
    projectSummaryRunIdRef.current = runId
    while (projectSummaryRunIdRef.current === runId) {
      const run = await fetchJSON<any>(`${API_BASE_URL}/api/projects/auto-summary/status/${runId}`)
      if (projectSummaryRunIdRef.current !== runId) return run
      const stats = run.stats || {}
      setProjectSummaryStatus(run.status || null)
      setProjectSummaryStage(stats.stage || null)
      setProjectSummaryProgress(typeof stats.progress === 'number' ? stats.progress : null)

      if (['completed', 'failed', 'cancelled'].includes(run.status)) {
        return run
      }
      await new Promise((resolve) => setTimeout(resolve, 2000))
    }
    return null
  }

  const handleStopProjectSync = async () => {
    if (!projectSyncRunId) return
    try {
      setProjectSyncStatus('cancelling')
      await fetchJSON(`${API_BASE_URL}/api/projects/sync/stop/${projectSyncRunId}`, {
        method: 'POST',
      })
    } catch (e: any) {
      flashError(e.message || 'Failed to stop sync')
    }
  }

  const handleStopProjectSummary = async () => {
    if (!projectSummaryRunId) return
    try {
      setProjectSummaryStatus('cancelling')
      await fetchJSON(`${API_BASE_URL}/api/projects/auto-summary/stop/${projectSummaryRunId}`, {
        method: 'POST',
      })
    } catch (e: any) {
      flashError(e.message || 'Failed to stop summary generation')
    }
  }

  const currentSync = selectedProject ? syncState[selectedProject.id] : undefined
  const lastSlackSync = currentSync?.slack ?? null
  const lastGmailSync = currentSync?.gmail ?? null
  const lastNotionSync = currentSync?.notion ?? null

  const slackSynced = lastSlackSync ? new Date(lastSlackSync).toLocaleString() : null
  const gmailSynced = lastGmailSync ? new Date(lastGmailSync).toLocaleString() : null
  const notionSynced = lastNotionSync ? new Date(lastNotionSync).toLocaleString() : null
  const hasSyncedAtLeastOnce = Boolean(
    lastSlackSync ||
      lastGmailSync ||
      lastNotionSync ||
      selectedProject?.last_project_sync_at,
  )

  const syncProgressText = projectSyncProgress != null ? `${(projectSyncProgress * 100).toFixed(0)}%` : null
  const summaryProgressText = projectSummaryProgress != null ? `${(projectSummaryProgress * 100).toFixed(0)}%` : null

  const loadProjects = async () => {
    try {
      setLoading(true)
      const data = await fetchJSON<{ projects: ProjectSummary[] }>(
        `${API_BASE_URL}/api/projects`,
      )
      setProjects(data.projects || [])
      if (!selectedProjectId && data.projects.length > 0) {
        setSelectedProjectId(data.projects[0].id)
      }
    } catch (e: any) {
      setError(e.message || 'Failed to load projects')
    } finally {
      setLoading(false)
    }
  }

  const loadProjectDetail = async (projectId: string) => {
    try {
      setLoading(true)
      const data = await fetchJSON<ProjectDetail>(
        `${API_BASE_URL}/api/projects/${projectId}`,
      )
      setSelectedProject(data)
      // Chat history is loaded separately (DB-backed per project)
    } catch (e: any) {
      setError(e.message || 'Failed to load project details')
    } finally {
      setLoading(false)
    }
  }

  const loadProjectChatHistory = async (projectId: string) => {
    try {
      const data = await fetchJSON<{ messages: Array<{ role: string; content: string; created_at?: string | null; sources?: any[] }> }>(
        `${API_BASE_URL}/api/projects/${projectId}/chat/history?limit=200`,
      )
      const msgs: ChatMessage[] = (data.messages || []).map((m, idx) => ({
        id: `${projectId}-${m.created_at || idx}`,
        role: (m.role as any) || 'assistant',
        content: m.content,
        created_at: m.created_at ?? null,
        sources: (m as any).sources || [],
      }))
      setChatMessages(msgs)
    } catch (e) {
      console.error('Failed to load project chat history', e)
      setChatMessages([])
    }
  }

  const handleClearProjectChat = async () => {
    if (!selectedProject) return
    try {
      await fetchJSON(`${API_BASE_URL}/api/projects/${selectedProject.id}/chat/history`, {
        method: 'DELETE',
      })
      setChatMessages([])
    } catch (e: any) {
      flashError(e.message || 'Failed to clear chat history')
    }
  }

  const refreshSelectedProject = async (projectId: string) => {
    try {
      const data = await fetchJSON<ProjectDetail>(`${API_BASE_URL}/api/projects/${projectId}`)
      setSelectedProject(data)
      setProjects((prev) => prev.map((p) => (p.id === projectId ? { ...p, ...data } : p)))
    } catch (e) {
      console.error('Failed to refresh project detail', e)
    }
  }

  const handleSyncData = async () => {
    if (!selectedProject) return
    setSyncing(true)
    try {
      setProjectSyncRunId(null)
      setProjectSyncStatus(null)
      setProjectSyncStage(null)
      setProjectSyncProgress(null)

      const started = await fetchJSON<{ run_id: string }>(
        `${API_BASE_URL}/api/projects/${selectedProject.id}/sync/run`,
        { method: 'POST' },
      )
      setProjectSyncRunId(started.run_id)

      const finalRun = await pollProjectSyncRun(started.run_id)
      const finalStats = finalRun?.stats || {}
      const ls = finalStats.last_synced || ({} as any)
      setSyncState((prev) => ({
        ...prev,
        [selectedProject.id]: {
          slack: ls.slack || null,
          gmail: ls.gmail || null,
          notion: ls.notion || null,
        },
      }))

      if (finalRun?.status === 'completed') {
        await refreshSelectedProject(selectedProject.id)
        await handleGenerateOverview()
      }
    } catch (e: any) {
      flashError(e.message || 'Failed to sync project data')
    } finally {
      setSyncing(false)
    }
  }

  const loadSlackChannels = async () => {
    try {
      const data = await fetchJSON<{ channels: SlackChannelOption[] }>(
        `${API_BASE_URL}/api/pipelines/slack/channels/options`,
      )
      setSlackChannels(data.channels || [])
    } catch (e) {
      console.error('Failed to load Slack channels', e)
    }
  }

  const loadGmailLabels = async () => {
    try {
      const data = await fetchJSON<{ labels: GmailLabelOption[] }>(
        `${API_BASE_URL}/api/pipelines/gmail/labels`,
      )
      setGmailLabels(data.labels || [])
    } catch (e) {
      console.error('Failed to load Gmail labels', e)
    }
  }

  const loadNotionPages = async () => {
    try {
      const data = await fetchJSON<{ workspace_name: string; pages: NotionPageOption[] }>(
        `${API_BASE_URL}/api/notion/hierarchy`,
      )
      setNotionPages(flattenNotionPages(data.pages || []))
    } catch (e) {
      console.error('Failed to load Notion pages', e)
    }
  }

  // Track which source options have been loaded
  const [sourcesLoaded, setSourcesLoaded] = useState(false)

  useEffect(() => {
    // Only load project list initially - source options are loaded on-demand
    loadProjects()
  }, [])

  // Load source options only when a project is selected (user might add sources)
  useEffect(() => {
    if (!selectedProjectId || sourcesLoaded) return
    // Load source options in background after project is selected
    Promise.all([loadSlackChannels(), loadGmailLabels(), loadNotionPages()]).then(() => {
      setSourcesLoaded(true)
    })
  }, [selectedProjectId, sourcesLoaded])

  useEffect(() => {
    if (selectedProjectId) {
      loadProjectDetail(selectedProjectId)
    } else {
      setSelectedProject(null)
    }
  }, [selectedProjectId])

  useEffect(() => {
    if (!selectedProjectId) return
    loadProjectChatHistory(selectedProjectId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId])

  const handleCreateProject = async () => {
    setCreateProjectName('')
    setCreateProjectOpen(true)
  }

  const handleConfirmCreateProject = async () => {
    const name = createProjectName.trim()
    if (!name) {
      flashError('Project name is required')
      return
    }
    try {
      const data = await fetchJSON<ProjectDetail>(`${API_BASE_URL}/api/projects`, {
        method: 'POST',
        body: JSON.stringify({ name }),
      })
      setProjects((prev) => [data, ...prev])
      setSelectedProjectId(data.id)
      setCreateProjectOpen(false)
    } catch (e: any) {
      flashError(e.message || 'Failed to create project')
    }
  }

  const handleGenerateOverview = async () => {
    if (!selectedProject) return
    try {
      setProjectSummaryRunId(null)
      setProjectSummaryStatus(null)
      setProjectSummaryStage(null)
      setProjectSummaryProgress(null)

      const started = await fetchJSON<{ run_id: string }>(
        `${API_BASE_URL}/api/projects/${selectedProject.id}/auto-summary/run`,
        {
          method: 'POST',
          body: JSON.stringify({ max_tokens: 256 }),
        },
      )
      setProjectSummaryRunId(started.run_id)

      const finalRun = await pollProjectSummaryRun(started.run_id)
      if (finalRun?.status === 'completed') {
        await refreshSelectedProject(selectedProject.id)
      }
    } catch (e: any) {
      flashError(e.message || 'Failed to generate overview from sources')
    }
  }

  useEffect(() => {
    projectSyncRunIdRef.current = projectSyncRunId
  }, [projectSyncRunId])

  useEffect(() => {
    projectSummaryRunIdRef.current = projectSummaryRunId
  }, [projectSummaryRunId])

  useEffect(() => {
    projectSyncRunIdRef.current = null
    projectSummaryRunIdRef.current = null
    setProjectSyncRunId(null)
    setProjectSyncStatus(null)
    setProjectSyncStage(null)
    setProjectSyncProgress(null)
    setProjectSummaryRunId(null)
    setProjectSummaryStatus(null)
    setProjectSummaryStage(null)
    setProjectSummaryProgress(null)
    setSyncing(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId])

  const handleAddSource = async (
    sourceType: 'slack_channel' | 'gmail_label' | 'notion_page',
    sourceId: string,
    displayName?: string,
  ) => {
    if (!selectedProject || !sourceId) return
    try {
      const payload = [
        {
          source_type: sourceType,
          source_id: sourceId,
          display_name: displayName,
        },
      ]
      await fetchJSON<{ sources: any[] }>(
        `${API_BASE_URL}/api/projects/${selectedProject.id}/sources`,
        {
          method: 'POST',
          body: JSON.stringify(payload),
        },
      )
      // Reload project detail to reflect sources
      await loadProjectDetail(selectedProject.id)
      if (sourceType === 'slack_channel') setSlackToAdd('')
      if (sourceType === 'gmail_label') setGmailToAdd('')
      if (sourceType === 'notion_page') setNotionToAdd('')
    } catch (e: any) {
      flashError(e.message || 'Failed to add source')
    }
  }

  const handleRemoveSource = async (
    sourceType: 'slack_channel' | 'gmail_label' | 'notion_page',
    sourceId: string,
  ) => {
    if (!selectedProject) return
    try {
      await fetchJSON(
        `${API_BASE_URL}/api/projects/${selectedProject.id}/sources/${sourceType}/${encodeURIComponent(
          sourceId,
        )}`,
        {
          method: 'DELETE',
        },
      )
      await loadProjectDetail(selectedProject.id)
    } catch (e: any) {
      flashError(e.message || 'Failed to remove source')
    }
  }

  const handleSendChat = async () => {
    // Require at least one successful sync before allowing project chat.
    if (!selectedProject || !chatInput.trim() || !hasSyncedAtLeastOnce || syncing) return
    const query = chatInput.trim()
    const newUserMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: query,
    }
    setChatMessages((prev) => [...prev, newUserMessage])
    setChatInput('')
    setChatLoading(true)

    try {
      const historyPayload = chatMessages
        .concat(newUserMessage)
        .slice(-20)
        .map((m) => ({ role: m.role, content: m.content }))

      const data = await fetchJSON<{
        response: string
        sources: any[]
        intent?: string
      }>(
        `${API_BASE_URL}/api/chat/project/${selectedProject.id}`,
        {
          method: 'POST',
          body: JSON.stringify({ query, conversation_history: historyPayload }),
        },
      )

      const assistantMessage: ChatMessage = {
        id: `${Date.now()}-assistant`,
        role: 'assistant',
        content: data.response,
        sources: data.sources || [],
      }
      setChatMessages((prev) => [...prev, assistantMessage])
    } catch (e: any) {
      console.error('Project chat failed', e)
      const errorMessage: ChatMessage = {
        id: `${Date.now()}-error`,
        role: 'assistant',
        content: e.message || 'Project chat failed',
      }
      setChatMessages((prev) => [...prev, errorMessage])
    } finally {
      setChatLoading(false)
    }
  }

  return (
    <div className="flex h-full bg-background">
      <AlertDialog
        open={deleteProjectTargetId !== null}
        onOpenChange={(open: boolean) => !open && setDeleteProjectTargetId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete project?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the project and its linked sources.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setDeleteProjectTargetId(null)}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 hover:bg-red-700"
              onClick={async () => {
                if (!deleteProjectTargetId) return
                const id = deleteProjectTargetId
                setDeleteProjectTargetId(null)
                await handleDeleteProject(id)
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={createProjectOpen} onOpenChange={setCreateProjectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create project</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="create-project-name">
              Project name
            </label>
            <input
              id="create-project-name"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              value={createProjectName}
              onChange={(e) => setCreateProjectName(e.target.value)}
              placeholder="e.g. Growth Q1"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setCreateProjectOpen(false)}>
              Cancel
            </Button>
            <Button type="button" onClick={handleConfirmCreateProject}>
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={renameProjectOpen} onOpenChange={setRenameProjectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename project</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="rename-project-name">
              Project name
            </label>
            <input
              id="rename-project-name"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              value={renameProjectName}
              onChange={(e) => setRenameProjectName(e.target.value)}
              placeholder="Project name"
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setRenameProjectOpen(false)
                setRenameProjectId(null)
              }}
            >
              Cancel
            </Button>
            <Button type="button" onClick={handleConfirmRenameProject}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Sidebar: project list */}
      <aside className="w-64 border-r border-border bg-card flex flex-col">
        <div className="p-3 border-b border-border flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">Projects</h2>
          <button
            type="button"
            onClick={handleCreateProject}
            className="text-xs rounded-md px-2 py-1 bg-blue-600 text-white hover:bg-blue-700"
          >
            New
          </button>
        </div>
        <div className="flex-1 overflow-auto">
          {loading && projects.length === 0 ? (
            <p className="p-3 text-xs text-muted-foreground">Loading projects…</p>
          ) : projects.length === 0 ? (
            <p className="p-3 text-xs text-muted-foreground">
              No projects yet. Create one to start tracking Slack, Gmail, and Notion data.
            </p>
          ) : (
            <ul className="py-2">
              {projects.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedProjectId(p.id)}
                    className={`group relative w-full text-left px-3 py-2 text-xs border-l-2 transition-colors ${{
                      true: 'border-blue-500 bg-muted/60',
                      false: 'border-transparent hover:bg-muted/40',
                    }[String(selectedProjectId === p.id)]}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-foreground truncate">{p.name}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">
                          {p.status || 'not_started'}
                        </span>
                        <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleStartRenameProject(p)
                            }}
                            className="hover:text-blue-600"
                            title="Rename project"
                            aria-label="Rename project"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              setDeleteProjectTargetId(p.id)
                            }}
                            className="hover:text-red-600"
                            title="Delete project"
                            aria-label="Delete project"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </div>
                    </div>
                    {p.summary && (
                      <p className="mt-0.5 text-[10px] text-muted-foreground line-clamp-2">
                        {p.summary}
                      </p>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {error && (
          <div className="p-2 text-[11px] text-red-400 border-t border-red-500/40 bg-red-950/60">
            {error}
          </div>
        )}
      </aside>

      {/* Main: project detail */}
      <section className="flex-1 flex flex-col overflow-hidden">
        {!selectedProject ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-xs text-muted-foreground">
              Select a project or create a new one to see details.
            </p>
          </div>
        ) : (
          <div className="flex-1 grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-4 p-4 overflow-hidden">
            {/* Left column: sources + overview */}
            <div className="flex flex-col gap-4 overflow-hidden">
              {/* Sources card */}
              <div className="border border-border rounded-md bg-card p-3 text-xs flex flex-col gap-2 overflow-hidden">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div className="flex items-center gap-2">
                    <h3 className="text-xs font-semibold text-foreground">Linked sources</h3>
                    {(projectSyncRunId || projectSyncStatus) && (
                      <span className="text-[10px] text-muted-foreground">
                        Sync: {projectSyncStatus || 'running'}
                        {projectSyncStage ? ` · ${projectSyncStage}` : ''}
                        {syncProgressText ? ` · ${syncProgressText}` : ''}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {projectSyncRunId && syncing && (
                      <button
                        type="button"
                        onClick={handleStopProjectSync}
                        className="text-[11px] px-2 py-0.5 rounded-md bg-red-600 text-white hover:bg-red-700"
                      >
                        Stop
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={handleSyncData}
                      disabled={syncing || !selectedProject}
                      className="text-[11px] px-2 py-0.5 rounded-md border border-border bg-background text-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {syncing ? 'Syncing…' : 'Sync data'}
                    </button>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-0.5 text-[10px] text-muted-foreground mb-1">
                  {selectedProject.last_project_sync_at && (
                    <span>
                      Project sync:{' '}
                      {new Date(selectedProject.last_project_sync_at).toLocaleString()}
                    </span>
                  )}
                  {selectedProject.last_summary_generated_at && (
                    <span>
                      Overview:{' '}
                      {new Date(selectedProject.last_summary_generated_at).toLocaleString()}
                    </span>
                  )}
                  <span>
                    Slack: {selectedProject.sources.slack_channels.length}
                    {slackSynced && <> · Last synced {slackSynced}</>}
                  </span>
                  <span>
                    Gmail: {selectedProject.sources.gmail_labels.length}
                    {gmailSynced && <> · Last synced {gmailSynced}</>}
                  </span>
                  <span>
                    Notion: {selectedProject.sources.notion_pages.length}
                    {notionSynced && <> · Last synced {notionSynced}</>}
                  </span>
                </div>

                {/* Slack */}
                <div>
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="text-[11px] font-semibold text-foreground">Slack channels</span>
                    <div className="flex items-center gap-1">
                      <SearchableSelect
                        value={slackToAdd}
                        onChange={setSlackToAdd}
                        options={slackChannels.map((ch) => ({
                          value: ch.channel_id,
                          label: `${ch.name || ch.channel_id}${ch.is_private ? ' (private)' : ''}`,
                        }))}
                        placeholder="Select channel…"
                        searchPlaceholder="Search channels…"
                        allowClear
                        containerClassName="w-[180px]"
                        fullWidth
                        triggerClassName="text-[11px]"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const ch = slackChannels.find((c) => c.channel_id === slackToAdd)
                          if (ch) {
                            handleAddSource('slack_channel', ch.channel_id, ch.name)
                          }
                        }}
                        className="text-[11px] px-2 py-0.5 rounded-md bg-blue-600 text-white hover:bg-blue-700"
                      >
                        Add
                      </button>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {selectedProject.sources.slack_channels.length === 0 && (
                      <span className="text-[10px] text-muted-foreground">No Slack channels linked.</span>
                    )}
                    {selectedProject.sources.slack_channels.map((s) => (
                      <button
                        key={s.source_id}
                        type="button"
                        onClick={() => handleRemoveSource('slack_channel', s.source_id)}
                        className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground hover:bg-red-900/40 hover:text-red-200"
                      >
                        <span>{s.display_name || s.source_id}</span>
                        <span>×</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Gmail */}
                <div>
                  <div className="flex items-center justify-between gap-2 mb-1 mt-2">
                    <span className="text-[11px] font-semibold text-foreground">Gmail labels</span>
                    <div className="flex items-center gap-1">
                      <SearchableSelect
                        value={gmailToAdd}
                        onChange={setGmailToAdd}
                        options={gmailLabels.map((lbl) => ({ value: lbl.id, label: lbl.name }))}
                        placeholder="Select label…"
                        searchPlaceholder="Search labels…"
                        allowClear
                        containerClassName="w-[180px]"
                        fullWidth
                        triggerClassName="text-[11px]"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const lbl = gmailLabels.find((l) => l.id === gmailToAdd)
                          if (lbl) {
                            handleAddSource('gmail_label', lbl.id, lbl.name)
                          }
                        }}
                        className="text-[11px] px-2 py-0.5 rounded-md bg-blue-600 text-white hover:bg-blue-700"
                      >
                        Add
                      </button>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {selectedProject.sources.gmail_labels.length === 0 && (
                      <span className="text-[10px] text-muted-foreground">No Gmail labels linked.</span>
                    )}
                    {selectedProject.sources.gmail_labels.map((s) => (
                      <button
                        key={s.source_id}
                        type="button"
                        onClick={() => handleRemoveSource('gmail_label', s.source_id)}
                        className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground hover:bg-red-900/40 hover:text-red-200"
                      >
                        <span>{s.display_name || s.source_id}</span>
                        <span>×</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Notion */}
                <div>
                  <div className="flex items-center justify-between gap-2 mb-1 mt-2">
                    <span className="text-[11px] font-semibold text-foreground">Notion pages</span>
                    <div className="flex items-center gap-1">
                      <SearchableSelect
                        value={notionToAdd}
                        onChange={setNotionToAdd}
                        options={notionPages.map((p) => ({ value: p.id, label: p.title }))}
                        placeholder="Select page…"
                        searchPlaceholder="Search pages…"
                        allowClear
                        containerClassName="w-[180px]"
                        fullWidth
                        triggerClassName="text-[11px]"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const page = notionPages.find((p) => p.id === notionToAdd)
                          if (page) {
                            handleAddSource('notion_page', page.id, page.title)
                          }
                        }}
                        className="text-[11px] px-2 py-0.5 rounded-md bg-blue-600 text-white hover:bg-blue-700"
                      >
                        Add
                      </button>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {selectedProject.sources.notion_pages.length === 0 && (
                      <span className="text-[10px] text-muted-foreground">No Notion pages linked.</span>
                    )}
                    {selectedProject.sources.notion_pages.map((s) => (
                      <button
                        key={s.source_id}
                        type="button"
                        onClick={() => handleRemoveSource('notion_page', s.source_id)}
                        className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground hover:bg-red-900/40 hover:text-red-200"
                      >
                        <span>{s.display_name || s.source_id}</span>
                        <span>×</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Overview card */}
              <div className="border border-border rounded-md bg-card p-3 text-xs flex flex-col gap-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex flex-col">
                    <input
                      className="bg-transparent border-none text-sm font-semibold text-foreground focus:outline-none focus:ring-0"
                      aria-label="Project name"
                      placeholder="Project name"
                      value={selectedProject.name}
                      onChange={(e) =>
                        setSelectedProject((prev) =>
                          prev ? { ...prev, name: e.target.value } : prev,
                        )
                      }
                    />
                    <input
                      className="bg-transparent border-none text-[11px] text-muted-foreground focus:outline-none focus:ring-0"
                      placeholder="Short description"
                      value={selectedProject.description || ''}
                      onChange={(e) =>
                        setSelectedProject((prev) =>
                          prev ? { ...prev, description: e.target.value } : prev,
                        )
                      }
                    />
                  </div>
                  <SearchableSelect
                    value={selectedProject.status || 'not_started'}
                    onChange={(next) =>
                      setSelectedProject((prev) => (prev ? { ...prev, status: next } : prev))
                    }
                    options={[
                      { value: 'not_started', label: 'Not started' },
                      { value: 'in_progress', label: 'In progress' },
                      { value: 'blocked', label: 'Blocked' },
                      { value: 'completed', label: 'Completed' },
                    ]}
                    searchPlaceholder="Search status…"
                    containerClassName="w-[160px]"
                    fullWidth
                    triggerClassName="text-[11px] capitalize"
                  />
                </div>

                <div className="flex items-center justify-between gap-2">
                  <div className="text-[10px] text-muted-foreground">
                    {(projectSummaryRunId || projectSummaryStatus) && (
                      <>
                        Overview: {projectSummaryStatus || 'running'}
                        {projectSummaryStage ? ` · ${projectSummaryStage}` : ''}
                        {summaryProgressText ? ` · ${summaryProgressText}` : ''}
                      </>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {projectSummaryRunId && projectSummaryStatus && ['pending', 'running', 'cancelling'].includes(projectSummaryStatus) && (
                      <button
                        type="button"
                        onClick={handleStopProjectSummary}
                        className="text-[11px] px-2 py-0.5 rounded-md bg-red-600 text-white hover:bg-red-700"
                      >
                        Stop
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={handleGenerateOverview}
                      disabled={!hasSyncedAtLeastOnce || Boolean(projectSummaryRunId && projectSummaryStatus && ['pending', 'running', 'cancelling'].includes(projectSummaryStatus))}
                      className="text-[11px] px-2 py-0.5 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                    >
                      Generate overview
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-2 mt-1">
                  <div>
                    <label className="block text-[10px] font-semibold text-muted-foreground mb-0.5">
                      Summary
                    </label>
                    <textarea
                      className="w-full min-h-[60px] rounded-md border border-border bg-background px-2 py-1 text-xs"
                      placeholder="High-level summary of this project"
                      value={selectedProject.summary || ''}
                      readOnly
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[10px] font-semibold text-muted-foreground mb-0.5">
                        Main goal
                      </label>
                      <textarea
                        className="w-full min-h-[40px] rounded-md border border-border bg-background px-2 py-1 text-xs"
                        placeholder="What is the main goal of this project?"
                        value={selectedProject.main_goal || ''}
                        readOnly
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] font-semibold text-muted-foreground mb-0.5">
                        Current status
                      </label>
                      <textarea
                        className="w-full min-h-[40px] rounded-md border border-border bg-background px-2 py-1 text-xs"
                        placeholder="Briefly describe the current status"
                        value={selectedProject.current_status_summary || ''}
                        readOnly
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold text-muted-foreground mb-0.5">
                      Important notes
                    </label>
                    <textarea
                      className="w-full min-h-[40px] rounded-md border border-border bg-background px-2 py-1 text-xs"
                      placeholder="Important things to remember (risks, dependencies, decisions)"
                      value={selectedProject.important_notes || ''}
                      onChange={(e) =>
                        setSelectedProject((prev) =>
                          prev
                            ? { ...prev, important_notes: e.target.value }
                            : prev,
                        )
                      }
                    />
                  </div>
                </div>

                <div className="mt-2 flex items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                    {selectedProject.created_at && (
                      <span>
                        Created:{' '}
                        {new Date(selectedProject.created_at).toLocaleString()}
                      </span>
                    )}
                    {selectedProject.updated_at && (
                      <span>
                        Updated:{' '}
                        {new Date(selectedProject.updated_at).toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Right column: project chat only */}
            <div className="flex flex-col gap-4 overflow-hidden">
              {/* Project chat */}
              <div className="border border-border rounded-md bg-card p-3 text-xs flex flex-col h-full min-h-[220px]">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <h3 className="text-xs font-semibold text-foreground">Project chat</h3>
                    <span className="text-[10px] text-muted-foreground">
                      Ask questions using only this project's Slack, Gmail, and Notion data.
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={handleClearProjectChat}
                    disabled={chatLoading}
                    className="text-[11px] px-2 py-1 rounded-md border border-border bg-background text-foreground hover:bg-muted disabled:opacity-60"
                  >
                    Clear chat
                  </button>
                </div>
                <div className="flex-1 overflow-auto border border-border rounded-md bg-background/40 p-2 mb-2">
                  {syncing ? (
                    <p className="text-[11px] text-muted-foreground">
                      Processing project data from linked Slack, Gmail, and Notion sources…
                      Chat will be available once sync completes.
                    </p>
                  ) : !hasSyncedAtLeastOnce ? (
                    <p className="text-[11px] text-muted-foreground">
                      Run <span className="font-semibold">Sync data</span> in the Linked sources
                      panel to prepare this project's workspace. Once sync is complete, you can
                      chat with the project-specific data here.
                    </p>
                  ) : chatMessages.length === 0 ? (
                    <p className="text-[11px] text-muted-foreground">
                      Start a conversation about this project. For example: "Summarize the latest
                      updates".
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {chatMessages.map((m) => (
                        <div key={m.id} className="flex flex-col">
                          <span
                            className={`text-[10px] font-semibold mb-0.5 ${
                              m.role === 'user' ? 'text-blue-300' : 'text-green-300'
                            }`}
                          >
                            {m.role === 'user' ? 'You' : 'Assistant'}
                          </span>
                          <div className="rounded-md bg-background px-2 py-1 text-[11px] text-foreground whitespace-pre-wrap">
                            {m.content}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <input
                    className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-xs"
                    placeholder="Ask about this project's status, updates, tasks…"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        handleSendChat()
                      }
                    }}
                    disabled={chatLoading || syncing || !hasSyncedAtLeastOnce}
                  />
                  <button
                    type="button"
                    onClick={handleSendChat}
                    disabled={
                      chatLoading ||
                      syncing ||
                      !hasSyncedAtLeastOnce ||
                      !chatInput.trim()
                    }
                    className="text-[11px] px-2 py-1 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                  >
                    {chatLoading ? 'Sending…' : 'Send'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
