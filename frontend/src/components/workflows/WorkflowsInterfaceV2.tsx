import { useEffect, useState, useCallback } from 'react'
import { API_BASE_URL } from '../../lib/api'
import { 
  Plus, Play, Pencil, Trash2, ChevronRight, 
  Database, Brain, Send, Clock, Check, X, 
  AlertCircle, Settings, History, Square
} from 'lucide-react'
import { SearchableSelect, type SearchableSelectOption } from '../common/SearchableSelect'
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

// Types
interface SourceConfig {
  sources: Array<{
    type: 'slack' | 'gmail' | 'notion'
    channels?: string[]
    labels?: string[]
    pages?: string[]
    time_range: string
    limit?: number
  }>
}

interface PromptConfig {
  system_prompt: string
  user_instructions: string
  output_format: string
}

interface OutputConfig {
  outputs: Array<{
    type: 'notion_page' | 'slack_message' | 'gmail_draft' | 'display'
    page_id?: string
    channel?: string
    to?: string
    subject?: string
    mode?: 'append' | 'replace'
    title?: string
    output_prompt?: string  // Additional instructions for how AI should handle this output
  }>
}

interface UserWorkflow {
  id: string
  name: string
  description?: string
  source_config: SourceConfig
  prompt_config: PromptConfig
  output_config: OutputConfig
  schedule_type: string
  schedule_config: Record<string, unknown>
  status: string
  last_run_at?: string
  next_run_at?: string
  created_at?: string
  updated_at?: string
}

interface WorkflowRun {
  id: string
  workflow_id: string
  status: string
  started_at?: string
  completed_at?: string
  source_items_count: number
  source_data_preview?: string
  ai_response?: string
  output_result?: Record<string, unknown>
  error_message?: string
  current_step?: string
  progress_percent: number
  logs: Array<{ timestamp: string; level: string; message: string }>
  created_at?: string
}

interface SlackChannel {
  id: string
  name: string
  is_private: boolean
}

interface GmailLabel {
  id: string
  name: string
  type: string
}

interface NotionPage {
  id: string
  title: string
  object_type?: string
}

const TIME_RANGE_OPTIONS = [
  { value: 'last_1h', label: 'Last 1 hour' },
  { value: 'last_24h', label: 'Last 24 hours' },
  { value: 'last_7d', label: 'Last 7 days' },
  { value: 'last_30d', label: 'Last 30 days' },
  { value: 'since_last_run', label: 'Since last run' },
  { value: 'all', label: 'All time' },
]

const OUTPUT_FORMAT_OPTIONS = [
  { value: 'markdown', label: 'Markdown' },
  { value: 'plain_text', label: 'Plain Text' },
  { value: 'bullet_points', label: 'Bullet Points' },
  { value: 'json', label: 'JSON' },
]

const SCHEDULE_TYPE_OPTIONS = [
  { value: 'manual', label: 'Manual only' },
  { value: 'interval', label: 'Run on interval' },
]

const INTERVAL_OPTIONS = [
  { value: 1800, label: 'Every 30 minutes' },
  { value: 3600, label: 'Every hour' },
  { value: 10800, label: 'Every 3 hours' },
  { value: 21600, label: 'Every 6 hours' },
  { value: 43200, label: 'Every 12 hours' },
  { value: 86400, label: 'Every 24 hours' },
]

