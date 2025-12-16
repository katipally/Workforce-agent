import { useEffect, useState, useRef } from 'react'
import { API_BASE_URL } from '../../lib/api'
import { SearchableSelect } from '../common/SearchableSelect'

interface SlackPipelineStats {
  users: number
  channels: number
  messages: number
  files: number
  reactions: number
}

interface SlackChannel {
  channel_id: string
  name: string | null
  is_private: boolean
  is_archived: boolean
  num_members?: number | null
  message_count: number
}

interface SlackMessage {
  message_id: string
  user_id?: string | null
  user_name?: string | null
  text: string | null
  timestamp: number
  thread_ts?: number | null
  reply_count?: number | null
  subtype?: string | null
}

interface GmailLabel {
  id: string
  name: string
  type?: string
}

interface GmailMessage {
  id: string
  thread_id?: string
  from?: string
  to?: string | null
  cc?: string | null
  bcc?: string | null
  subject?: string
  date?: string | null
  snippet?: string
  body_text?: string
  body_html?: string
}

interface NotionPage {
  id: string
  title: string
  url?: string
  last_edited_time?: string | null
  object_type?: string
  parent_id?: string | null
  properties?: { name: string; type: string; value: string }[]
  children?: NotionPage[]
}

interface DatabaseEntry {
  id: string
  title: string
  properties: Record<string, any>
}

interface DatabaseData {
  database_id?: string
  title?: string
  columns?: string[]
  entries?: DatabaseEntry[]
  total?: number
  error?: string
}

interface NotionPageContentState {
  content?: string
  attachments?: { id?: string; type: string; name?: string; url?: string | null }[]
  loading?: boolean
  error?: string | null
  isDatabase?: boolean
  database?: DatabaseData
  childDatabases?: DatabaseData[]
}

type PipelineSource = 'slack' | 'gmail' | 'notion'

