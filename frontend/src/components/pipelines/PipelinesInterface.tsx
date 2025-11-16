import { useEffect, useState, useRef } from 'react'

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
  last_edited_time?: string
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
  const [slackMessages, setSlackMessages] = useState<SlackMessage[]>([])
  const [slackSearchQuery, setSlackSearchQuery] = useState('')

  // Gmail state
  const [gmailLabels, setGmailLabels] = useState<GmailLabel[]>([])
  const [selectedLabelId, setSelectedLabelId] = useState<string | ''>('')
  const [gmailRunId, setGmailRunId] = useState<string | null>(null)
  const [gmailRunStatus, setGmailRunStatus] = useState<string | null>(null)
  const [gmailIsRunning, setGmailIsRunning] = useState(false)
  const [gmailMessages, setGmailMessages] = useState<GmailMessage[]>([])

  // Notion state
  const [notionRunId, setNotionRunId] = useState<string | null>(null)
  const [notionRunStatus, setNotionRunStatus] = useState<string | null>(null)
  const [notionIsRunning, setNotionIsRunning] = useState(false)
  const [notionPages, setNotionPages] = useState<NotionPage[]>([])
  const [notionSearchQuery, setNotionSearchQuery] = useState('')

  // Shared error
  const [error, setError] = useState<string | null>(null)

  const slackMessagesEndRef = useRef<HTMLDivElement | null>(null)
  const gmailMessagesEndRef = useRef<HTMLDivElement | null>(null)

  // -----------------------------
  // Slack helpers
  // -----------------------------

  const fetchSlackData = async () => {
    try {
      setError(null)
      const response = await fetch('http://localhost:8000/api/pipelines/slack/data')
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

  const fetchSlackMessages = async (channelId: string) => {
    try {
      setError(null)
      const response = await fetch(
        `http://localhost:8000/api/pipelines/slack/messages?channel_id=${encodeURIComponent(channelId)}&limit=200`,
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
        const response = await fetch(`http://localhost:8000/api/pipelines/slack/status/${id}`)
        if (!response.ok) {
          throw new Error(`Failed to fetch run status: ${response.status}`)
        }
        const data = await response.json()
        setSlackRunStatus(data.status)

        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          done = true
          setSlackIsRunning(false)
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

      const response = await fetch('http://localhost:8000/api/pipelines/slack/run', {
        method: 'POST',
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
      await fetch(`http://localhost:8000/api/pipelines/slack/stop/${encodeURIComponent(slackRunId)}`, {
        method: 'POST',
      })
    } catch (err: any) {
      console.error('Error stopping Slack pipeline:', err)
      setError(err.message || 'Failed to stop Slack pipeline')
    }
  }

  const selectedChannel = channels.find((ch) => ch.channel_id === selectedChannelId) || null

  const groupedSlackThreads = (() => {
    const threads: Record<string, { root: SlackMessage | null; replies: SlackMessage[] }> = {}
    const sortedMessages = [...slackMessages].sort((a, b) => a.timestamp - b.timestamp)
    const search = slackSearchQuery.trim().toLowerCase()
    for (const msg of sortedMessages) {
      if (search && !(msg.text || '').toLowerCase().includes(search)) {
        continue
      }
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
      const response = await fetch('http://localhost:8000/api/pipelines/gmail/labels')
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
        `http://localhost:8000/api/pipelines/gmail/messages/by-label?${params.toString()}`,
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
        const response = await fetch(`http://localhost:8000/api/pipelines/gmail/status/${id}`)
        if (!response.ok) {
          throw new Error(`Failed to fetch Gmail run status: ${response.status}`)
        }
        const data = await response.json()
        setGmailRunStatus(data.status)

        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          done = true
          setGmailIsRunning(false)

          const messagesResp = await fetch(
            `http://localhost:8000/api/pipelines/gmail/messages?run_id=${encodeURIComponent(id)}`,
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
      const response = await fetch(`http://localhost:8000/api/pipelines/gmail/run?${params.toString()}`, {
        method: 'POST',
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
      await fetch(`http://localhost:8000/api/pipelines/gmail/stop/${encodeURIComponent(gmailRunId)}`, {
        method: 'POST',
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
        const response = await fetch(`http://localhost:8000/api/pipelines/notion/status/${id}`)
        if (!response.ok) {
          throw new Error(`Failed to fetch Notion run status: ${response.status}`)
        }
        const data = await response.json()
        setNotionRunStatus(data.status)

        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          done = true
          setNotionIsRunning(false)

          const pagesResp = await fetch(
            `http://localhost:8000/api/pipelines/notion/pages?run_id=${encodeURIComponent(id)}`,
          )
          if (pagesResp.ok) {
            const pagesData = await pagesResp.json()
            setNotionPages(pagesData.pages || [])
          }
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

      const response = await fetch('http://localhost:8000/api/pipelines/notion/run', {
        method: 'POST',
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
      await fetch(`http://localhost:8000/api/pipelines/notion/stop/${encodeURIComponent(notionRunId)}`, {
        method: 'POST',
      })
    } catch (err: any) {
      console.error('Error stopping Notion pipeline:', err)
      setError(err.message || 'Failed to stop Notion pipeline')
    }
  }

  // -----------------------------
  // Initial data
  // -----------------------------

  useEffect(() => {
    fetchSlackData()
    fetchGmailLabels()
  }, [])

  useEffect(() => {
    if (!selectedLabelId) {
      setGmailMessages([])
      return
    }
    fetchGmailMessagesForLabel(selectedLabelId)
  }, [selectedLabelId])

  useEffect(() => {
    if (slackMessages.length > 0 && slackMessagesEndRef.current) {
      slackMessagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [slackMessages.length, selectedChannelId])

  useEffect(() => {
    if (gmailMessages.length > 0 && gmailMessagesEndRef.current) {
      gmailMessagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [gmailMessages.length, gmailRunId])

  // -----------------------------
  // Render helpers
  // -----------------------------

  const renderSlackView = () => (
    <>
      <div className="w-80 border-r border-border bg-card p-4 flex flex-col gap-4">
        <div>
          <h2 className="text-lg font-semibold mb-2">Slack Pipeline</h2>
          <p className="text-sm text-muted-foreground mb-3">
            Manually sync Slack workspace history (users, channels, messages, files) into the database.
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
          </div>
        )}
      </div>

      <div className="flex-1 p-4 overflow-hidden flex flex-col">
        <h2 className="text-lg font-semibold mb-3">Slack Channels</h2>
        <div className="flex-1 flex overflow-hidden gap-4">
          <div className="w-80 border border-border rounded-md bg-card overflow-auto">
            <table className="min-w-full text-xs">
              <thead className="bg-muted">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Channel</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Messages</th>
                </tr>
              </thead>
              <tbody>
                {channels.map((ch) => (
                  <tr
                    key={ch.channel_id}
                    className={
                      'cursor-pointer border-b border-border/60 hover:bg-muted ' +
                      (selectedChannelId === ch.channel_id ? 'bg-muted/80' : '')
                    }
                    onClick={() => {
                      setSelectedChannelId(ch.channel_id)
                      fetchSlackMessages(ch.channel_id)
                    }}
                  >
                    <td className="px-3 py-2 align-top">
                      <div className="font-medium text-foreground text-xs">
                        {ch.name || ch.channel_id}
                        {ch.is_private && <span className="ml-1 text-[10px] text-yellow-400">(private)</span>}
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        {ch.num_members != null ? `${ch.num_members} members` : 'Members unknown'}
                        {ch.is_archived && <span className="ml-1 text-[10px] text-red-400">archived</span>}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right align-top text-xs">{ch.message_count}</td>
                  </tr>
                ))}
                {channels.length === 0 && (
                  <tr>
                    <td colSpan={2} className="px-3 py-4 text-center text-xs text-muted-foreground">
                      No Slack channels found yet. Run the Slack pipeline to load data.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="flex-1 border border-border rounded-md bg-card p-4 overflow-auto">
            {selectedChannel ? (
              <div className="flex flex-col h-full">
                <div className="mb-3">
                  <h3 className="text-base font-semibold mb-1">Channel Details</h3>
                  <p className="text-sm mb-1">
                    <span className="font-mono text-sm">{selectedChannel.name || selectedChannel.channel_id}</span>
                    {selectedChannel.is_private && <span className="ml-2 text-xs text-yellow-400">Private</span>}
                    {selectedChannel.is_archived && <span className="ml-2 text-xs text-red-400">Archived</span>}
                  </p>
                  <p className="text-xs text-muted-foreground mb-2">
                    Members:{' '}
                    {selectedChannel.num_members != null ? selectedChannel.num_members : 'Unknown'} · Messages:{' '}
                    {selectedChannel.message_count}
                  </p>
                </div>

                <div className="flex-1 overflow-auto border border-border rounded-md bg-background p-2">
                  {slackMessages.length === 0 ? (
                    <p className="text-xs text-muted-foreground">
                      No messages loaded for this channel yet. Run the Slack pipeline or select the channel again.
                    </p>
                  ) : (
                    <>
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <input
                          type="text"
                          value={slackSearchQuery}
                          onChange={(e) => setSlackSearchQuery(e.target.value)}
                          placeholder="Filter messages"
                          className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-xs"
                        />
                        <span className="text-[11px] text-muted-foreground">{slackMessages.length} loaded</span>
                      </div>
                      <div className="space-y-3">
                        {Object.entries(groupedSlackThreads).map(([key, thread]) => (
                          <div key={key} className="rounded-md border border-border/60 bg-card p-2">
                            {thread.root && (
                              <div className="mb-1">
                                <div className="flex items-center justify-between gap-2">
                                  <div className="text-xs font-semibold text-foreground">
                                    {thread.root.user_name || thread.root.user_id || 'Unknown user'}
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
                                    {thread.root.reply_count} repl{thread.root.reply_count === 1 ? 'y' : 'ies'}
                                  </p>
                                ) : null}
                              </div>
                            )}

                            {thread.replies.length > 0 && (
                              <div className="mt-2 border-t border-border/40 pt-2 space-y-1">
                                {[...thread.replies]
                                  .sort((a, b) => a.timestamp - b.timestamp)
                                  .map((reply) => (
                                    <div key={reply.message_id} className="pl-2 border-l border-border/40">
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
              <p className="text-sm text-muted-foreground">Select a channel on the left to see details.</p>
            )}
          </div>
        </div>
      </div>
    </>
  )

  const renderGmailView = () => (
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
          <select
            id="gmail-label-select"
            className="w-full rounded-md border border-border bg-background px-2 py-1 text-xs mb-2"
            value={selectedLabelId}
            onChange={(e) => setSelectedLabelId(e.target.value)}
          >
            <option value="">Select a label…</option>
            {gmailLabels.map((lbl) => (
              <option key={lbl.id} value={lbl.id}>
                {lbl.name}
              </option>
            ))}
          </select>

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
        </div>
      </div>

      <div className="flex-1 p-4 overflow-hidden flex flex-col">
        <h2 className="text-lg font-semibold mb-3">Gmail Messages</h2>
        <div className="flex-1 overflow-auto border border-border rounded-md bg-card p-2">
          {gmailMessages.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No messages loaded yet. Select a label and run the Gmail pipeline.
            </p>
          ) : (
            <div className="space-y-2">
              {[...gmailMessages]
                .sort((a, b) => {
                  const aTime = a.date ? new Date(a.date).getTime() : 0
                  const bTime = b.date ? new Date(b.date).getTime() : 0
                  return aTime - bTime
                })
                .map((msg, index, arr) => {
                  const header = `${msg.from || 'Unknown sender'} · ${msg.subject || 'No subject'}`
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
        </div>
      </div>
    </>
  )

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
              Fetch pages under the configured NOTION_PARENT_PAGE_ID and explore them.
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
          </div>
        </div>

        <div className="flex-1 p-4 overflow-hidden flex flex-col">
          <h2 className="text-lg font-semibold mb-3">Notion Pages</h2>
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
          <div className="flex-1 overflow-auto border border-border rounded-md bg-card">
            {filteredPages.length === 0 ? (
              <p className="p-3 text-xs text-muted-foreground">
                No pages loaded yet. Run the Notion pipeline to fetch pages under the parent.
              </p>
            ) : (
              <table className="min-w-full text-xs">
                <thead className="bg-muted">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Title</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Last Edited</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Open</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPages.map((page) => (
                    <tr key={page.id} className="border-b border-border/60">
                      <td className="px-3 py-2 align-top">
                        <div className="font-medium text-foreground text-xs truncate">{page.title}</div>
                        <div className="text-[11px] text-muted-foreground break-all">{page.id}</div>
                      </td>
                      <td className="px-3 py-2 align-top text-[11px] text-muted-foreground">
                        {page.last_edited_time
                          ? new Date(page.last_edited_time).toLocaleString()
                          : 'Unknown'}
                      </td>
                      <td className="px-3 py-2 align-top text-right">
                        {page.url ? (
                          <button
                            type="button"
                            onClick={() => window.open(page.url as string, '_blank')}
                            className="text-[11px] font-medium text-blue-400 hover:underline"
                          >
                            Open
                          </button>
                        ) : (
                          <span className="text-[11px] text-muted-foreground">No URL</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
          {error}
        </div>
      )}
    </div>
  )
}
