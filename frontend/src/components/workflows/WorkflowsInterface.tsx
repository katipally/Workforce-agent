import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../../lib/api'

interface WorkflowChannel {
  slack_channel_id: string
  slack_channel_name?: string | null
  notion_subpage_id?: string | null
  last_slack_ts_synced?: number | null
  created_at?: string | null
  updated_at?: string | null
}

interface Workflow {
  id: string
  name: string
  type: string
  status: string
  notion_master_page_id?: string | null
  poll_interval_seconds: number
  last_run_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  channels: WorkflowChannel[]
}

interface WorkflowsListResponse {
  workflows: Workflow[]
}

interface RunOnceStats {
  workflow_id: string
  messages_synced: number
  replies_synced: number
  channels_processed?: number
  duration_ms: number
  started_at: string
  finished_at: string
}

interface SlackChannelOption {
  channel_id: string
  name: string | null
  is_private?: boolean
  is_archived?: boolean
}

const INTERVAL_OPTIONS: { value: number; label: string }[] = [
  { value: 30, label: '30 seconds' },
  { value: 60, label: '1 minute' },
  { value: 300, label: '5 minutes' },
  { value: 600, label: '10 minutes' },
  { value: 3600, label: '1 hour' },
]

export default function WorkflowsInterface() {
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null)

  const [slackChannels, setSlackChannels] = useState<SlackChannelOption[]>([])
  const [slackToAdd, setSlackToAdd] = useState('')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [runOnceLoading, setRunOnceLoading] = useState(false)
  const [lastRunStats, setLastRunStats] = useState<RunOnceStats | null>(null)

  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null)

  const selectedWorkflow =
    workflows.find((w) => w.id === selectedWorkflowId) || (workflows.length > 0 ? workflows[0] : null)

  // Ensure selectedWorkflowId stays in sync when workflows list changes
  useEffect(() => {
    if (!selectedWorkflowId && workflows.length > 0) {
      setSelectedWorkflowId(workflows[0].id)
    } else if (selectedWorkflowId && !workflows.find((w) => w.id === selectedWorkflowId)) {
      setSelectedWorkflowId(workflows.length > 0 ? workflows[0].id : null)
    }
  }, [selectedWorkflowId, workflows])

  const loadWorkflows = async () => {
    try {
      setLoading(true)
      setError(null)
      const res = await fetch(`${API_BASE_URL}/api/workflows`, {
        credentials: 'include',
      })
      if (!res.ok) {
        throw new Error(`Failed to load workflows: ${res.status}`)
      }
      const data = (await res.json()) as WorkflowsListResponse
      setWorkflows(data.workflows || [])
    } catch (e: any) {
      console.error('Error loading workflows', e)
      setError(e.message || 'Failed to load workflows')
    } finally {
      setLoading(false)
    }
  }

  const handleUpdateStatus = async (workflow: Workflow, newStatus: 'active' | 'paused') => {
    try {
      setError(null)
      const res = await fetch(`${API_BASE_URL}/api/workflows/${workflow.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ status: newStatus }),
      })
      if (!res.ok) {
        throw new Error(`Failed to update status: ${res.status}`)
      }
      const updated = (await res.json()) as Workflow
      setWorkflows((prev) => prev.map((w) => (w.id === updated.id ? updated : w)))
    } catch (e: any) {
      console.error('Error updating workflow status', e)
      setError(e.message || 'Failed to update workflow status')
    }
  }

  const loadSlackChannels = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/pipelines/slack/data`, {
        credentials: 'include',
      })
      if (!res.ok) {
        throw new Error(`Failed to load Slack channels: ${res.status}`)
      }
      const data = await res.json()
      setSlackChannels((data.channels || []) as SlackChannelOption[])
    } catch (e) {
      console.error('Failed to load Slack channels for workflows', e)
    }
  }

  useEffect(() => {
    loadWorkflows()
    loadSlackChannels()
  }, [])

  useEffect(() => {
    const hasActive = workflows.some((w) => w.status === 'active')
    if (!hasActive) {
      return
    }

    const id = window.setInterval(() => {
      loadWorkflows()
    }, 5000)

    return () => window.clearInterval(id)
  }, [workflows])

  // Timer effect: simple UX countdown that loops from the selected interval to 0.
  // This is intentionally decoupled from the actual worker scheduling and is
  // just a visual indicator of the chosen interval.
  useEffect(() => {
    if (!selectedWorkflow || selectedWorkflow.status !== 'active') {
      setRemainingSeconds(null)
      return
    }

    const interval = selectedWorkflow.poll_interval_seconds || 30

    // Compute remaining seconds until the next scheduled run based on
    // last_run_at + interval, clamped between 0 and the interval.
    const computeInitialRemaining = () => {
      if (selectedWorkflow.last_run_at) {
        const lastRunMs = new Date(selectedWorkflow.last_run_at).getTime()
        const dueMs = lastRunMs + interval * 1000
        const nowMs = Date.now()
        const diffSec = Math.ceil((dueMs - nowMs) / 1000)
        if (diffSec <= 0) return 0
        if (diffSec > interval) return interval
        return diffSec
      }
      // Never run before: in the worker this is effectively "due now".
      return 0
    }

    setRemainingSeconds(computeInitialRemaining())

    const id = window.setInterval(() => {
      setRemainingSeconds((prev) => {
        if (prev == null) return prev
        if (prev <= 0) return 0
        return prev - 1
      })
    }, 1000)

    return () => window.clearInterval(id)
  }, [
    selectedWorkflow?.id,
    selectedWorkflow?.poll_interval_seconds,
    selectedWorkflow?.last_run_at,
    selectedWorkflow?.status,
  ])

  const handleCreateWorkflow = async () => {
    const name = window.prompt('Workflow name (e.g., "Slack → Notion: Zephyr")')
    if (!name) return
    const masterPageId = window.prompt('Notion master page ID (required for Slack → Notion)')
    if (!masterPageId) return

    try {
      setError(null)
      setLoading(true)
      const res = await fetch(`${API_BASE_URL}/api/workflows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          name,
          type: 'slack_to_notion',
          notion_master_page_id: masterPageId,
          poll_interval_seconds: 30,
        }),
      })
      if (!res.ok) {
        throw new Error(`Failed to create workflow: ${res.status}`)
      }
      const created = (await res.json()) as Workflow
      setWorkflows((prev) => [created, ...prev])
      setSelectedWorkflowId(created.id)
    } catch (e: any) {
      console.error('Error creating workflow', e)
      setError(e.message || 'Failed to create workflow')
    } finally {
      setLoading(false)
    }
  }

  const handleUpdateInterval = async (workflow: Workflow, newInterval: number) => {
    try {
      setError(null)
      const res = await fetch(`${API_BASE_URL}/api/workflows/${workflow.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ poll_interval_seconds: newInterval }),
      })
      if (!res.ok) {
        throw new Error(`Failed to update interval: ${res.status}`)
      }
      const updated = (await res.json()) as Workflow
      setWorkflows((prev) => prev.map((w) => (w.id === updated.id ? updated : w)))
    } catch (e: any) {
      console.error('Error updating workflow interval', e)
      setError(e.message || 'Failed to update workflow interval')
    }
  }

  const handleRunOnce = async (workflow: Workflow) => {
    try {
      setError(null)
      setRunOnceLoading(true)
      const res = await fetch(`${API_BASE_URL}/api/workflows/${workflow.id}/run-once`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) {
        throw new Error(`Failed to run workflow once: ${res.status}`)
      }
      const stats = (await res.json()) as RunOnceStats
      setLastRunStats(stats)
      // Reset the local countdown after a manual run
      setRemainingSeconds(workflow.poll_interval_seconds || 30)
      // Refresh workflows to pick up updated last_run_at
      await loadWorkflows()
    } catch (e: any) {
      console.error('Error running workflow once', e)
      setError(e.message || 'Failed to run workflow once')
    } finally {
      setRunOnceLoading(false)
    }
  }

  const handleAddSlackChannel = async () => {
    if (!selectedWorkflow || !slackToAdd) return
    const channel = slackChannels.find((c) => c.channel_id === slackToAdd)
    if (!channel) return

    try {
      setError(null)
      const res = await fetch(
        `${API_BASE_URL}/api/workflows/${selectedWorkflow.id}/channels`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify([
            {
              slack_channel_id: channel.channel_id,
              slack_channel_name: channel.name,
            },
          ]),
        },
      )
      if (!res.ok) {
        throw new Error(`Failed to add Slack channel: ${res.status}`)
      }
      await loadWorkflows()
      setSlackToAdd('')
    } catch (e: any) {
      console.error('Error adding Slack channel to workflow', e)
      setError(e.message || 'Failed to add Slack channel')
    }
  }

  const handleRemoveWorkflowChannel = async (workflowId: string, slackChannelId: string) => {
    try {
      setError(null)
      const res = await fetch(
        `${API_BASE_URL}/api/workflows/${workflowId}/channels/${encodeURIComponent(slackChannelId)}`,
        {
          method: 'DELETE',
          credentials: 'include',
        },
      )
      if (!res.ok) {
        throw new Error(`Failed to remove workflow channel: ${res.status}`)
      }
      await loadWorkflows()
    } catch (e: any) {
      console.error('Error removing workflow channel', e)
      setError(e.message || 'Failed to remove workflow channel')
    }
  }

  const formatRemaining = (value: number | null): string => {
    if (value == null) return '—'
    if (value <= 0) return 'due now'
    const m = Math.floor(value / 60)
    const s = value % 60
    if (m <= 0) return `${s}s`
    return `${m}m ${s.toString().padStart(2, '0')}s`
  }

  return (
    <div className="flex h-full bg-background">
      {/* Sidebar: workflow list */}
      <aside className="w-64 border-r border-border bg-card flex flex-col">
        <div className="p-3 border-b border-border flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">Workflows</h2>
          <button
            type="button"
            onClick={handleCreateWorkflow}
            className="text-xs rounded-md px-2 py-1 bg-blue-600 text-white hover:bg-blue-700"
          >
            New
          </button>
        </div>
        <div className="flex-1 overflow-auto">
          {loading && workflows.length === 0 ? (
            <p className="p-3 text-xs text-muted-foreground">Loading workflows…</p>
          ) : workflows.length === 0 ? (
            <p className="p-3 text-xs text-muted-foreground">
              No workflows yet. Create one to stream Slack channels into Notion.
            </p>
          ) : (
            <ul className="py-2">
              {workflows.map((wf) => (
                <li key={wf.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedWorkflowId(wf.id)}
                    className={`w-full text-left px-3 py-2 text-xs border-l-2 transition-colors ${{
                      true: 'border-blue-500 bg-muted/60',
                      false: 'border-transparent hover:bg-muted/40',
                    }[String(selectedWorkflow?.id === wf.id)]}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-foreground truncate">{wf.name}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">
                        {wf.status || 'active'}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[10px] text-muted-foreground line-clamp-2">
                      {wf.type === 'slack_to_notion'
                        ? 'Slack → Notion (per-channel subpages)'
                        : wf.type}
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
          </div>
        )}
      </aside>

      {/* Main: workflow detail */}
      <section className="flex-1 flex flex-col overflow-hidden">
        {!selectedWorkflow ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-xs text-muted-foreground">
              Select a workflow or create a new one to see details.
            </p>
          </div>
        ) : (
          <div className="flex-1 grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-4 p-4 overflow-hidden">
            {/* Left column: configuration + channels */}
            <div className="flex flex-col gap-4 overflow-hidden">
              {/* Configuration card */}
              <div className="border border-border rounded-md bg-card p-3 text-xs flex flex-col gap-2">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div className="flex flex-col flex-1 mr-2">
                    <div className="text-sm font-semibold text-foreground truncate" aria-label="Workflow name">
                      {selectedWorkflow.name}
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      Type: {selectedWorkflow.type}
                    </p>
                    {selectedWorkflow.notion_master_page_id && (
                      <p className="text-[10px] text-muted-foreground break-all">
                        Master Notion page: {selectedWorkflow.notion_master_page_id}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">
                        {selectedWorkflow.status || 'active'}
                      </span>
                      <button
                        type="button"
                        onClick={() =>
                          handleUpdateStatus(
                            selectedWorkflow,
                            selectedWorkflow.status === 'active' ? 'paused' : 'active',
                          )
                        }
                        className={`text-[11px] px-2 py-0.5 rounded-md border ${
                          selectedWorkflow.status === 'active'
                            ? 'border-red-500 text-red-500 hover:bg-red-500/10'
                            : 'border-green-600 text-green-600 hover:bg-green-600/10'
                        }`}
                      >
                        {selectedWorkflow.status === 'active' ? 'Stop' : 'Start'}
                      </button>
                    </div>
                    <label className="text-[10px] text-muted-foreground">Interval</label>
                    <select
                      className="text-[11px] rounded-md border border-border bg-background px-1.5 py-0.5"
                      aria-label="Workflow interval"
                      value={selectedWorkflow.poll_interval_seconds || 30}
                      onChange={(e) =>
                        handleUpdateInterval(selectedWorkflow, Number(e.target.value) || 30)
                      }
                    >
                      {INTERVAL_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                    <p className="text-[10px] text-muted-foreground">
                      Next run in{' '}
                      <span className="font-semibold">
                        {selectedWorkflow.status === 'active'
                          ? formatRemaining(remainingSeconds)
                          : 'paused'}
                      </span>
                    </p>
                    <button
                      type="button"
                      onClick={() => handleRunOnce(selectedWorkflow)}
                      disabled={runOnceLoading}
                      className="mt-1 text-[11px] px-2 py-0.5 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
                    >
                      {runOnceLoading ? 'Running…' : 'Run now'}
                    </button>
                  </div>
                </div>

                {selectedWorkflow.last_run_at && (
                  <p className="text-[10px] text-muted-foreground">
                    Last run: {new Date(selectedWorkflow.last_run_at).toLocaleString()}
                  </p>
                )}

                {lastRunStats && lastRunStats.workflow_id === selectedWorkflow.id && (
                  <div className="mt-2 rounded-md border border-border bg-background px-2 py-1 text-[10px] text-muted-foreground">
                    <p>
                      Last manual run: synced {lastRunStats.messages_synced} messages,{' '}
                      {lastRunStats.replies_synced} replies in{' '}
                      {(lastRunStats.duration_ms / 1000).toFixed(1)}s
                    </p>
                  </div>
                )}
              </div>

              {/* Channels card */}
              <div className="border border-border rounded-md bg-card p-3 text-xs flex flex-col gap-2 overflow-hidden">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <h3 className="text-xs font-semibold text-foreground">Slack channels</h3>
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
                      onClick={handleAddSlackChannel}
                      className="text-[11px] px-2 py-0.5 rounded-md bg-blue-600 text-white hover:bg-blue-700"
                    >
                      Add
                    </button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1">
                  {selectedWorkflow.channels.length === 0 && (
                    <span className="text-[10px] text-muted-foreground">
                      No Slack channels linked.
                    </span>
                  )}
                  {selectedWorkflow.channels.map((ch) => (
                    <button
                      key={ch.slack_channel_id}
                      type="button"
                      onClick={() =>
                        handleRemoveWorkflowChannel(selectedWorkflow.id, ch.slack_channel_id)
                      }
                      className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground hover:bg-red-900/40 hover:text-red-200"
                    >
                      <span>{ch.slack_channel_name || ch.slack_channel_id}</span>
                      <span>×</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Right column: placeholder explanation / future stats */}
            <div className="flex flex-col gap-4 overflow-hidden">
              <div className="border border-border rounded-md bg-card p-3 text-xs flex flex-col gap-2">
                <h3 className="text-xs font-semibold text-foreground mb-1">
                  Slack → Notion stream (read-only preview)
                </h3>
                <p className="text-[11px] text-muted-foreground mb-1">
                  This workflow will:
                </p>
                <ul className="list-disc list-inside text-[11px] text-muted-foreground space-y-0.5">
                  <li>Poll Slack every configured interval for new messages.</li>
                  <li>Create or reuse a Notion subpage per linked channel under the master page.</li>
                  <li>Append new messages as bulleted list items, including reactions and files.</li>
                  <li>Attach thread replies as indented child bullets under the root message.</li>
                  <li>Use idempotent mappings so messages are never duplicated in Notion.</li>
                </ul>
                <p className="mt-2 text-[11px] text-muted-foreground">
                  To start streaming, ensure your Slack data is synced in the Pipelines tab and that
                  the Notion integration has access to the master page and its children.
                </p>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