export default function PipelinesInterface() {
  const [activeSource, setActiveSource] = useState<PipelineSource>('slack')

  // Slack state
  const [slackStats, setSlackStats] = useState<SlackPipelineStats | null>(null)
  const [channels, setChannels] = useState<SlackChannel[]>([])
  const [selectedChannelId, setSelectedChannelId] = useState<string | null>(null)
  const [slackRunId, setSlackRunId] = useState<string | null>(null)
  const [slackRunStatus, setSlackRunStatus] = useState<string | null>(null)
  const [slackIsRunning, setSlackIsRunning] = useState(false)
  const [slackListRefreshing, setSlackListRefreshing] = useState(false)
  const [slackListProgress, setSlackListProgress] = useState<number | null>(null)
  const [slackListRunId, setSlackListRunId] = useState<string | null>(null)
  const [slackListRunStatus, setSlackListRunStatus] = useState<string | null>(null)
  const [slackChannelRunId, setSlackChannelRunId] = useState<string | null>(null)
  const [slackChannelRunChannelId, setSlackChannelRunChannelId] = useState<string | null>(null)
  const [slackChannelRunStatus, setSlackChannelRunStatus] = useState<string | null>(null)
  const [slackChannelProgress, setSlackChannelProgress] = useState<number | null>(null)
  const [slackMessages, setSlackMessages] = useState<SlackMessage[]>([])
  // Channel list search
  const [slackSearchQuery, setSlackSearchQuery] = useState('')
  // Messages pane search (independent from channel search)
  const [slackMessageSearchQuery, setSlackMessageSearchQuery] = useState('')
  const [slackLastRunAt, setSlackLastRunAt] = useState<string | null>(null)

  // Gmail state
  const [gmailLabels, setGmailLabels] = useState<GmailLabel[]>([])
  const [selectedLabelId, setSelectedLabelId] = useState<string | ''>('')
  const [gmailRunId, setGmailRunId] = useState<string | null>(null)
  const [gmailRunStatus, setGmailRunStatus] = useState<string | null>(null)
  const [gmailIsRunning, setGmailIsRunning] = useState(false)
  const [gmailMessages, setGmailMessages] = useState<GmailMessage[]>([])
  const [gmailSearchQuery, setGmailSearchQuery] = useState('')
  const [gmailLastRunAt, setGmailLastRunAt] = useState<string | null>(null)

  // Notion state
  const [notionRunId, setNotionRunId] = useState<string | null>(null)
  const [notionRunStatus, setNotionRunStatus] = useState<string | null>(null)
  const [notionIsRunning, setNotionIsRunning] = useState(false)
  const [notionPages, setNotionPages] = useState<NotionPage[]>([])
  const [notionSearchQuery, setNotionSearchQuery] = useState('')
  const [notionWorkspaceName, setNotionWorkspaceName] = useState('')
  const [notionPageContent, setNotionPageContent] = useState<Record<string, NotionPageContentState>>({})
  const [notionLastRunAt, setNotionLastRunAt] = useState<string | null>(null)

  // Shared error
  const [error, setError] = useState<string | null>(null)

  const slackMessagesEndRef = useRef<HTMLDivElement | null>(null)
  const gmailMessagesEndRef = useRef<HTMLDivElement | null>(null)
  const slackMessagesContainerRef = useRef<HTMLDivElement | null>(null)
  const gmailMessagesContainerRef = useRef<HTMLDivElement | null>(null)
  // Snapshots to restore on cancel
  const prevChannelsRef = useRef<SlackChannel[]>([])
  const prevSlackStatsRef = useRef<SlackPipelineStats | null>(null)
  const prevChannelMessagesRef = useRef<Record<string, SlackMessage[]>>({})

  const handleRefreshChannelList = async () => {
    try {
      setError(null)
      // snapshot for rollback
      prevChannelsRef.current = channels
      prevSlackStatsRef.current = slackStats
      setSlackListRefreshing(true)
      setSlackListProgress(0)
      setSlackListRunStatus('starting')
      const params = new URLSearchParams({
        include_archived: 'false',
      })
      const response = await fetch(
        `${API_BASE_URL}/api/pipelines/slack/channels/refresh?${params.toString()}`,
        {
          method: 'POST',
          credentials: 'include',
        },
      )
      if (!response.ok) {
        throw new Error(`Failed to refresh channel list: ${response.status}`)
      }
      const data = await response.json()
      const runId = data.run_id as string
      setSlackListRunId(runId)
      setSlackListRunStatus(data.status || 'started')
      pollSlackListRunStatus(runId)
    } catch (err: any) {
      console.error('Error refreshing channel list:', err)
      setError(err.message || 'Failed to refresh channel list')
    } finally {
      // leave refreshing flag to poller to clear on completion
    }
  }

  const handleStopSlackChannel = async () => {
    if (!slackChannelRunId) return
    try {
      setSlackChannelRunStatus('cancelling')
      await fetch(`${API_BASE_URL}/api/pipelines/slack/channel/stop/${encodeURIComponent(slackChannelRunId)}`, {
        method: 'POST',
        credentials: 'include',
      })
      // UI rollback immediately; backend will also transition to cancelled
      const prev = slackChannelRunChannelId ? prevChannelMessagesRef.current[slackChannelRunChannelId] : undefined
      if (prev && slackChannelRunChannelId === selectedChannelId) {
        setSlackMessages(prev)
      }
      setSlackChannelProgress(null)
    } catch (err: any) {
      console.error('Error stopping Slack channel refresh:', err)
      setError(err.message || 'Failed to stop channel refresh')
    }
  }

  const handleStopChannelList = async () => {
    if (!slackListRunId) return
    try {
      setSlackListRunStatus('cancelling')
      await fetch(`${API_BASE_URL}/api/pipelines/slack/channels/stop/${encodeURIComponent(slackListRunId)}`, {
        method: 'POST',
        credentials: 'include',
      })
      // rollback immediately
      setChannels(prevChannelsRef.current)
      setSlackStats(prevSlackStatsRef.current)
      setSlackListProgress(null)
    } catch (err: any) {
      console.error('Error stopping channel list refresh:', err)
      setError(err.message || 'Failed to stop channel list refresh')
    }
  }

  const pollSlackListRunStatus = async (id: string) => {
    let done = false
    while (!done) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/pipelines/slack/status/${id}`, {
          credentials: 'include',
        })
        if (!response.ok) {
          throw new Error(`Failed to fetch channel-list run status: ${response.status}`)
        }
        const data = await response.json()
        setSlackListRunStatus(data.status)
        const progressVal =
          data?.stats?.progress != null ? Math.min(1, Math.max(0, data.stats.progress)) : null
        setSlackListProgress(progressVal)

        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          done = true
          setSlackListRefreshing(false)
          setSlackIsRunning(false)
          setSlackListProgress(progressVal ?? 1)
          if (data.status === 'completed') {
            await fetchSlackData()
          } else {
            // rollback
            setChannels(prevChannelsRef.current)
            setSlackStats(prevSlackStatsRef.current)
          }
          setSlackListRunId(null)
          setSlackListRunStatus(data.status)
        } else {
          await new Promise((resolve) => setTimeout(resolve, 2000))
        }
      } catch (err: any) {
        console.error('Error polling Slack channel-list status:', err)
        setError(err.message || 'Failed to poll channel list status')
        setSlackListRefreshing(false)
        done = true
      }
    }
  }

  // Restore persisted Pipelines UI state on mount
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const raw = window.localStorage.getItem('workforce-pipelines-ui')
      if (!raw) return
      const stored = JSON.parse(raw)

      if (stored.activeSource === 'slack' || stored.activeSource === 'gmail' || stored.activeSource === 'notion') {
        setActiveSource(stored.activeSource)
      }
      if (typeof stored.selectedChannelId === 'string') {
        setSelectedChannelId(stored.selectedChannelId)
      }
      if (typeof stored.selectedLabelId === 'string') {
        setSelectedLabelId(stored.selectedLabelId)
      }
      if (typeof stored.slackSearchQuery === 'string') {
        setSlackSearchQuery(stored.slackSearchQuery)
      }
      if (typeof stored.slackMessageSearchQuery === 'string') {
        setSlackMessageSearchQuery(stored.slackMessageSearchQuery)
      }
      if (typeof stored.gmailSearchQuery === 'string') {
        setGmailSearchQuery(stored.gmailSearchQuery)
      }
      if (typeof stored.notionSearchQuery === 'string') {
        setNotionSearchQuery(stored.notionSearchQuery)
      }
      if (typeof stored.slackLastRunAt === 'string') {
        setSlackLastRunAt(stored.slackLastRunAt)
      }
      if (typeof stored.gmailLastRunAt === 'string') {
        setGmailLastRunAt(stored.gmailLastRunAt)
      }
      if (typeof stored.notionLastRunAt === 'string') {
        setNotionLastRunAt(stored.notionLastRunAt)
      }
    } catch (err) {
      console.error('Failed to restore pipelines UI state', err)
    }
  }, [])

  // Persist Pipelines UI state when key fields change
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const payload = {
        activeSource,
        selectedChannelId,
        selectedLabelId,
        slackSearchQuery,
        slackMessageSearchQuery,
        gmailSearchQuery,
        notionSearchQuery,
        slackLastRunAt,
        gmailLastRunAt,
        notionLastRunAt,
      }
      window.localStorage.setItem('workforce-pipelines-ui', JSON.stringify(payload))
    } catch (err) {
      console.error('Failed to persist pipelines UI state', err)
    }
  }, [
    activeSource,
    selectedChannelId,
    selectedLabelId,
    slackSearchQuery,
    slackMessageSearchQuery,
    gmailSearchQuery,
    notionSearchQuery,
    slackLastRunAt,
    gmailLastRunAt,
    notionLastRunAt,
  ])

  // -----------------------------
  // Slack helpers
  // -----------------------------

  const fetchSlackData = async () => {
    try {
      setError(null)
      const response = await fetch(`${API_BASE_URL}/api/pipelines/slack/data`, {
        credentials: 'include',
      })
      if (!response.ok) {
        throw new Error(`Failed to load Slack data: ${response.status}`)
      }
      const data = await response.json()
      setSlackStats(data.stats || null)
      setChannels(data.channels || [])
      if (!selectedChannelId && data.channels && data.channels.length > 0) {
        setSelectedChannelId(data.channels[0].channel_id)
      }
    } catch (err: any) {
      console.error('Error loading Slack pipeline data:', err)
      setError(err.message || 'Failed to load Slack data')
    }
  }

  const pollSlackChannelRunStatus = async (id: string) => {
    let done = false
    while (!done) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/pipelines/slack/channel/status/${id}`, {
          credentials: 'include',
        })
        if (!response.ok) {
          throw new Error(`Failed to fetch channel run status: ${response.status}`)
        }
        const data = await response.json()
        setSlackChannelRunStatus(data.status)
        const progressVal =
          data?.stats?.progress != null ? Math.min(1, Math.max(0, data.stats.progress)) : null
        setSlackChannelProgress(progressVal)

        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          done = true
          setSlackIsRunning(false)
          if (data.finished_at || data.started_at) {
            setSlackLastRunAt(data.finished_at || data.started_at)
          } else {
            setSlackLastRunAt(new Date().toISOString())
          }
          if (data.status === 'completed') {
            await fetchSlackData()
            if (selectedChannelId) {
              await fetchSlackMessages(selectedChannelId)
            }
          } else {
            // rollback messages for that channel
            const prev = slackChannelRunChannelId ? prevChannelMessagesRef.current[slackChannelRunChannelId] : undefined
            if (prev && slackChannelRunChannelId === selectedChannelId) {
              setSlackMessages(prev)
            }
          }
          setSlackChannelRunId(null)
          setSlackChannelRunChannelId(null)
          setSlackChannelProgress(null)
        } else {
          await new Promise((resolve) => setTimeout(resolve, 2000))
        }
      } catch (err: any) {
        console.error('Error polling Slack channel pipeline status:', err)
        setError(err.message || 'Failed to poll channel run status')
        setSlackIsRunning(false)
        done = true
      }
    }
  }

  const handleRunSlackChannel = async (channelId: string) => {
    try {
      setError(null)
      setSlackIsRunning(true)
      setSlackChannelRunChannelId(channelId)
      prevChannelMessagesRef.current[channelId] = slackMessages
      setSlackChannelRunStatus('starting')
      setSlackChannelProgress(null)

      const params = new URLSearchParams({
        channel_id: channelId,
        include_threads: 'false',
        lookback_hours: '24',
      })

      const response = await fetch(`${API_BASE_URL}/api/pipelines/slack/channel/run?${params.toString()}`, {
        method: 'POST',
        credentials: 'include',
      })

      if (!response.ok) {
        throw new Error(`Failed to start Slack channel refresh: ${response.status}`)
      }

      const data = await response.json()
      const newRunId = data.run_id as string
      setSlackChannelRunId(newRunId)
      setSlackChannelRunStatus(data.status || 'started')

      pollSlackChannelRunStatus(newRunId)
    } catch (err: any) {
      console.error('Error starting Slack channel refresh:', err)
      setError(err.message || 'Failed to start Slack channel refresh')
      setSlackIsRunning(false)
    }
  }

  const fetchSlackMessages = async (channelId: string) => {
    try {
      setError(null)
      const response = await fetch(
        `${API_BASE_URL}/api/pipelines/slack/messages?channel_id=${encodeURIComponent(channelId)}&limit=200`,
        {
          credentials: 'include',
        },
      )
      if (!response.ok) {
        throw new Error(`Failed to load Slack messages: ${response.status}`)
      }
      const data = await response.json()
      setSlackMessages(data.messages || [])
    } catch (err: any) {
      console.error('Error loading Slack messages:', err)
      setError(err.message || 'Failed to load Slack messages')
    }
  }

  const pollSlackRunStatus = async (id: string) => {
    let done = false
    while (!done) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/pipelines/slack/status/${id}`, {
          credentials: 'include',
        })
        if (!response.ok) {
          throw new Error(`Failed to fetch run status: ${response.status}`)
        }
        const data = await response.json()
        setSlackRunStatus(data.status)

        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          done = true
          setSlackIsRunning(false)
          if (data.finished_at || data.started_at) {
            setSlackLastRunAt(data.finished_at || data.started_at)
          } else {
            setSlackLastRunAt(new Date().toISOString())
          }
          await fetchSlackData()
          if (selectedChannelId) {
            await fetchSlackMessages(selectedChannelId)
          }
        } else {
          await new Promise((resolve) => setTimeout(resolve, 2000))
        }
      } catch (err: any) {
        console.error('Error polling Slack pipeline status:', err)
        setError(err.message || 'Failed to poll run status')
        setSlackIsRunning(false)
        done = true
      }
    }
  }

  const handleRunSlackPipeline = async () => {
    try {
      setError(null)
      setSlackIsRunning(true)
      setSlackRunStatus('starting')

      const response = await fetch(`${API_BASE_URL}/api/pipelines/slack/run`, {
        method: 'POST',
        credentials: 'include',
      })

      if (!response.ok) {
        throw new Error(`Failed to start Slack pipeline: ${response.status}`)
      }

      const data = await response.json()
      const newRunId = data.run_id as string
      setSlackRunId(newRunId)
      setSlackRunStatus(data.status || 'started')

      pollSlackRunStatus(newRunId)
    } catch (err: any) {
      console.error('Error starting Slack pipeline:', err)
      setError(err.message || 'Failed to start Slack pipeline')
      setSlackIsRunning(false)
    }
  }

  const handleStopSlackPipeline = async () => {
    if (!slackRunId) return
    try {
      setError(null)
      await fetch(
        `${API_BASE_URL}/api/pipelines/slack/stop/${encodeURIComponent(slackRunId)}`,
        {
          method: 'POST',
          credentials: 'include',
        },
      )
    } catch (err: any) {
      console.error('Error stopping Slack pipeline:', err)
      setError(err.message || 'Failed to stop Slack pipeline')
    }
  }

  const selectedChannel = channels.find((ch) => ch.channel_id === selectedChannelId) || null

  // Slack channel search (left column)
  const slackChannelSearch = slackSearchQuery.trim().toLowerCase()
  const filteredChannels = slackChannelSearch
    ? channels.filter((ch) => {
        const name = (ch.name || ch.channel_id || '').toLowerCase()
        return name.includes(slackChannelSearch)
      })
    : channels

  // Slack message search (right column) - independent from channel search
  const slackMessageSearch = slackMessageSearchQuery.trim().toLowerCase()
  const filteredSlackMessages = slackMessageSearch
    ? slackMessages.filter((msg) => {
        const parts = [msg.user_name, msg.user_id, msg.text]
        const haystack = parts
          .filter((p) => p && p !== '')
          .join(' ')
          .toLowerCase()
        return haystack.includes(slackMessageSearch)
      })
    : slackMessages

  const groupedSlackThreads = (() => {
    const threads: Record<string, { root: SlackMessage | null; replies: SlackMessage[] }> = {}
    const sortedMessages = [...filteredSlackMessages].sort((a, b) => a.timestamp - b.timestamp)
    for (const msg of sortedMessages) {
      const key = msg.thread_ts != null ? String(msg.thread_ts) : String(msg.timestamp)
      if (!threads[key]) {
        threads[key] = { root: null, replies: [] }
      }
      if (msg.thread_ts && msg.thread_ts === msg.timestamp) {
        threads[key].root = msg
      } else if (!msg.thread_ts) {
        // Non-threaded message acts as its own root
        threads[key].root = msg
      } else {
        threads[key].replies.push(msg)
      }
    }
    return threads
  })()

  // -----------------------------
  // Gmail helpers
  // -----------------------------

  const fetchGmailLabels = async () => {
    try {
      setError(null)
      const response = await fetch(`${API_BASE_URL}/api/pipelines/gmail/labels`, {
        credentials: 'include',
      })
      if (!response.ok) {
        throw new Error(`Failed to load Gmail labels: ${response.status}`)
      }
      const data = await response.json()
      setGmailLabels(data.labels || [])
      if (!selectedLabelId && data.labels && data.labels.length > 0) {
        setSelectedLabelId(data.labels[0].id)
      }
    } catch (err: any) {
      console.error('Error loading Gmail labels:', err)
      setError(err.message || 'Failed to load Gmail labels')
    }
  }

  const fetchGmailMessagesForLabel = async (labelId: string) => {
    if (!labelId) {
      setGmailMessages([])
      return
    }

    try {
      setError(null)
      const params = new URLSearchParams({ label_id: labelId })
      const response = await fetch(
        `${API_BASE_URL}/api/pipelines/gmail/messages/by-label?${params.toString()}`,
        {
          credentials: 'include',
        },
      )
      if (!response.ok) {
        throw new Error(`Failed to load Gmail messages: ${response.status}`)
      }
      const data = await response.json()
      setGmailMessages(data.messages || [])
    } catch (err: any) {
      console.error('Error loading Gmail messages for label:', err)
      setError(err.message || 'Failed to load Gmail messages for label')
      setGmailMessages([])
    }
  }

  const pollGmailRunStatus = async (id: string) => {
    let done = false
    while (!done) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/pipelines/gmail/status/${id}`, {
          credentials: 'include',
        })
        if (!response.ok) {
          throw new Error(`Failed to fetch Gmail run status: ${response.status}`)
        }
        const data = await response.json()
        setGmailRunStatus(data.status)

        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          done = true
          setGmailIsRunning(false)
          if (data.finished_at || data.started_at) {
            setGmailLastRunAt(data.finished_at || data.started_at)
          } else {
            setGmailLastRunAt(new Date().toISOString())
          }

          const messagesResp = await fetch(
            `${API_BASE_URL}/api/pipelines/gmail/messages?run_id=${encodeURIComponent(id)}`,
            {
              credentials: 'include',
            },
          )
          if (messagesResp.ok) {
            const messagesData = await messagesResp.json()
            setGmailMessages(messagesData.messages || [])
          }
        } else {
          await new Promise((resolve) => setTimeout(resolve, 2000))
        }
      } catch (err: any) {
        console.error('Error polling Gmail pipeline status:', err)
        setError(err.message || 'Failed to poll Gmail run status')
        setGmailIsRunning(false)
        done = true
      }
    }
  }

  const handleRunGmailPipeline = async () => {
    if (!selectedLabelId) {
      setError('Please select a Gmail label first')
      return
    }

    try {
      setError(null)
      setGmailIsRunning(true)
      setGmailRunStatus('starting')

      const params = new URLSearchParams({ label_id: selectedLabelId })
      const response = await fetch(`${API_BASE_URL}/api/pipelines/gmail/run?${params.toString()}`, {
        method: 'POST',
        credentials: 'include',
      })

      if (!response.ok) {
        throw new Error(`Failed to start Gmail pipeline: ${response.status}`)
      }

      const data = await response.json()
      const newRunId = data.run_id as string
      setGmailRunId(newRunId)
      setGmailRunStatus(data.status || 'started')
      setGmailMessages([])

      pollGmailRunStatus(newRunId)
    } catch (err: any) {
      console.error('Error starting Gmail pipeline:', err)
      setError(err.message || 'Failed to start Gmail pipeline')
      setGmailIsRunning(false)
    }
  }

  const handleStopGmailPipeline = async () => {
    if (!gmailRunId) return
    try {
      setError(null)
      await fetch(`${API_BASE_URL}/api/pipelines/gmail/stop/${encodeURIComponent(gmailRunId)}`, {
        method: 'POST',
        credentials: 'include',
      })
    } catch (err: any) {
      console.error('Error stopping Gmail pipeline:', err)
      setError(err.message || 'Failed to stop Gmail pipeline')
    }
  }

  // -----------------------------
  // Notion helpers
  // -----------------------------

  const pollNotionRunStatus = async (id: string) => {
    let done = false
    while (!done) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/pipelines/notion/status/${id}`, {
          credentials: 'include',
        })
        if (!response.ok) {
          throw new Error(`Failed to fetch Notion run status: ${response.status}`)
        }
        const data = await response.json()
        setNotionRunStatus(data.status)

        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          done = true
          setNotionIsRunning(false)
          if (data.finished_at || data.started_at) {
            setNotionLastRunAt(data.finished_at || data.started_at)
          } else {
            setNotionLastRunAt(new Date().toISOString())
          }
          // Refresh hierarchy from the database so the view reflects
          // persisted pages grouped by parent/child relationships.
          await fetchNotionHierarchy()
        } else {
          await new Promise((resolve) => setTimeout(resolve, 2000))
        }
      } catch (err: any) {
        console.error('Error polling Notion pipeline status:', err)
        setError(err.message || 'Failed to poll Notion run status')
        setNotionIsRunning(false)
        done = true
      }
    }
  }

  const handleRunNotionPipeline = async () => {
    try {
      setError(null)
      setNotionIsRunning(true)
      setNotionRunStatus('starting')

      const response = await fetch(`${API_BASE_URL}/api/pipelines/notion/run`, {
        method: 'POST',
        credentials: 'include',
      })

      if (!response.ok) {
        throw new Error(`Failed to start Notion pipeline: ${response.status}`)
      }

      const data = await response.json()
      const newRunId = data.run_id as string
      setNotionRunId(newRunId)
      setNotionRunStatus(data.status || 'started')
      setNotionPages([])

      pollNotionRunStatus(newRunId)
    } catch (err: any) {
      console.error('Error starting Notion pipeline:', err)
      setError(err.message || 'Failed to start Notion pipeline')
      setNotionIsRunning(false)
    }
  }

  const handleStopNotionPipeline = async () => {
    if (!notionRunId) return
    try {
      setError(null)
      await fetch(
        `${API_BASE_URL}/api/pipelines/notion/stop/${encodeURIComponent(notionRunId)}`,
        {
          method: 'POST',
          credentials: 'include',
        },
      )
    } catch (err: any) {
      console.error('Error stopping Notion pipeline:', err)
      setError(err.message || 'Failed to stop Notion pipeline')
    }
  }

  // -----------------------------
  // Initial data - load only active source for speed
  // -----------------------------

  // Track which sources have been loaded to avoid re-fetching
  const [loadedSources, setLoadedSources] = useState<Set<PipelineSource>>(() => new Set())

  useEffect(() => {
    // Only load data for the active source if not already loaded
    if (loadedSources.has(activeSource)) return

    const loadData = async () => {
      if (activeSource === 'slack') {
        await fetchSlackData()
      } else if (activeSource === 'gmail') {
        await fetchGmailLabels()
      } else if (activeSource === 'notion') {
        await fetchNotionHierarchy()
      }
      setLoadedSources((prev) => new Set([...prev, activeSource]))
    }

    loadData()
  }, [activeSource, loadedSources])

  useEffect(() => {
    if (!selectedLabelId) {
      setGmailMessages([])
      return
    }
    fetchGmailMessagesForLabel(selectedLabelId)
  }, [selectedLabelId])

  useEffect(() => {
    const container = slackMessagesContainerRef.current
    if (!container || slackMessages.length === 0 || !slackMessagesEndRef.current) return

    const threshold = 80
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight
    if (distanceFromBottom <= threshold) {
      slackMessagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [slackMessages.length, selectedChannelId])

  useEffect(() => {
    const container = gmailMessagesContainerRef.current
    if (!container || gmailMessages.length === 0 || !gmailMessagesEndRef.current) return

    const threshold = 80
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight
    if (distanceFromBottom <= threshold) {
      gmailMessagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [gmailMessages.length, gmailRunId])

  const fetchNotionHierarchy = async () => {
    try {
      setError(null)
      const response = await fetch(`${API_BASE_URL}/api/notion/hierarchy`, {
        credentials: 'include',
      })
      if (!response.ok) {
        throw new Error(`Failed to load Notion hierarchy: ${response.status}`)
      }
      const data = await response.json()
      setNotionWorkspaceName(data.workspace_name || 'Notion Workspace')
      setNotionPages(data.pages || [])
    } catch (err: any) {
      console.error('Error loading Notion hierarchy:', err)
      setError(err.message || 'Failed to load Notion hierarchy')
    }
  }

  const fetchNotionPageContent = async (pageId: string) => {
    setNotionPageContent((prev) => {
      const existing = prev[pageId]
      if (existing?.loading) {
        return prev
      }
      return {
        ...prev,
        [pageId]: {
          ...existing,
          loading: true,
          error: null,
        },
      }
    })

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/notion/page-content?page_id=${encodeURIComponent(pageId)}&include_databases=true`,
        {
          credentials: 'include',
        },
      )
      if (!response.ok) {
        throw new Error(`Failed to load Notion page content: ${response.status}`)
      }
      const data = await response.json()
      setNotionPageContent((prev) => ({
        ...prev,
        [pageId]: {
          content: data.content || '',
          attachments: data.attachments || [],
          loading: false,
          error: null,
          isDatabase: data.is_database || false,
          database: data.database || null,
          childDatabases: data.child_databases || [],
        },
      }))
    } catch (err: any) {
      console.error('Error loading Notion page content:', err)
      setNotionPageContent((prev) => ({
        ...prev,
        [pageId]: {
          ...(prev[pageId] || {}),
          loading: false,
          error: err.message || 'Failed to load Notion page content',
        },
      }))
    }
  }

  // -----------------------------
  // Render helpers
  // -----------------------------

  const renderSlackView = () => {
    const channelProgressDisplay =
      slackChannelRunStatus || slackChannelProgress != null
        ? `Refresh status: ${slackChannelRunStatus || 'running'}${
            slackChannelProgress != null ? ` · ${(slackChannelProgress * 100).toFixed(0)}%` : ''
          }`
        : null

    const channelListProgressDisplay =
      slackListRefreshing || slackListRunStatus || slackListProgress != null
        ? `${slackListRunStatus || 'running'}${
            slackListProgress != null ? ` · ${(slackListProgress * 100).toFixed(0)}%` : ''
          }`
        : null

    return (
      <>
        <div className="w-80 border-r border-border bg-card p-4 flex flex-col gap-4">
          <div>
            <h2 className="text-lg font-semibold mb-2">Slack Pipeline</h2>
            <p className="text-sm text-muted-foreground mb-3">
              Manually sync Slack workspace history (users, channels, messages, files) into the
              database.
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleRunSlackPipeline}
                disabled={slackIsRunning}
                className="inline-flex items-center justify-center rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {slackIsRunning ? 'Running…' : 'Run Slack Pipeline'}
              </button>
              {slackIsRunning && slackRunId && (
                <button
                  type="button"
                  onClick={handleStopSlackPipeline}
                  className="inline-flex items-center justify-center rounded-md bg-red-600 px-2 py-1 text-xs font-medium text-white shadow-sm hover:bg-red-700"
                >
                  Stop
                </button>
              )}
            </div>
            {slackRunStatus && (
              <p className="mt-2 text-xs text-muted-foreground">
                Run status: <span className="font-medium">{slackRunStatus}</span>
              </p>
            )}
            {slackRunId && (
              <p className="mt-1 text-[11px] text-muted-foreground break-all">Run ID: {slackRunId}</p>
            )}
            {channelProgressDisplay && (
              <p className="mt-1 text-[11px] text-muted-foreground">{channelProgressDisplay}</p>
            )}
          </div>

          {slackStats && (
            <div className="mt-2 rounded-md border border-border bg-background p-3">
              <h3 className="text-sm font-semibold mb-2">Slack Stats</h3>
              <dl className="grid grid-cols-2 gap-1 text-xs">
                <div>
                  <dt className="text-muted-foreground">Users</dt>
                  <dd className="font-medium">{slackStats.users}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Channels</dt>
                  <dd className="font-medium">{slackStats.channels}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Messages</dt>
                  <dd className="font-medium">{slackStats.messages}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Files</dt>
                  <dd className="font-medium">{slackStats.files}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Reactions</dt>
                  <dd className="font-medium">{slackStats.reactions}</dd>
                </div>
              </dl>
              {slackLastRunAt && (
                <p className="mt-2 text-[11px] text-muted-foreground">
                  Last run: {new Date(slackLastRunAt).toLocaleString()}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="flex-1 p-4 overflow-hidden flex flex-col">
          <div className="flex items-center justify-between mb-3 gap-2">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold">Slack Channels</h2>
              {channelListProgressDisplay && (
                <span className="text-[11px] text-muted-foreground">
                  {channelListProgressDisplay}
                  {slackListRunId ? ` · run ${slackListRunId.slice(0, 8)}` : ''}
                </span>
              )}
              {!channelListProgressDisplay && slackListRunStatus && (
                <span className="text-[11px] text-muted-foreground">
                  Status: {slackListRunStatus}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {slackListRefreshing && (
                <button
                  type="button"
                  onClick={handleStopChannelList}
                  className="inline-flex items-center justify-center rounded-md bg-red-600 px-2.5 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-red-700 disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  Stop
                </button>
              )}
              <button
                type="button"
                onClick={handleRefreshChannelList}
                disabled={slackListRefreshing || slackIsRunning}
                className="inline-flex items-center justify-center rounded-md bg-blue-600 px-2.5 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {slackListRefreshing
                  ? `Refreshing ${slackListProgress != null ? `${(slackListProgress * 100).toFixed(0)}%` : '…'}`
                  : 'Refresh channel list'}
              </button>
            </div>
          </div>
          <div className="flex-1 flex overflow-hidden gap-4">
            <div className="w-80 border border-border rounded-md bg-card flex flex-col">
              <div className="p-2 border-b border-border flex items-center gap-2">
                <input
                  type="text"
                  value={slackSearchQuery}
                  onChange={(e) => setSlackSearchQuery(e.target.value)}
                  placeholder="Search channels and messages"
                  className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-xs"
                />
                <span className="text-[11px] text-muted-foreground whitespace-nowrap">
                  {filteredChannels.length} channels
                </span>
              </div>
              <div className="flex-1 overflow-auto">
                <table className="min-w-full text-xs">
                  <thead className="bg-muted">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium text-muted-foreground">Channel</th>
                      <th className="px-3 py-2 text-right font-medium text-muted-foreground">Messages</th>
                      <th className="px-3 py-2 text-right font-medium text-muted-foreground">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredChannels.map((ch) => (
                      <tr
                        key={ch.channel_id}
                        className={
                          'border-b border-border/60 hover:bg-muted ' +
                          (selectedChannelId === ch.channel_id ? 'bg-muted/80' : '')
                        }
                      >
                        <td
                          className="px-3 py-2 align-top cursor-pointer"
                          onClick={() => {
                            setSelectedChannelId(ch.channel_id)
                            fetchSlackMessages(ch.channel_id)
                          }}
                        >
                          <div className="font-medium text-foreground text-xs">
                            {ch.name || ch.channel_id}
                            {ch.is_private && (
                              <span className="ml-1 text-[10px] text-yellow-400">(private)</span>
                            )}
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            {ch.num_members != null ? `${ch.num_members} members` : 'Members unknown'}
                            {ch.is_archived && (
                              <span className="ml-1 text-[10px] text-red-400">archived</span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2 text-right align-top text-xs">{ch.message_count}</td>
                        <td className="px-3 py-2 text-right align-top space-x-1">
                          {slackChannelRunId && slackChannelRunChannelId === ch.channel_id ? (
                            <>
                              <button
                                type="button"
                                onClick={handleStopSlackChannel}
                                className="inline-flex items-center justify-center rounded-md bg-red-600 px-2 py-1 text-[11px] font-medium text-white shadow-sm hover:bg-red-700"
                              >
                                Stop
                              </button>
                              <span className="text-[11px] text-muted-foreground">
                                {slackChannelProgress != null ? `${(slackChannelProgress * 100).toFixed(0)}%` : '...'}
                              </span>
                            </>
                          ) : (
                            <button
                              type="button"
                              onClick={() => handleRunSlackChannel(ch.channel_id)}
                              disabled={slackIsRunning}
                              className="inline-flex items-center justify-center rounded-md bg-blue-600 px-2 py-1 text-[11px] font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
                            >
                              Refresh
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {filteredChannels.length === 0 && (
                      <tr>
                        <td colSpan={3} className="px-3 py-4 text-center text-xs text-muted-foreground">
                          No Slack channels match this search.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div
              className="flex-1 border border-border rounded-md bg-card p-4 overflow-auto"
              ref={slackMessagesContainerRef}
            >
              {selectedChannel ? (
                <div className="flex flex-col h-full">
                  <div className="mb-3">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <h3 className="text-base font-semibold">Channel Details</h3>
                      {slackChannelRunChannelId === selectedChannel?.channel_id && (
                        <div className="flex items-center gap-2 text-[11px]">
                          <span className="text-muted-foreground">
                            {slackChannelRunStatus || 'running'}
                            {slackChannelProgress != null ? ` · ${(slackChannelProgress * 100).toFixed(0)}%` : ''}
                          </span>
                          <button
                            type="button"
                            onClick={handleStopSlackChannel}
                            className="inline-flex items-center justify-center rounded-md bg-red-600 px-2 py-1 text-[11px] font-medium text-white shadow-sm hover:bg-red-700"
                          >
                            Stop
                          </button>
                        </div>
                      )}
                    </div>
                    <p className="text-sm mb-1">
                      <span className="font-mono text-sm">
                        {selectedChannel.name || selectedChannel.channel_id}
                      </span>
                      {selectedChannel.is_private && (
                        <span className="ml-2 text-xs text-yellow-400">Private</span>
                      )}
                      {selectedChannel.is_archived && (
                        <span className="ml-2 text-xs text-red-400">Archived</span>
                      )}
                    </p>
                    <p className="text-xs text-muted-foreground mb-2">
                      Members:{' '}
                      {selectedChannel.num_members != null ? selectedChannel.num_members : 'Unknown'} ·
                      Messages: {selectedChannel.message_count}
                    </p>
                    {slackChannelRunStatus && (
                      <p className="text-[11px] text-muted-foreground">
                        Refresh status: {slackChannelRunStatus}
                        {slackChannelProgress != null
                          ? ` · ${(slackChannelProgress * 100).toFixed(0)}%`
                          : ''}
                      </p>
                    )}
                  </div>

                  <div className="flex-1 border border-border rounded-md bg-background p-2 flex flex-col">
                    {slackMessages.length === 0 ? (
                      <p className="text-xs text-muted-foreground">
                        No messages loaded for this channel yet. Run the Slack pipeline or select the
                        channel again.
                      </p>
                    ) : (
                      <>
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <input
                            type="text"
                            value={slackMessageSearchQuery}
                            onChange={(e) => setSlackMessageSearchQuery(e.target.value)}
                            placeholder="Filter by text or user"
                            className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-xs"
                          />
                          <span className="text-[11px] text-muted-foreground whitespace-nowrap">
                            {filteredSlackMessages.length} shown / {slackMessages.length} loaded
                          </span>
                        </div>
                        <div className="flex-1 overflow-auto space-y-3">
                          {Object.entries(groupedSlackThreads).map(([key, thread]) => (
                            <div key={key} className="rounded-md border border-border/60 bg-card p-2">
                              {thread.root && (
                                <div className="mb-1">
                                  <div className="flex items-center justify-between gap-2">
                                    <div className="text-xs font-semibold text-foreground">
                                      {thread.root.user_name ||
                                        thread.root.user_id ||
                                        'Unknown user'}
                                    </div>
                                    <div className="text-[10px] text-muted-foreground">
                                      {new Date(thread.root.timestamp * 1000).toLocaleString()}
                                    </div>
                                  </div>
                                  <p className="text-xs text-foreground whitespace-pre-wrap">
                                    {thread.root.text || '[no text]'}
                                  </p>
                                  {thread.root.reply_count ? (
                                    <p className="mt-1 text-[10px] text-muted-foreground">
                                      {thread.root.reply_count} repl
                                      {thread.root.reply_count === 1 ? 'y' : 'ies'}
                                    </p>
                                  ) : null}
                                </div>
                              )}

                              {thread.replies.length > 0 && (
                                <div className="mt-2 border-t border-border/40 pt-2 space-y-1">
                                  {[...thread.replies]
                                    .sort((a, b) => a.timestamp - b.timestamp)
                                    .map((reply) => (
                                      <div
                                        key={reply.message_id}
                                        className="pl-2 border-l border-border/40"
                                      >
                                        <div className="flex items-center justify-between gap-2">
                                          <div className="text-[11px] font-medium text-foreground">
                                            {reply.user_name || reply.user_id || 'Unknown user'}
                                          </div>
                                          <div className="text-[10px] text-muted-foreground">
                                            {new Date(reply.timestamp * 1000).toLocaleString()}
                                          </div>
                                        </div>
                                        <p className="text-[11px] text-foreground whitespace-pre-wrap">
                                          {reply.text || '[no text]'}
                                        </p>
                                      </div>
                                    ))}
                                </div>
                              )}
                            </div>
                          ))}
                          <div ref={slackMessagesEndRef} />
                        </div>
                      </>
                    )}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Select a channel on the left to see details.
                </p>
              )}
            </div>
          </div>
        </div>
      </>
    )
  }

  const renderGmailView = () => {
    const search = gmailSearchQuery.trim().toLowerCase()
    const filteredMessages = search
      ? gmailMessages.filter((msg) => {
          const parts = [
            msg.from,
            msg.to,
            msg.cc,
            msg.bcc,
            msg.subject,
            msg.snippet,
            msg.body_text,
            msg.body_html,
          ]
          const haystack = parts
            .filter((p) => p && p !== '')
            .join(' ')
            .toLowerCase()
          return haystack.includes(search)
        })
      : gmailMessages

    return (
      <>
        <div className="w-80 border-r border-border bg-card p-4 flex flex-col gap-4">
        <div>
          <h2 className="text-lg font-semibold mb-2">Gmail Pipeline</h2>
          <p className="text-sm text-muted-foreground mb-3">
            Incrementally sync emails for a specific label and explore them as accordions.
          </p>

          <label
            htmlFor="gmail-label-select"
            className="block text-xs font-medium text-muted-foreground mb-1"
          >
            Label
          </label>
          <SearchableSelect
            id="gmail-label-select"
            value={selectedLabelId}
            onChange={setSelectedLabelId}
            options={gmailLabels.map((lbl) => ({ value: lbl.id, label: lbl.name }))}
            placeholder="Select a label…"
            searchPlaceholder="Search labels…"
            allowClear
            fullWidth
            containerClassName="mb-2"
          />

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleRunGmailPipeline}
              disabled={gmailIsRunning || !selectedLabelId}
              className="inline-flex items-center justify-center rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {gmailIsRunning ? 'Running…' : 'Run Gmail Pipeline'}
            </button>
            {gmailIsRunning && gmailRunId && (
              <button
                type="button"
                onClick={handleStopGmailPipeline}
                className="inline-flex items-center justify-center rounded-md bg-red-600 px-2 py-1 text-xs font-medium text-white shadow-sm hover:bg-red-700"
              >
                Stop
              </button>
            )}
          </div>
          {gmailRunStatus && (
            <p className="mt-2 text-xs text-muted-foreground">
              Run status: <span className="font-medium">{gmailRunStatus}</span>
            </p>
          )}
          {gmailRunId && (
            <p className="mt-1 text-[11px] text-muted-foreground break-all">Run ID: {gmailRunId}</p>
          )}
          {gmailLastRunAt && (
            <p className="mt-1 text-[11px] text-muted-foreground">
              Last run: {new Date(gmailLastRunAt).toLocaleString()}
            </p>
          )}
        </div>
      </div>

      <div className="flex-1 p-4 overflow-hidden flex flex-col">
        <h2 className="text-lg font-semibold mb-3">Gmail Messages</h2>
        <div
          className="flex-1 overflow-auto border border-border rounded-md bg-card p-2"
          ref={gmailMessagesContainerRef}
        >
          {gmailMessages.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No messages loaded yet. Select a label and run the Gmail pipeline.
            </p>
          ) : (
            <>
              <div className="mb-2 flex items-center justify-between gap-2">
                <input
                  type="text"
                  value={gmailSearchQuery}
                  onChange={(e) => setGmailSearchQuery(e.target.value)}
                  placeholder="Filter by sender, subject, recipients, or body"
                  className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-xs"
                />
                <span className="text-[11px] text-muted-foreground whitespace-nowrap">
                  {filteredMessages.length} shown / {gmailMessages.length} loaded
                </span>
              </div>

              {filteredMessages.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No messages match this search.
                </p>
              ) : (
                <div className="space-y-2">
                  {[...filteredMessages]
                    .sort((a, b) => {
                      const aTime = a.date ? new Date(a.date).getTime() : 0
                      const bTime = b.date ? new Date(b.date).getTime() : 0
                      return aTime - bTime
                    })
                    .map((msg, index, arr) => {
                      const recipients = msg.to || msg.cc || msg.bcc
                      const header = recipients
                        ? `${msg.from || 'Unknown sender'} -> ${recipients} · ${
                            msg.subject || 'No subject'
                          }`
                        : `${msg.from || 'Unknown sender'} · ${msg.subject || 'No subject'}`
                      const dateStr = msg.date ? new Date(msg.date).toLocaleString() : 'Unknown date'
                      const body = msg.body_html || msg.body_text || msg.snippet || '[no content]'
                      const isLatest = index === arr.length - 1
                      const gmailUrl = msg.id ? `https://mail.google.com/mail/u/0/#all/${msg.id}` : null
                      return (
                        <details
                          key={msg.id}
                          open={isLatest}
                          className="rounded-md border border-border/60 bg-background open:bg-card"
                        >
                          <summary className="cursor-pointer px-3 py-2 text-xs flex flex-col gap-0.5">
                            <span className="font-medium text-foreground truncate">{header}</span>
                            <span className="text-[11px] text-muted-foreground">{dateStr}</span>
                          </summary>
                          <div className="px-3 py-2 border-t border-border/40 text-xs text-foreground">
                            {gmailUrl && (
                              <div className="mb-2 flex items-center justify-between gap-2">
                                <span className="text-[11px] text-muted-foreground break-all">ID: {msg.id}</span>
                                <button
                                  type="button"
                                  onClick={() => window.open(gmailUrl, '_blank')}
                                  className="text-[11px] font-medium text-blue-400 hover:underline"
                                >
                                  Open in Gmail
                                </button>
                              </div>
                            )}
                            {msg.body_html ? (
                              <div
                                className="prose prose-invert max-w-none text-xs"
                                dangerouslySetInnerHTML={{ __html: msg.body_html }}
                              />
                            ) : (
                              <pre className="whitespace-pre-wrap text-xs text-foreground">{body}</pre>
                            )}
                          </div>
                        </details>
                      )
                    })}
                  <div ref={gmailMessagesEndRef} />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  )
  }

  const renderNotionTreeNode = (page: NotionPage, depth = 0) => {
    const lastEdited = page.last_edited_time
      ? new Date(page.last_edited_time).toLocaleString()
      : 'Unknown'
    const children = page.children || []
    const pageProps = page.properties || []
    const hasChildren = children.length > 0
    const hasProps = pageProps.length > 0
    const contentState = notionPageContent[page.id]

    const handleToggle = (e: any) => {
      const detailsEl = e.currentTarget as HTMLDetailsElement
      if (detailsEl.open && !contentState?.content && !contentState?.loading) {
        fetchNotionPageContent(page.id)
      }
    }

    return (
      <details
        key={page.id}
        className={`rounded-md border border-border/60 bg-background open:bg-card ${depth > 0 ? 'ml-3' : ''}`}
        onToggle={handleToggle}
      >
        <summary className="cursor-pointer px-3 py-2 text-xs flex flex-col gap-0.5">
          <span className="font-medium text-foreground truncate">{page.title}</span>
          <span className="text-[11px] text-muted-foreground">
            {lastEdited}
            {hasChildren && (
              <>
                {' · '}
                {children.length} subpage
                {children.length === 1 ? '' : 's'}
              </>
            )}
          </span>
        </summary>
        <div className="px-3 py-2 border-t border-border/40 text-xs text-foreground space-y-2">
          {page.url && (
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] text-muted-foreground break-all">ID: {page.id}</span>
              <button
                type="button"
                onClick={() => window.open(page.url as string, '_blank')}
                className="text-[11px] font-medium text-blue-400 hover:underline"
              >
                Open in Notion
              </button>
            </div>
          )}
          {/* Only show Properties for regular pages, not for databases */}
          {hasProps && !contentState?.isDatabase && (
            <div>
              <div className="text-[11px] font-semibold text-muted-foreground mb-0.5">Properties</div>
              <dl className="space-y-0.5">
                {pageProps.slice(0, 8).map((prop: { name: string; type: string; value: string }) => (
                  <div key={prop.name} className="flex items-center justify-between gap-2">
                    <dt className="text-[11px] text-muted-foreground truncate max-w-[40%]">{prop.name}</dt>
                    <dd className="text-[11px] text-foreground text-right truncate max-w-[55%]">
                      {prop.value || '-'}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
          {contentState?.loading && (
            <p className="text-[11px] text-muted-foreground">Loading page content…</p>
          )}
          {!contentState?.loading && contentState?.error && (
            <p className="text-[11px] text-red-400">Failed to load content: {contentState.error}</p>
          )}
          {/* Show database content as table */}
          {!contentState?.loading && contentState?.isDatabase && contentState?.database && (
            <div>
              <div className="text-[11px] font-semibold text-muted-foreground mb-1">
                📊 Database: {contentState.database.title || 'Untitled'} ({contentState.database.total || 0} entries)
              </div>
              {contentState.database.error && (
                <p className="text-[10px] text-amber-500 mb-1">{contentState.database.error}</p>
              )}
              {(contentState.database.entries?.length || 0) > 0 ? (
                <div className="max-h-80 overflow-auto border border-border/40 rounded-md bg-background/40">
                  <table className="w-full text-[10px]">
                    <thead className="bg-muted/50 sticky top-0">
                      <tr>
                        {(contentState.database.columns || []).map((col) => (
                          <th key={col} className="px-2 py-1 text-left font-medium text-muted-foreground border-b border-border/40 whitespace-nowrap">
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(contentState.database.entries || []).map((entry) => (
                        <tr key={entry.id} className="border-b border-border/20 hover:bg-muted/20">
                          {(contentState.database?.columns || []).map((col) => {
                            const val = entry.properties?.[col]
                            let displayVal = '-'
                            if (val !== null && val !== undefined && val !== '') {
                              if (Array.isArray(val)) {
                                displayVal = val.slice(0, 3).join(', ') + (val.length > 3 ? '...' : '')
                              } else if (typeof val === 'number') {
                                displayVal = val >= 1000 ? `$${val.toLocaleString()}` : String(val)
                              } else {
                                displayVal = String(val).slice(0, 80) + (String(val).length > 80 ? '...' : '')
                              }
                            }
                            return (
                              <td key={col} className="px-2 py-1 text-foreground whitespace-nowrap">
                                {displayVal}
                              </td>
                            )
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-[10px] text-muted-foreground">
                  No entries found. This may be a linked database view - ensure the original database is shared with the Notion integration.
                </p>
              )}
            </div>
          )}
          {/* Show child databases */}
          {!contentState?.loading && contentState?.childDatabases && contentState.childDatabases.length > 0 && (
            <div className="space-y-2">
              {contentState.childDatabases.map((db) => (
                <div key={db.database_id || db.title}>
                  <div className="text-[11px] font-semibold text-muted-foreground mb-1">
                    📊 {db.title || 'Database'} ({db.total || 0} entries)
                  </div>
                  {db.error && (
                    <p className="text-[10px] text-amber-500 mb-1">{db.error}</p>
                  )}
                  {(db.entries?.length || 0) > 0 ? (
                    <div className="max-h-64 overflow-auto border border-border/40 rounded-md bg-background/40">
                      <table className="w-full text-[10px]">
                        <thead className="bg-muted/50 sticky top-0">
                          <tr>
                            {(db.columns || []).map((col) => (
                              <th key={col} className="px-2 py-1 text-left font-medium text-muted-foreground border-b border-border/40 whitespace-nowrap">
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {(db.entries || []).map((entry) => (
                            <tr key={entry.id} className="border-b border-border/20 hover:bg-muted/20">
                              {(db.columns || []).map((col) => {
                                const val = entry.properties?.[col]
                                let displayVal = '-'
                                if (val !== null && val !== undefined && val !== '') {
                                  if (Array.isArray(val)) {
                                    displayVal = val.slice(0, 2).join(', ') + (val.length > 2 ? '...' : '')
                                  } else if (typeof val === 'number') {
                                    displayVal = val >= 1000 ? `$${val.toLocaleString()}` : String(val)
                                  } else {
                                    displayVal = String(val).slice(0, 60) + (String(val).length > 60 ? '...' : '')
                                  }
                                }
                                return (
                                  <td key={col} className="px-2 py-1 text-foreground whitespace-nowrap">
                                    {displayVal}
                                  </td>
                                )
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-[10px] text-muted-foreground">
                      No entries found. This may be a linked database - ensure the original is shared with the integration.
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
          {!contentState?.loading && contentState?.content && !contentState?.isDatabase && (
            <div>
              <div className="text-[11px] font-semibold text-muted-foreground mb-0.5">Page content</div>
              <pre className="whitespace-pre-wrap text-[11px] text-foreground max-h-48 overflow-auto border border-border/40 rounded-md p-1.5 bg-background/40">
                {contentState.content}
              </pre>
            </div>
          )}
          {!contentState?.loading && contentState?.attachments && contentState.attachments.length > 0 && (
            <div>
              <div className="text-[11px] font-semibold text-muted-foreground mb-0.5">Attachments</div>
              <ul className="space-y-0.5">
                {contentState.attachments.map((att) => (
                  <li
                    key={att.id || att.name}
                    className="flex items-center justify-between gap-2"
                  >
                    <span className="text-[11px] text-foreground truncate max-w-[60%]">
                      {att.name || att.id || 'Attachment'}
                    </span>
                    {att.url ? (
                      <button
                        type="button"
                        onClick={() => window.open(att.url as string, '_blank')}
                        className="text-[11px] font-medium text-blue-400 hover:underline"
                      >
                        Open
                      </button>
                    ) : (
                      <span className="text-[10px] text-muted-foreground">No URL</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {hasChildren && (
            <div className="mt-1 space-y-1">
              {children.map((child) => renderNotionTreeNode(child, depth + 1))}
            </div>
          )}
          {!hasProps && !hasChildren && !contentState?.content && !contentState?.loading && (
            <p className="text-[11px] text-muted-foreground">No additional information.</p>
          )}
        </div>
      </details>
    )
  }

  const renderNotionView = () => {
    const search = notionSearchQuery.trim().toLowerCase()
    const filteredPages = search
      ? notionPages.filter((page) => page.title.toLowerCase().includes(search))
      : notionPages

    return (
      <>
        <div className="w-80 border-r border-border bg-card p-4 flex flex-col gap-4">
          <div>
            <h2 className="text-lg font-semibold mb-2">Notion Pipeline</h2>
            <p className="text-sm text-muted-foreground mb-3">
              Sync pages and databases that your integration can access in the Notion
              workspace and explore them locally.
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleRunNotionPipeline}
                disabled={notionIsRunning}
                className="inline-flex items-center justify-center rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {notionIsRunning ? 'Running…' : 'Run Notion Pipeline'}
              </button>
              {notionIsRunning && notionRunId && (
                <button
                  type="button"
                  onClick={handleStopNotionPipeline}
                  className="inline-flex items-center justify-center rounded-md bg-red-600 px-2 py-1 text-xs font-medium text-white shadow-sm hover:bg-red-700"
                >
                  Stop
                </button>
              )}
            </div>
            {notionRunStatus && (
              <p className="mt-2 text-xs text-muted-foreground">
                Run status: <span className="font-medium">{notionRunStatus}</span>
              </p>
            )}
            {notionRunId && (
              <p className="mt-1 text-[11px] text-muted-foreground break-all">Run ID: {notionRunId}</p>
            )}
            {notionLastRunAt && (
              <p className="mt-1 text-[11px] text-muted-foreground">
                Last run: {new Date(notionLastRunAt).toLocaleString()}
              </p>
            )}
          </div>
        </div>

        <div className="flex-1 p-4 overflow-hidden flex flex-col">
          <h2 className="text-lg font-semibold mb-1">Notion Pages</h2>
          <p className="text-xs text-muted-foreground mb-2">
            Workspace:{' '}
            <span className="font-medium">{notionWorkspaceName || 'Notion Workspace'}</span>
          </p>
          <div className="mb-2 flex items-center justify-between gap-2">
            <input
              type="text"
              value={notionSearchQuery}
              onChange={(e) => setNotionSearchQuery(e.target.value)}
              placeholder="Filter pages by title"
              className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-xs"
            />
            <span className="text-[11px] text-muted-foreground">{filteredPages.length} pages</span>
          </div>
          <div className="flex-1 overflow-auto border border-border rounded-md bg-card p-2">
            {filteredPages.length === 0 ? (
              <p className="p-3 text-xs text-muted-foreground">
                No pages loaded yet. Run the Notion pipeline to fetch workspace pages.
              </p>
            ) : (
              <div className="space-y-2">
                {filteredPages.map((page) => renderNotionTreeNode(page))}
              </div>
            )}
          </div>
        </div>
      </>
    )
  }

  return (
    <div className="flex h-full bg-background">
      {/* Left: source tabs wrapper is in parent header; here we just render per-source layouts */}
      {activeSource === 'slack' && renderSlackView()}
      {activeSource === 'gmail' && renderGmailView()}
      {activeSource === 'notion' && renderNotionView()}

      {/* Simple local source switcher pinned bottom-left to avoid changing App.tsx header */}
      <div className="fixed bottom-4 left-4 flex gap-2 text-xs">
        <button
          type="button"
          onClick={() => setActiveSource('slack')}
          className={`rounded-md px-2 py-1 border ${
            activeSource === 'slack'
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-card text-foreground border-border hover:bg-muted'
          }`}
        >
          Slack
        </button>
        <button
          type="button"
          onClick={() => setActiveSource('gmail')}
          className={`rounded-md px-2 py-1 border ${
            activeSource === 'gmail'
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-card text-foreground border-border hover:bg-muted'
          }`}
        >
          Gmail
        </button>
        <button
          type="button"
          onClick={() => setActiveSource('notion')}
          className={`rounded-md px-2 py-1 border ${
            activeSource === 'notion'
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-card text-foreground border-border hover:bg-muted'
          }`}
        >
          Notion
        </button>
      </div>

      {error && (
        <div className="fixed bottom-4 right-4 max-w-sm rounded-md border border-red-500/40 bg-red-950/70 p-3 text-xs text-red-100 shadow-lg">
          <div className="flex items-start justify-between gap-2">
            <span className="flex-1">{error}</span>
            <button
              type="button"
              onClick={() => setError(null)}
              className="ml-2 inline-flex h-5 w-5 items-center justify-center rounded-full border border-red-400/60 text-[10px] hover:bg-red-800/80"
              aria-label="Dismiss error"
            >
              ×
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
