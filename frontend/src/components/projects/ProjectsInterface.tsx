import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../../lib/api'

interface ProjectSummary {
  id: string
  name: string
  description?: string | null
  status: string
  summary?: string | null
  main_goal?: string | null
  current_status_summary?: string | null
  important_notes?: string | null
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
    throw new Error(`Request failed: ${res.status}`)
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

  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const currentSync = selectedProject ? syncState[selectedProject.id] : undefined
  const lastSlackSync = currentSync?.slack ?? null
  const lastGmailSync = currentSync?.gmail ?? null
  const lastNotionSync = currentSync?.notion ?? null

  const slackSynced = lastSlackSync ? new Date(lastSlackSync).toLocaleString() : null
  const gmailSynced = lastGmailSync ? new Date(lastGmailSync).toLocaleString() : null
  const notionSynced = lastNotionSync ? new Date(lastNotionSync).toLocaleString() : null
  const hasSyncedAtLeastOnce = Boolean(lastSlackSync || lastGmailSync || lastNotionSync)

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
      // Reset chat state for the new project
      setChatMessages([])
    } catch (e: any) {
      setError(e.message || 'Failed to load project details')
    } finally {
      setLoading(false)
    }
  }

  const handleSyncData = async () => {
    if (!selectedProject) return
    setSyncing(true)
    try {
      const data = await fetchJSON<{
        project_id: string
        indexed_slack: number
        indexed_gmail: number
        indexed_notion: number
        last_synced: {
          slack: string | null
          gmail: string | null
          notion: string | null
        }
      }>(`${API_BASE_URL}/api/projects/${selectedProject.id}/sync`, {
        method: 'POST',
      })

      const ls = data.last_synced || ({} as any)
      setSyncState((prev) => ({
        ...prev,
        [selectedProject.id]: {
          slack: ls.slack || null,
          gmail: ls.gmail || null,
          notion: ls.notion || null,
        },
      }))

      await handleGenerateOverview()
    } catch (e: any) {
      alert(e.message || 'Failed to sync project data')
    } finally {
      setSyncing(false)
    }
  }

  const loadSlackChannels = async () => {
    try {
      const data = await fetchJSON<{ channels: SlackChannelOption[] }>(
        `${API_BASE_URL}/api/pipelines/slack/data`,
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

  useEffect(() => {
    loadProjects()
    loadSlackChannels()
    loadGmailLabels()
    loadNotionPages()
  }, [])

  useEffect(() => {
    if (selectedProjectId) {
      loadProjectDetail(selectedProjectId)
    } else {
      setSelectedProject(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId])

  const handleCreateProject = async () => {
    const name = prompt('Project name')
    if (!name) return
    try {
      const data = await fetchJSON<ProjectDetail>(`${API_BASE_URL}/api/projects`, {
        method: 'POST',
        body: JSON.stringify({ name }),
      })
      setProjects((prev) => [data, ...prev])
      setSelectedProjectId(data.id)
    } catch (e: any) {
      alert(e.message || 'Failed to create project')
    }
  }

  const handleGenerateOverview = async () => {
    if (!selectedProject) return
    try {
      const data = await fetchJSON<{
        short_description: string | null
        summary: string | null
        main_goal?: string | null
        current_status?: string | null
        important_notes?: string | null
        raw: string
      }>(`${API_BASE_URL}/api/projects/${selectedProject.id}/auto-summary`, {
        method: 'POST',
        body: JSON.stringify({ max_tokens: 256 }),
      })

      // Merge AI-generated fields into project and persist as the canonical report
      const updated: ProjectDetail = {
        ...selectedProject,
        description: data.short_description ?? selectedProject.description,
        summary: data.summary ?? selectedProject.summary,
        main_goal: data.main_goal ?? selectedProject.main_goal,
        current_status_summary:
          data.current_status ?? selectedProject.current_status_summary,
        important_notes: data.important_notes ?? selectedProject.important_notes,
      }

      const savedCore = await fetchJSON<ProjectSummary>(
        `${API_BASE_URL}/api/projects/${selectedProject.id}`,
        {
          method: 'PUT',
          body: JSON.stringify({
            name: updated.name,
            description: updated.description,
            status: updated.status,
            summary: updated.summary,
            main_goal: updated.main_goal,
            current_status_summary: updated.current_status_summary,
            important_notes: updated.important_notes,
          }),
        },
      )

      // The update_project API does not return linked sources, so preserve the
      // existing sources on the selected project while refreshing core fields
      // like description/summary and timestamps from the backend.
      const merged: ProjectDetail = {
        ...selectedProject,
        ...savedCore,
        sources: selectedProject.sources,
      }

      setSelectedProject(merged)
      setProjects((prev) => prev.map((p) => (p.id === merged.id ? merged : p)))
    } catch (e: any) {
      alert(e.message || 'Failed to generate overview from sources')
    }
  }

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
      alert(e.message || 'Failed to add source')
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
      alert(e.message || 'Failed to remove source')
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
                    className={`w-full text-left px-3 py-2 text-xs border-l-2 transition-colors ${{
                      true: 'border-blue-500 bg-muted/60',
                      false: 'border-transparent hover:bg-muted/40',
                    }[String(selectedProjectId === p.id)]}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-foreground truncate">{p.name}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">
                        {p.status || 'not_started'}
                      </span>
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
                  <h3 className="text-xs font-semibold text-foreground">Linked sources</h3>
                  <div className="flex items-center gap-2">
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
                      <select
                        className="text-[11px] rounded-md border border-border bg-background px-1.5 py-0.5 max-w-[180px]"
                        aria-label="Select Slack channel to link"
                        value={slackToAdd}
                        onChange={(e) => setSlackToAdd(e.target.value)}
                      >
                        <option value="">Select channel…</option>
                        {slackChannels.map((ch) => (
                          <option key={ch.channel_id} value={ch.channel_id}>
                            {ch.name || ch.channel_id}
                            {ch.is_private ? ' (private)' : ''}
                          </option>
                        ))}
                      </select>
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
                      <select
                        className="text-[11px] rounded-md border border-border bg-background px-1.5 py-0.5 max-w-[180px]"
                        aria-label="Select Gmail label to link"
                        value={gmailToAdd}
                        onChange={(e) => setGmailToAdd(e.target.value)}
                      >
                        <option value="">Select label…</option>
                        {gmailLabels.map((lbl) => (
                          <option key={lbl.id} value={lbl.id}>
                            {lbl.name}
                          </option>
                        ))}
                      </select>
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
                      <select
                        className="text-[11px] rounded-md border border-border bg-background px-1.5 py-0.5 max-w-[180px]"
                        aria-label="Select Notion page to link"
                        value={notionToAdd}
                        onChange={(e) => setNotionToAdd(e.target.value)}
                      >
                        <option value="">Select page…</option>
                        {notionPages.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.title}
                          </option>
                        ))}
                      </select>
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
                  <select
                    className="text-[11px] rounded-md border border-border bg-background px-1.5 py-0.5 capitalize"
                    aria-label="Project status"
                    value={selectedProject.status || 'not_started'}
                    onChange={(e) =>
                      setSelectedProject((prev) =>
                        prev ? { ...prev, status: e.target.value } : prev,
                      )
                    }
                  >
                    <option value="not_started">Not started</option>
                    <option value="in_progress">In progress</option>
                    <option value="blocked">Blocked</option>
                    <option value="completed">Completed</option>
                  </select>
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
                  <h3 className="text-xs font-semibold text-foreground">Project chat</h3>
                  <span className="text-[10px] text-muted-foreground">
                    Ask questions using only this project's Slack, Gmail, and Notion data.
                  </span>
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