export default function WorkflowsInterfaceV2() {
  // Workflow list state
  const [workflows, setWorkflows] = useState<UserWorkflow[]>([])
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Source options (for dropdowns)
  const [slackChannels, setSlackChannels] = useState<SlackChannel[]>([])
  const [gmailLabels, setGmailLabels] = useState<GmailLabel[]>([])
  const [notionPages, setNotionPages] = useState<NotionPage[]>([])

  // Dialogs
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [renameDialogOpen, setRenameDialogOpen] = useState(false)
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null)
  const [sourceEditorOpen, setSourceEditorOpen] = useState(false)
  const [promptEditorOpen, setPromptEditorOpen] = useState(false)
  const [outputEditorOpen, setOutputEditorOpen] = useState(false)

  // Form state
  const [newWorkflowName, setNewWorkflowName] = useState('')
  const [renameWorkflowName, setRenameWorkflowName] = useState('')

  // Run state
  const [runLoading, setRunLoading] = useState(false)
  const [currentRun, setCurrentRun] = useState<WorkflowRun | null>(null)
  const [runHistory, setRunHistory] = useState<WorkflowRun[]>([])
  const [showRunHistory, setShowRunHistory] = useState(false)

  const selectedWorkflow = workflows.find(w => w.id === selectedWorkflowId) || null

  // Load workflows
  const loadWorkflows = useCallback(async () => {
    try {
      setLoading(true)
      const res = await fetch(`${API_BASE_URL}/api/v2/workflows`, {
        credentials: 'include',
      })
      if (!res.ok) throw new Error(`Failed to load workflows: ${res.status}`)
      const data = await res.json()
      setWorkflows(data.workflows || [])
    } catch (e: unknown) {
      const err = e as Error
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  // Load source options
  const loadSourceOptions = useCallback(async () => {
    try {
      const [channelsRes, labelsRes, pagesRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v2/workflows/sources/slack/channels`, { credentials: 'include' }),
        fetch(`${API_BASE_URL}/api/v2/workflows/sources/gmail/labels`, { credentials: 'include' }),
        fetch(`${API_BASE_URL}/api/v2/workflows/sources/notion/pages`, { credentials: 'include' }),
      ])
      
      if (channelsRes.ok) {
        const data = await channelsRes.json()
        setSlackChannels(data.channels || [])
      }
      if (labelsRes.ok) {
        const data = await labelsRes.json()
        setGmailLabels(data.labels || [])
      }
      if (pagesRes.ok) {
        const data = await pagesRes.json()
        setNotionPages(data.pages || [])
      }
    } catch (e) {
      console.error('Failed to load source options:', e)
    }
  }, [])

  // Load run history for selected workflow
  const loadRunHistory = useCallback(async (workflowId: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v2/workflows/${workflowId}/runs?limit=10`, {
        credentials: 'include',
      })
      if (res.ok) {
        const data = await res.json()
        setRunHistory(data.runs || [])
      }
    } catch (e) {
      console.error('Failed to load run history:', e)
    }
  }, [])

  useEffect(() => {
    loadWorkflows()
    loadSourceOptions()
  }, [loadWorkflows, loadSourceOptions])

  useEffect(() => {
    if (selectedWorkflowId) {
      loadRunHistory(selectedWorkflowId)
    }
  }, [selectedWorkflowId, loadRunHistory])

  // Keep selection in sync
  useEffect(() => {
    if (!selectedWorkflowId && workflows.length > 0) {
      setSelectedWorkflowId(workflows[0].id)
    } else if (selectedWorkflowId && !workflows.find(w => w.id === selectedWorkflowId)) {
      setSelectedWorkflowId(workflows.length > 0 ? workflows[0].id : null)
    }
  }, [selectedWorkflowId, workflows])

  // Create workflow
  const handleCreateWorkflow = async () => {
    if (!newWorkflowName.trim()) {
      setError('Workflow name is required')
      return
    }
    try {
      setLoading(true)
      const res = await fetch(`${API_BASE_URL}/api/v2/workflows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          name: newWorkflowName.trim(),
          source_config: { sources: [] },
          prompt_config: { system_prompt: '', user_instructions: '', output_format: 'markdown' },
          output_config: { outputs: [] },
        }),
      })
      if (!res.ok) throw new Error('Failed to create workflow')
      const created = await res.json()
      setWorkflows(prev => [created, ...prev])
      setSelectedWorkflowId(created.id)
      setCreateDialogOpen(false)
      setNewWorkflowName('')
    } catch (e: unknown) {
      const err = e as Error
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Rename workflow
  const handleRenameWorkflow = async () => {
    if (!selectedWorkflowId || !renameWorkflowName.trim()) return
    try {
      const res = await fetch(`${API_BASE_URL}/api/v2/workflows/${selectedWorkflowId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ name: renameWorkflowName.trim() }),
      })
      if (!res.ok) throw new Error('Failed to rename workflow')
      const updated = await res.json()
      setWorkflows(prev => prev.map(w => w.id === updated.id ? updated : w))
      setRenameDialogOpen(false)
    } catch (e: unknown) {
      const err = e as Error
      setError(err.message)
    }
  }

  // Delete workflow
  const handleDeleteWorkflow = async (workflowId: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v2/workflows/${workflowId}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (!res.ok) throw new Error('Failed to delete workflow')
      setWorkflows(prev => prev.filter(w => w.id !== workflowId))
      if (selectedWorkflowId === workflowId) {
        setSelectedWorkflowId(workflows.length > 1 ? workflows.find(w => w.id !== workflowId)?.id || null : null)
      }
      setDeleteTargetId(null)
    } catch (e: unknown) {
      const err = e as Error
      setError(err.message)
    }
  }

  // Update workflow config
  const updateWorkflowConfig = async (updates: Partial<UserWorkflow>) => {
    if (!selectedWorkflowId) return
    try {
      const res = await fetch(`${API_BASE_URL}/api/v2/workflows/${selectedWorkflowId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(updates),
      })
      if (!res.ok) throw new Error('Failed to update workflow')
      const updated = await res.json()
      setWorkflows(prev => prev.map(w => w.id === updated.id ? updated : w))
    } catch (e: unknown) {
      const err = e as Error
      setError(err.message)
    }
  }

  // Run workflow
  const handleRunWorkflow = async () => {
    if (!selectedWorkflowId) return
    try {
      setRunLoading(true)
      setCurrentRun(null)
      const res = await fetch(`${API_BASE_URL}/api/v2/workflows/${selectedWorkflowId}/run`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) throw new Error('Failed to run workflow')
      const result = await res.json()
      
      // Load the run details
      if (result.run_id) {
        const runRes = await fetch(`${API_BASE_URL}/api/v2/workflows/${selectedWorkflowId}/runs/${result.run_id}`, {
          credentials: 'include',
        })
        if (runRes.ok) {
          const runData = await runRes.json()
          setCurrentRun(runData)
        }
      }
      
      // Refresh run history
      loadRunHistory(selectedWorkflowId)
      loadWorkflows()
    } catch (e: unknown) {
      const err = e as Error
      setError(err.message)
    } finally {
      setRunLoading(false)
    }
  }

  // Stop workflow run
  const handleStopWorkflow = async () => {
    if (!selectedWorkflowId || !currentRun?.id) return
    try {
      const res = await fetch(`${API_BASE_URL}/api/v2/workflows/${selectedWorkflowId}/runs/${currentRun.id}/cancel`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) throw new Error('Failed to stop workflow')
      
      // Refresh run status
      const runRes = await fetch(`${API_BASE_URL}/api/v2/workflows/${selectedWorkflowId}/runs/${currentRun.id}`, {
        credentials: 'include',
      })
      if (runRes.ok) {
        const runData = await runRes.json()
        setCurrentRun(runData)
      }
      loadRunHistory(selectedWorkflowId)
    } catch (e: unknown) {
      const err = e as Error
      setError(err.message)
    }
  }

  // Check if workflow is currently running
  const isWorkflowRunning = currentRun?.status === 'running' || runLoading

  // Get source summary for display
  const getSourceSummary = (config: SourceConfig) => {
    const sources = config?.sources || []
    if (sources.length === 0) return 'No sources configured'
    
    const parts: string[] = []
    for (const s of sources) {
      if (s.type === 'slack') {
        const count = s.channels?.length || 0
        parts.push(`Slack (${count} channel${count !== 1 ? 's' : ''})`)
      } else if (s.type === 'gmail') {
        const count = s.labels?.length || 0
        parts.push(`Gmail (${count} label${count !== 1 ? 's' : ''})`)
      } else if (s.type === 'notion') {
        const count = s.pages?.length || 0
        parts.push(`Notion (${count} page${count !== 1 ? 's' : ''})`)
      }
    }
    return parts.join(', ') || 'No sources configured'
  }

  // Get prompt summary for display
  const getPromptSummary = (config: PromptConfig) => {
    const instructions = config?.user_instructions || ''
    if (!instructions) return 'No prompt configured'
    return instructions.length > 60 ? instructions.substring(0, 60) + '...' : instructions
  }

  // Get output summary for display
  const getOutputSummary = (config: OutputConfig) => {
    const outputs = config?.outputs || []
    if (outputs.length === 0) return 'No outputs configured'
    
    const types = outputs.map(o => {
      if (o.type === 'notion_page') return 'Notion'
      if (o.type === 'slack_message') return 'Slack'
      if (o.type === 'gmail_draft') return 'Gmail Draft'
      if (o.type === 'display') return 'Display'
      return o.type
    })
    return types.join(', ')
  }

  return (
    <div className="flex h-full bg-background">
      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteTargetId !== null} onOpenChange={(open) => !open && setDeleteTargetId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete workflow?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the workflow and all its run history.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 hover:bg-red-700"
              onClick={() => deleteTargetId && handleDeleteWorkflow(deleteTargetId)}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Create Workflow Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create New Workflow</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-4">
            <div className="grid gap-2">
              <label className="text-sm font-medium">Workflow Name</label>
              <input
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                value={newWorkflowName}
                onChange={(e) => setNewWorkflowName(e.target.value)}
                placeholder="e.g., Daily Slack Summary"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleCreateWorkflow}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rename Workflow Dialog */}
      <Dialog open={renameDialogOpen} onOpenChange={setRenameDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename Workflow</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-4">
            <label htmlFor="rename-workflow-input" className="sr-only">Workflow name</label>
            <input
              id="rename-workflow-input"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              value={renameWorkflowName}
              onChange={(e) => setRenameWorkflowName(e.target.value)}
              placeholder="Workflow name"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleRenameWorkflow}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Source Editor Dialog */}
      <SourceEditorDialog
        open={sourceEditorOpen}
        onOpenChange={setSourceEditorOpen}
        config={selectedWorkflow?.source_config || { sources: [] }}
        slackChannels={slackChannels}
        gmailLabels={gmailLabels}
        notionPages={notionPages}
        onSave={(config) => {
          updateWorkflowConfig({ source_config: config })
          setSourceEditorOpen(false)
        }}
      />

      {/* Prompt Editor Dialog */}
      <PromptEditorDialog
        open={promptEditorOpen}
        onOpenChange={setPromptEditorOpen}
        config={selectedWorkflow?.prompt_config || { system_prompt: '', user_instructions: '', output_format: 'markdown' }}
        onSave={(config) => {
          updateWorkflowConfig({ prompt_config: config })
          setPromptEditorOpen(false)
        }}
      />

      {/* Output Editor Dialog */}
      <OutputEditorDialog
        open={outputEditorOpen}
        onOpenChange={setOutputEditorOpen}
        config={selectedWorkflow?.output_config || { outputs: [] }}
        slackChannels={slackChannels}
        notionPages={notionPages}
        onSave={(config) => {
          updateWorkflowConfig({ output_config: config })
          setOutputEditorOpen(false)
        }}
      />

      {/* Sidebar */}
      <aside className="w-64 border-r border-border bg-card flex flex-col">
        <div className="p-3 border-b border-border flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">Workflows</h2>
          <button
            onClick={() => setCreateDialogOpen(true)}
            className="p-1 rounded-md hover:bg-muted"
            title="New Workflow"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-auto">
          {loading && workflows.length === 0 ? (
            <p className="p-3 text-xs text-muted-foreground">Loading...</p>
          ) : workflows.length === 0 ? (
            <p className="p-3 text-xs text-muted-foreground">
              No workflows yet. Create one to automate your tasks.
            </p>
          ) : (
            <ul className="py-2">
              {workflows.map((wf) => (
                <li key={wf.id}>
                  <button
                    onClick={() => setSelectedWorkflowId(wf.id)}
                    className={`group relative w-full text-left px-3 py-2 text-xs border-l-2 transition-colors ${
                      selectedWorkflowId === wf.id
                        ? 'border-blue-500 bg-muted/60'
                        : 'border-transparent hover:bg-muted/40'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-foreground truncate">{wf.name}</span>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setRenameWorkflowName(wf.name)
                            setRenameDialogOpen(true)
                          }}
                          className="p-0.5 hover:text-blue-500"
                          title="Rename workflow"
                          aria-label="Rename workflow"
                        >
                          <Pencil className="h-3 w-3" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setDeleteTargetId(wf.id)
                          }}
                          className="p-0.5 hover:text-red-500"
                          title="Delete workflow"
                          aria-label="Delete workflow"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    </div>
                    <p className="text-[10px] text-muted-foreground mt-0.5 truncate">
                      {wf.status === 'draft' ? 'Draft' : wf.status === 'active' ? 'Active' : wf.status}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {error && (
          <div className="p-2 text-[11px] text-red-400 border-t border-red-500/40 bg-red-950/60">
            {error}
            <button onClick={() => setError(null)} className="ml-2 underline">Dismiss</button>
          </div>
        )}
      </aside>

      {/* Main Content */}
      <section className="flex-1 flex flex-col overflow-hidden">
        {!selectedWorkflow ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <p className="text-muted-foreground mb-4">Select a workflow or create a new one</p>
              <Button onClick={() => setCreateDialogOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                New Workflow
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col p-6 overflow-auto">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
              <div>
                <h1 className="text-xl font-semibold text-foreground">{selectedWorkflow.name}</h1>
                <p className="text-sm text-muted-foreground">
                  {selectedWorkflow.status === 'draft' ? 'Draft - Configure blocks below' : `Status: ${selectedWorkflow.status}`}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowRunHistory(!showRunHistory)}
                >
                  <History className="h-4 w-4 mr-2" />
                  History
                </Button>
{isWorkflowRunning ? (
                  <Button
                    onClick={handleStopWorkflow}
                    className="bg-red-600 hover:bg-red-700"
                  >
                    <Square className="h-4 w-4 mr-2" />
                    Stop
                  </Button>
                ) : (
                  <Button
                    onClick={handleRunWorkflow}
                    className="bg-green-600 hover:bg-green-700"
                  >
                    <Play className="h-4 w-4 mr-2" />
                    Run Workflow
                  </Button>
                )}
              </div>
            </div>

            {/* Workflow Canvas - 3 Blocks */}
            <div className="flex items-center gap-4 mb-6">
              {/* Source Block */}
              <div
                className="flex-1 border-2 border-dashed border-border rounded-lg p-4 hover:border-blue-500 cursor-pointer transition-colors bg-card"
                onClick={() => setSourceEditorOpen(true)}
              >
                <div className="flex items-center gap-2 mb-2">
                  <div className="p-2 rounded-md bg-blue-500/10">
                    <Database className="h-5 w-5 text-blue-500" />
                  </div>
                  <h3 className="font-medium text-foreground">Source</h3>
                  <Settings className="h-4 w-4 text-muted-foreground ml-auto" />
                </div>
                <p className="text-xs text-muted-foreground">
                  {getSourceSummary(selectedWorkflow.source_config)}
                </p>
              </div>

              <ChevronRight className="h-6 w-6 text-muted-foreground flex-shrink-0" />

              {/* AI Prompt Block */}
              <div
                className="flex-1 border-2 border-dashed border-border rounded-lg p-4 hover:border-purple-500 cursor-pointer transition-colors bg-card"
                onClick={() => setPromptEditorOpen(true)}
              >
                <div className="flex items-center gap-2 mb-2">
                  <div className="p-2 rounded-md bg-purple-500/10">
                    <Brain className="h-5 w-5 text-purple-500" />
                  </div>
                  <h3 className="font-medium text-foreground">AI Prompt</h3>
                  <Settings className="h-4 w-4 text-muted-foreground ml-auto" />
                </div>
                <p className="text-xs text-muted-foreground">
                  {getPromptSummary(selectedWorkflow.prompt_config)}
                </p>
              </div>

              <ChevronRight className="h-6 w-6 text-muted-foreground flex-shrink-0" />

              {/* Output Block */}
              <div
                className="flex-1 border-2 border-dashed border-border rounded-lg p-4 hover:border-green-500 cursor-pointer transition-colors bg-card"
                onClick={() => setOutputEditorOpen(true)}
              >
                <div className="flex items-center gap-2 mb-2">
                  <div className="p-2 rounded-md bg-green-500/10">
                    <Send className="h-5 w-5 text-green-500" />
                  </div>
                  <h3 className="font-medium text-foreground">Output</h3>
                  <Settings className="h-4 w-4 text-muted-foreground ml-auto" />
                </div>
                <p className="text-xs text-muted-foreground">
                  {getOutputSummary(selectedWorkflow.output_config)}
                </p>
              </div>
            </div>

            {/* Scheduling Configuration */}
            <div className="border border-border rounded-lg p-4 mb-6 bg-card">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Clock className="h-5 w-5 text-muted-foreground" />
                  <h3 className="font-medium text-foreground">Schedule</h3>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  selectedWorkflow.schedule_type === 'interval' && selectedWorkflow.status === 'active'
                    ? 'bg-green-500/10 text-green-500'
                    : 'bg-muted text-muted-foreground'
                }`}>
                  {selectedWorkflow.schedule_type === 'manual' ? 'Manual' : 
                   selectedWorkflow.status === 'active' ? 'Active' : 'Paused'}
                </span>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="schedule-type" className="text-xs font-medium text-muted-foreground block mb-1">
                    Schedule Type
                  </label>
                  <select
                    id="schedule-type"
                    value={selectedWorkflow.schedule_type}
                    onChange={(e) => updateWorkflowConfig({ 
                      schedule_type: e.target.value,
                      status: e.target.value === 'manual' ? 'draft' : selectedWorkflow.status
                    })}
                    className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm"
                    aria-label="Schedule type"
                  >
                    {SCHEDULE_TYPE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>

                {selectedWorkflow.schedule_type === 'interval' && (
                  <div>
                    <label htmlFor="schedule-interval" className="text-xs font-medium text-muted-foreground block mb-1">
                      Run Interval
                    </label>
                    <select
                      id="schedule-interval"
                      value={(selectedWorkflow.schedule_config as Record<string, number>)?.interval_seconds || 3600}
                      onChange={(e) => updateWorkflowConfig({ 
                        schedule_config: { interval_seconds: parseInt(e.target.value) }
                      })}
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm"
                      aria-label="Run interval"
                    >
                      {INTERVAL_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {selectedWorkflow.schedule_type === 'interval' && (
                <div className="mt-3 flex items-center justify-between">
                  <p className="text-xs text-muted-foreground">
                    {selectedWorkflow.last_run_at 
                      ? `Last run: ${new Date(selectedWorkflow.last_run_at).toLocaleString()}`
                      : 'Never run'}
                  </p>
                  <Button
                    size="sm"
                    variant={selectedWorkflow.status === 'active' ? 'destructive' : 'default'}
                    onClick={() => updateWorkflowConfig({ 
                      status: selectedWorkflow.status === 'active' ? 'paused' : 'active'
                    })}
                  >
                    {selectedWorkflow.status === 'active' ? 'Pause Schedule' : 'Activate Schedule'}
                  </Button>
                </div>
              )}
            </div>

            {/* Current Run Status / Logs */}
            {(currentRun || runLoading) && (
              <div className="border border-border rounded-lg p-4 mb-6 bg-card">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-medium text-foreground">Current Run</h3>
                  {currentRun && (
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      currentRun.status === 'completed' ? 'bg-green-500/10 text-green-500' :
                      currentRun.status === 'failed' ? 'bg-red-500/10 text-red-500' :
                      'bg-blue-500/10 text-blue-500'
                    }`}>
                      {currentRun.status}
                    </span>
                  )}
                </div>
                
                {/* Progress bar */}
                {(() => {
                  const progressValue: number =
                    currentRun?.progress_percent ?? (runLoading ? 10 : 0)
                  return (
                <div className="h-2 bg-muted rounded-full mb-3 overflow-hidden">
                  <progress
                    className="sr-only"
                    value={progressValue}
                    max={100}
                    aria-label="Workflow progress"
                  />
                  <div
                    className="h-full bg-blue-500 transition-all duration-300"
                    style={{ width: `${progressValue}%` }}
                    aria-hidden="true"
                  />
                </div>
                  )
                })()}

                {/* Current step */}
                <p className="text-xs text-muted-foreground mb-2">
                  {currentRun?.current_step || (runLoading ? 'Starting...' : '')}
                </p>

                {/* Logs */}
                {currentRun?.logs && currentRun.logs.length > 0 && (
                  <div className="bg-background rounded-md p-2 max-h-40 overflow-auto text-xs font-mono">
                    {currentRun.logs.map((log, i) => (
                      <div key={i} className={`py-0.5 ${
                        log.level === 'error' ? 'text-red-400' : 'text-muted-foreground'
                      }`}>
                        <span className="text-muted-foreground/50">{log.timestamp.split('T')[1]?.split('.')[0]}</span>
                        {' '}{log.message}
                      </div>
                    ))}
                  </div>
                )}

                {/* AI Response Preview */}
                {currentRun?.ai_response && (
                  <div className="mt-3">
                    <h4 className="text-xs font-medium text-muted-foreground mb-1">AI Response Preview</h4>
                    <div className="bg-background rounded-md p-2 text-xs max-h-32 overflow-auto whitespace-pre-wrap">
                      {currentRun.ai_response.substring(0, 500)}
                      {currentRun.ai_response.length > 500 && '...'}
                    </div>
                  </div>
                )}

                {/* Error */}
                {currentRun?.error_message && (
                  <div className="mt-3 p-2 bg-red-500/10 rounded-md text-xs text-red-400">
                    <AlertCircle className="h-4 w-4 inline mr-1" />
                    {currentRun.error_message}
                  </div>
                )}
              </div>
            )}

            {/* Run History */}
            {showRunHistory && (
              <div className="border border-border rounded-lg p-4 bg-card">
                <h3 className="font-medium text-foreground mb-3">Run History</h3>
                {runHistory.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No runs yet</p>
                ) : (
                  <div className="space-y-2">
                    {runHistory.map((run) => (
                      <div
                        key={run.id}
                        className="flex items-center justify-between p-2 bg-background rounded-md text-xs"
                      >
                        <div className="flex items-center gap-2">
                          {run.status === 'completed' ? (
                            <Check className="h-4 w-4 text-green-500" />
                          ) : run.status === 'failed' ? (
                            <X className="h-4 w-4 text-red-500" />
                          ) : (
                            <Clock className="h-4 w-4 text-muted-foreground" />
                          )}
                          <span className="text-muted-foreground">
                            {run.started_at ? new Date(run.started_at).toLocaleString() : 'Pending'}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground">
                            {run.source_items_count} items
                          </span>
                          <span className={`px-1.5 py-0.5 rounded ${
                            run.status === 'completed' ? 'bg-green-500/10 text-green-500' :
                            run.status === 'failed' ? 'bg-red-500/10 text-red-500' :
                            'bg-muted text-muted-foreground'
                          }`}>
                            {run.status}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Last Run Info */}
            {selectedWorkflow.last_run_at && !showRunHistory && !currentRun && (
              <div className="text-xs text-muted-foreground">
                Last run: {new Date(selectedWorkflow.last_run_at).toLocaleString()}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  )
}

// Source Editor Dialog Component
function SourceEditorDialog({
  open,
  onOpenChange,
  config,
  slackChannels,
  gmailLabels,
  notionPages,
  onSave,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: SourceConfig
  slackChannels: SlackChannel[]
  gmailLabels: GmailLabel[]
  notionPages: NotionPage[]
  onSave: (config: SourceConfig) => void
}) {
  const [sources, setSources] = useState(config.sources || [])

  const [pendingSlackAdd, setPendingSlackAdd] = useState<Record<number, string>>({})
  const [pendingGmailAdd, setPendingGmailAdd] = useState<Record<number, string>>({})
  const [pendingNotionAdd, setPendingNotionAdd] = useState<Record<number, string>>({})

  useEffect(() => {
    if (open) {
      setSources(config.sources || [])
      setPendingSlackAdd({})
      setPendingGmailAdd({})
      setPendingNotionAdd({})
    }
  }, [open, config])

  const addSource = (type: 'slack' | 'gmail' | 'notion') => {
    setSources([...sources, { type, time_range: 'last_24h', channels: [], labels: [], pages: [] }])
  }

  const removeSource = (index: number) => {
    setSources(sources.filter((_, i) => i !== index))
  }

  const updateSource = (index: number, updates: Partial<SourceConfig['sources'][0]>) => {
    setSources(sources.map((s, i) => i === index ? { ...s, ...updates } : s))
  }

  const slackOptions: SearchableSelectOption[] = slackChannels.map((ch) => ({
    value: ch.id,
    label: `#${ch.name}${ch.is_private ? ' (private)' : ''}`,
  }))

  const gmailOptions: SearchableSelectOption[] = gmailLabels.map((l) => ({
    value: l.id,
    label: l.name,
  }))

  const notionOptions: SearchableSelectOption[] = notionPages.map((p) => ({
    value: p.id,
    label: p.title || p.id,
  }))

  const labelForSlackId = (id: string) => slackOptions.find((o) => o.value === id)?.label || id
  const labelForGmailId = (id: string) => gmailOptions.find((o) => o.value === id)?.label || id
  const labelForNotionId = (id: string) => notionOptions.find((o) => o.value === id)?.label || id

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-auto">
        <DialogHeader>
          <DialogTitle>Configure Sources</DialogTitle>
        </DialogHeader>
        <div className="py-4 space-y-4">
          {/* Add source buttons */}
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => addSource('slack')}>
              + Slack
            </Button>
            <Button variant="outline" size="sm" onClick={() => addSource('gmail')}>
              + Gmail
            </Button>
            <Button variant="outline" size="sm" onClick={() => addSource('notion')}>
              + Notion
            </Button>
          </div>

          {/* Source list */}
          {sources.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No sources added. Click above to add a source.
            </p>
          ) : (
            <div className="space-y-4">
              {sources.map((source, index) => (
                <div key={index} className="border border-border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="font-medium capitalize">{source.type}</h4>
                    <button
                      onClick={() => removeSource(index)}
                      className="text-red-500 hover:text-red-600"
                      title="Remove source"
                      aria-label="Remove source"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>

                  {/* Source-specific options */}
                  {source.type === 'slack' && (
                    <div className="space-y-2">
                      <label className="text-xs font-medium">Channels</label>
                      <div className="flex items-center gap-2">
                        <SearchableSelect
                          id={`slack-channel-add-${index}`}
                          value={pendingSlackAdd[index] || ''}
                          onChange={(v) => setPendingSlackAdd((prev) => ({ ...prev, [index]: v }))}
                          options={slackOptions}
                          placeholder="Add channel…"
                          searchPlaceholder="Search channels…"
                          allowClear
                          containerClassName="flex-1"
                          fullWidth
                        />
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => {
                            const idToAdd = (pendingSlackAdd[index] || '').trim()
                            if (!idToAdd) return
                            const current = source.channels || []
                            if (current.includes(idToAdd)) {
                              setPendingSlackAdd((prev) => ({ ...prev, [index]: '' }))
                              return
                            }
                            updateSource(index, { channels: [...current, idToAdd] })
                            setPendingSlackAdd((prev) => ({ ...prev, [index]: '' }))
                          }}
                          disabled={!pendingSlackAdd[index]}
                        >
                          Add
                        </Button>
                      </div>

                      <div className="flex flex-wrap gap-1">
                        {(source.channels || []).length === 0 ? (
                          <span className="text-[11px] text-muted-foreground">No channels selected.</span>
                        ) : (
                          (source.channels || []).map((id) => (
                            <button
                              key={id}
                              type="button"
                              onClick={() => updateSource(index, { channels: (source.channels || []).filter((x) => x !== id) })}
                              className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground hover:bg-red-900/40 hover:text-red-200"
                              title="Remove channel"
                              aria-label="Remove channel"
                            >
                              <span className="truncate">{labelForSlackId(id)}</span>
                              <span>×</span>
                            </button>
                          ))
                        )}
                      </div>
                    </div>
                  )}

                  {source.type === 'gmail' && (
                    <div className="space-y-2">
                      <label className="text-xs font-medium">Labels</label>
                      <div className="flex items-center gap-2">
                        <SearchableSelect
                          id={`gmail-label-add-${index}`}
                          value={pendingGmailAdd[index] || ''}
                          onChange={(v) => setPendingGmailAdd((prev) => ({ ...prev, [index]: v }))}
                          options={gmailOptions}
                          placeholder="Add label…"
                          searchPlaceholder="Search labels…"
                          allowClear
                          containerClassName="flex-1"
                          fullWidth
                        />
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => {
                            const idToAdd = (pendingGmailAdd[index] || '').trim()
                            if (!idToAdd) return
                            const current = source.labels || []
                            if (current.includes(idToAdd)) {
                              setPendingGmailAdd((prev) => ({ ...prev, [index]: '' }))
                              return
                            }
                            updateSource(index, { labels: [...current, idToAdd] })
                            setPendingGmailAdd((prev) => ({ ...prev, [index]: '' }))
                          }}
                          disabled={!pendingGmailAdd[index]}
                        >
                          Add
                        </Button>
                      </div>

                      <div className="flex flex-wrap gap-1">
                        {(source.labels || []).length === 0 ? (
                          <span className="text-[11px] text-muted-foreground">No labels selected.</span>
                        ) : (
                          (source.labels || []).map((id) => (
                            <button
                              key={id}
                              type="button"
                              onClick={() => updateSource(index, { labels: (source.labels || []).filter((x) => x !== id) })}
                              className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground hover:bg-red-900/40 hover:text-red-200"
                              title="Remove label"
                              aria-label="Remove label"
                            >
                              <span className="truncate">{labelForGmailId(id)}</span>
                              <span>×</span>
                            </button>
                          ))
                        )}
                      </div>
                    </div>
                  )}

                  {source.type === 'notion' && (
                    <div className="space-y-2">
                      <label className="text-xs font-medium">Pages</label>
                      <div className="flex items-center gap-2">
                        <SearchableSelect
                          id={`notion-page-add-${index}`}
                          value={pendingNotionAdd[index] || ''}
                          onChange={(v) => setPendingNotionAdd((prev) => ({ ...prev, [index]: v }))}
                          options={notionOptions}
                          placeholder="Add page…"
                          searchPlaceholder="Search pages…"
                          allowClear
                          containerClassName="flex-1"
                          fullWidth
                        />
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => {
                            const idToAdd = (pendingNotionAdd[index] || '').trim()
                            if (!idToAdd) return
                            const current = source.pages || []
                            if (current.includes(idToAdd)) {
                              setPendingNotionAdd((prev) => ({ ...prev, [index]: '' }))
                              return
                            }
                            updateSource(index, { pages: [...current, idToAdd] })
                            setPendingNotionAdd((prev) => ({ ...prev, [index]: '' }))
                          }}
                          disabled={!pendingNotionAdd[index]}
                        >
                          Add
                        </Button>
                      </div>

                      <div className="flex flex-wrap gap-1">
                        {(source.pages || []).length === 0 ? (
                          <span className="text-[11px] text-muted-foreground">No pages selected.</span>
                        ) : (
                          (source.pages || []).map((id) => (
                            <button
                              key={id}
                              type="button"
                              onClick={() => updateSource(index, { pages: (source.pages || []).filter((x) => x !== id) })}
                              className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground hover:bg-red-900/40 hover:text-red-200"
                              title="Remove page"
                              aria-label="Remove page"
                            >
                              <span className="truncate">{labelForNotionId(id)}</span>
                              <span>×</span>
                            </button>
                          ))
                        )}
                      </div>
                    </div>
                  )}

                  {/* Time range */}
                  <div className="mt-3">
                    <label htmlFor={`time-range-${index}`} className="text-xs font-medium">Time Range</label>
                    <select
                      id={`time-range-${index}`}
                      value={source.time_range}
                      onChange={(e) => updateSource(index, { time_range: e.target.value })}
                      className="w-full mt-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm"
                      aria-label="Time range"
                    >
                      {TIME_RANGE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => onSave({ sources })}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Prompt Editor Dialog Component
function PromptEditorDialog({
  open,
  onOpenChange,
  config,
  onSave,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: PromptConfig
  onSave: (config: PromptConfig) => void
}) {
  const [systemPrompt, setSystemPrompt] = useState(config.system_prompt || '')
  const [userInstructions, setUserInstructions] = useState(config.user_instructions || '')
  const [outputFormat, setOutputFormat] = useState(config.output_format || 'markdown')

  useEffect(() => {
    if (open) {
      setSystemPrompt(config.system_prompt || '')
      setUserInstructions(config.user_instructions || '')
      setOutputFormat(config.output_format || 'markdown')
    }
  }, [open, config])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Configure AI Prompt</DialogTitle>
        </DialogHeader>
        <div className="py-4 space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">System Prompt (optional)</label>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="You are a helpful assistant that processes and analyzes data..."
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm min-h-[80px]"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Instructions *</label>
            <textarea
              value={userInstructions}
              onChange={(e) => setUserInstructions(e.target.value)}
              placeholder="Summarize the key points and action items from this data..."
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm min-h-[120px]"
            />
            <p className="text-xs text-muted-foreground">
              Tell the AI what to do with the source data.
            </p>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="prompt-output-format">Output Format</label>
            <select
              id="prompt-output-format"
              value={outputFormat}
              onChange={(e) => setOutputFormat(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              aria-label="Output format"
            >
              {OUTPUT_FORMAT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => onSave({
            system_prompt: systemPrompt,
            user_instructions: userInstructions,
            output_format: outputFormat,
          })}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Output Editor Dialog Component
function OutputEditorDialog({
  open,
  onOpenChange,
  config,
  slackChannels,
  notionPages,
  onSave,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: OutputConfig
  slackChannels: SlackChannel[]
  notionPages: NotionPage[]
  onSave: (config: OutputConfig) => void
}) {
  const [outputs, setOutputs] = useState(config.outputs || [])

  const slackOptions: SearchableSelectOption[] = slackChannels.map((ch) => ({
    value: ch.id,
    label: `#${ch.name}${ch.is_private ? ' (private)' : ''}`,
  }))

  const notionOptions: SearchableSelectOption[] = notionPages.map((p) => ({
    value: p.id,
    label: p.title || p.id,
  }))

  useEffect(() => {
    if (open) {
      setOutputs(config.outputs || [])
    }
  }, [open, config])

  const addOutput = (type: OutputConfig['outputs'][0]['type']) => {
    setOutputs([...outputs, { type }])
  }

  const removeOutput = (index: number) => {
    setOutputs(outputs.filter((_, i) => i !== index))
  }

  const updateOutput = (index: number, updates: Partial<OutputConfig['outputs'][0]>) => {
    setOutputs(outputs.map((o, i) => i === index ? { ...o, ...updates } : o))
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-auto">
        <DialogHeader>
          <DialogTitle>Configure Outputs</DialogTitle>
        </DialogHeader>
        <div className="py-4 space-y-4">
          {/* Add output buttons */}
          <div className="flex gap-2 flex-wrap">
            <Button variant="outline" size="sm" onClick={() => addOutput('notion_page')}>
              + Notion Page
            </Button>
            <Button variant="outline" size="sm" onClick={() => addOutput('slack_message')}>
              + Slack Message
            </Button>
            <Button variant="outline" size="sm" onClick={() => addOutput('gmail_draft')}>
              + Gmail Draft
            </Button>
            <Button variant="outline" size="sm" onClick={() => addOutput('display')}>
              + Display Only
            </Button>
          </div>

          {/* Output list */}
          {outputs.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No outputs added. Click above to add an output destination.
            </p>
          ) : (
            <div className="space-y-4">
              {outputs.map((output, index) => (
                <div key={index} className="border border-border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="font-medium">
                      {output.type === 'notion_page' ? 'Notion Page' :
                       output.type === 'slack_message' ? 'Slack Message' :
                       output.type === 'gmail_draft' ? 'Gmail Draft' :
                       output.type === 'display' ? 'Display Only' : output.type}
                    </h4>
                    <button
                      onClick={() => removeOutput(index)}
                      className="text-red-500 hover:text-red-600"
                      title="Remove output"
                      aria-label="Remove output"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>

                  {/* Output-specific options */}
                  {output.type === 'notion_page' && (
                    <div className="space-y-2">
                      <label className="text-xs font-medium">Target Page or Database (optional)</label>
                      <div className="flex items-center gap-2">
                        <SearchableSelect
                          id={`notion-page-${index}`}
                          value={output.page_id || ''}
                          onChange={(v) => updateOutput(index, { page_id: v || undefined })}
                          options={notionOptions}
                          placeholder="Let AI create new page"
                          searchPlaceholder="Search Notion pages…"
                          allowClear
                          clearLabel="Let AI create new page"
                          containerClassName="flex-1"
                          fullWidth
                        />
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        AI will read the target page/database structure and intelligently update it based on your prompt.
                        It can fill empty fields, update existing content, add to databases, or modify subpages as needed.
                      </p>
                    </div>
                  )}

                  {output.type === 'slack_message' && (
                    <div className="space-y-2">
                      <label className="text-xs font-medium">Channel</label>
                      <SearchableSelect
                        id={`slack-channel-${index}`}
                        value={output.channel || ''}
                        onChange={(v) => updateOutput(index, { channel: v || undefined })}
                        options={slackOptions}
                        placeholder="Select channel…"
                        searchPlaceholder="Search channels…"
                        allowClear
                        containerClassName="w-full"
                        fullWidth
                      />
                    </div>
                  )}

                  {output.type === 'gmail_draft' && (
                    <div className="space-y-2">
                      <div>
                        <label className="text-xs font-medium">To (email)</label>
                        <input
                          type="email"
                          value={output.to || ''}
                          onChange={(e) => updateOutput(index, { to: e.target.value })}
                          placeholder="recipient@example.com"
                          className="w-full mt-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-xs font-medium">Subject</label>
                        <input
                          type="text"
                          value={output.subject || ''}
                          onChange={(e) => updateOutput(index, { subject: e.target.value })}
                          placeholder="Workflow Output"
                          className="w-full mt-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm"
                        />
                      </div>
                    </div>
                  )}

                  {output.type === 'display' && (
                    <p className="text-xs text-muted-foreground">
                      The AI response will be displayed in the UI without sending to any external service.
                    </p>
                  )}

                  {/* Output-specific prompt for all output types */}
                  <div className="mt-4 pt-4 border-t border-border">
                    <label className="text-xs font-medium block mb-1">
                      Output Instructions (optional)
                    </label>
                    <textarea
                      value={output.output_prompt || ''}
                      onChange={(e) => updateOutput(index, { output_prompt: e.target.value })}
                      placeholder="Give specific instructions for this output. E.g., 'Format as a table with columns: Task, Status, Owner' or 'Only include action items from the discussion'"
                      className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm min-h-[80px] resize-y"
                      rows={3}
                    />
                    <p className="text-[11px] text-muted-foreground mt-1">
                      AI agent will use these instructions when processing and delivering this specific output.
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => onSave({ outputs })}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
