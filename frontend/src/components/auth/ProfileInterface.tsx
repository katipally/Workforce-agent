import React, { useEffect, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { API_BASE_URL } from '../../lib/api'

type PersonalSettingsView = {
  openai_api_key_set: boolean
  openai_api_key_last4: string
  llm_model: string
  timezone: string | null
  openai_api_key_full?: string
}

type WorkspaceSettingsView = {
  slack: {
    bot_token_set: boolean
    bot_token_last4: string
    user_token_set: boolean
    user_token_last4: string
    mode: string
    readonly_channels: string[]
    blocked_channels: string[]
    bot_token_value?: string
    user_token_value?: string
  }
  notion: {
    token_set: boolean
    token_last4: string
    mode: string
    parent_page_id: string
    token_value?: string
  }
  gmail: {
    send_mode: string
    allowed_send_domains: string[]
    allowed_read_domains: string[]
    default_label: string
  }
  workspace: {
    name: string
    id: string
  }
  runtime: {
    frontend_base_url: string
    api_host: string
    api_port: number
    log_level: string
    log_file: string
    tier_4_rate_limit: number
    default_rate_limit: number
    socket_mode_enabled: boolean
    max_reconnect_attempts: number
  }
  database: {
    database_url: string
    data_dir: string
    files_dir: string
    export_dir: string
    project_registry_file: string
  }
  ai_infra: {
    embedding_model: string
    reranker_model: string
    embedding_batch_size: number
    use_gpu: boolean
    editable: boolean
  }
}

const ProfileInterface: React.FC = () => {
  const { user, logout } = useAuthStore()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [personalView, setPersonalView] = useState<PersonalSettingsView | null>(null)
  const [personalForm, setPersonalForm] = useState({
    openaiApiKey: '',
    llmModel: '',
    timezone: '' as string | ''
  })
  const [personalDirty, setPersonalDirty] = useState(false)
  const [savingPersonal, setSavingPersonal] = useState(false)

  const [workspaceView, setWorkspaceView] = useState<WorkspaceSettingsView | null>(null)
  const [workspaceForm, setWorkspaceForm] = useState({
    slackBotToken: '',
    slackMode: 'standard',
    slackReadonly: '',
    slackBlocked: '',
    notionParentPageId: '',
    notionToken: '',
    gmailSendMode: 'confirm',
    gmailAllowedSend: '',
    gmailAllowedRead: '',
    gmailDefaultLabel: '',
    workspaceName: '',
    workspaceId: '',
    frontendBaseUrl: '',
    apiHost: '',
    apiPort: '' as string | '',
    logLevel: '',
    logFile: '',
    tier4RateLimit: '' as string | '',
    defaultRateLimit: '' as string | '',
    socketModeEnabled: false,
    maxReconnectAttempts: '' as string | '',
  })
  const [workspaceDirty, setWorkspaceDirty] = useState(false)
  const [savingWorkspace, setSavingWorkspace] = useState(false)

  const [showPersonalKey, setShowPersonalKey] = useState(false)
  const [showSlackToken, setShowSlackToken] = useState(false)
  const [showNotionToken, setShowNotionToken] = useState(false)

  const MASKED_SECRET = '********'

  const [timezoneOptions, setTimezoneOptions] = useState<string[]>([])
  const [slackChannelOptions, setSlackChannelOptions] = useState<{ id: string; name: string }[]>([])
  const [gmailLabelOptions, setGmailLabelOptions] = useState<string[]>([])

  useEffect(() => {
    if (!user) {
      setLoading(false)
      return
    }

    const load = async () => {
      try {
        setLoading(true)
        setError(null)

        const [personalRes, workspaceRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/settings/me`, { credentials: 'include' }),
          fetch(`${API_BASE_URL}/api/settings/workspace`, { credentials: 'include' }),
        ])

        if (!personalRes.ok) {
          throw new Error('Failed to load personal settings')
        }
        if (!workspaceRes.ok) {
          throw new Error('Failed to load workspace settings')
        }

        const personalJson = (await personalRes.json()) as PersonalSettingsView
        const workspaceJson = (await workspaceRes.json()) as WorkspaceSettingsView

        setPersonalView(personalJson)
        setPersonalForm({
          openaiApiKey: '',
          llmModel: personalJson.llm_model || '',
          timezone: personalJson.timezone || '',
        })

        setWorkspaceView(workspaceJson)
        setWorkspaceForm({
          slackBotToken: '',
          slackMode: workspaceJson.slack.mode || 'standard',
          slackReadonly: workspaceJson.slack.readonly_channels.join(', '),
          slackBlocked: workspaceJson.slack.blocked_channels.join(', '),
          notionParentPageId: workspaceJson.notion.parent_page_id || '',
          notionToken: '',
          gmailSendMode: workspaceJson.gmail.send_mode || 'confirm',
          gmailAllowedSend: workspaceJson.gmail.allowed_send_domains.join(', '),
          gmailAllowedRead: workspaceJson.gmail.allowed_read_domains.join(', '),
          gmailDefaultLabel: workspaceJson.gmail.default_label || '',
          workspaceName: workspaceJson.workspace.name || '',
          workspaceId: workspaceJson.workspace.id || '',
          frontendBaseUrl: workspaceJson.runtime.frontend_base_url || '',
          apiHost: workspaceJson.runtime.api_host || '',
          apiPort: String(workspaceJson.runtime.api_port ?? ''),
          logLevel: workspaceJson.runtime.log_level || '',
          logFile: workspaceJson.runtime.log_file || '',
          tier4RateLimit: String(workspaceJson.runtime.tier_4_rate_limit ?? ''),
          defaultRateLimit: String(workspaceJson.runtime.default_rate_limit ?? ''),
          socketModeEnabled: workspaceJson.runtime.socket_mode_enabled,
          maxReconnectAttempts: String(workspaceJson.runtime.max_reconnect_attempts ?? ''),
        })

        try {
          const [tzRes, slackOptRes, gmailLabelRes] = await Promise.all([
            fetch(`${API_BASE_URL}/api/settings/options/timezones`, { credentials: 'include' }),
            fetch(`${API_BASE_URL}/api/settings/options/slack-channels`, { credentials: 'include' }),
            fetch(`${API_BASE_URL}/api/settings/options/gmail-labels`, { credentials: 'include' }),
          ])

          if (tzRes.ok) {
            const tzJson = (await tzRes.json()) as { timezones: string[] }
            setTimezoneOptions(tzJson.timezones || [])
          }
          if (slackOptRes.ok) {
            const slackJson = (await slackOptRes.json()) as { channels: { id: string; name: string }[] }
            setSlackChannelOptions(slackJson.channels || [])
          }
          if (gmailLabelRes.ok) {
            const labelsJson = (await gmailLabelRes.json()) as { labels: string[] }
            setGmailLabelOptions(labelsJson.labels || [])
          }
        } catch {
          // Suggestions are optional; ignore failures.
        }

        setPersonalDirty(false)
        setWorkspaceDirty(false)
      } catch (e: any) {
        setError(e?.message || 'Failed to load settings')
      } finally {
        setLoading(false)
      }
    }

    void load()
  }, [user])

  const reloadSuggestions = async () => {
    try {
      const [tzRes, slackOptRes, gmailLabelRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/settings/options/timezones`, { credentials: 'include' }),
        fetch(`${API_BASE_URL}/api/settings/options/slack-channels`, { credentials: 'include' }),
        fetch(`${API_BASE_URL}/api/settings/options/gmail-labels`, { credentials: 'include' }),
      ])

      if (tzRes.ok) {
        const tzJson = (await tzRes.json()) as { timezones: string[] }
        setTimezoneOptions(tzJson.timezones || [])
      }
      if (slackOptRes.ok) {
        const slackJson = (await slackOptRes.json()) as { channels: { id: string; name: string }[] }
        setSlackChannelOptions(slackJson.channels || [])
      }
      if (gmailLabelRes.ok) {
        const labelsJson = (await gmailLabelRes.json()) as { labels: string[] }
        setGmailLabelOptions(labelsJson.labels || [])
      }
    } catch {
    }
  }

  const handleReconnectGmail = () => {
    const url = `${API_BASE_URL}/auth/google/login?redirect_path=/`
    window.location.href = url
  }

  const handlePersonalChange = (field: keyof typeof personalForm, value: string) => {
    setPersonalForm((prev) => ({ ...prev, [field]: value }))
    setPersonalDirty(true)
  }

  const handleWorkspaceChange = (field: keyof typeof workspaceForm, value: string | boolean) => {
    setWorkspaceForm((prev) => ({ ...prev, [field]: value as any }))
    setWorkspaceDirty(true)
  }

  const handleTogglePersonalKeyVisibility = async () => {
    if (!personalView) return

    if (!showPersonalKey) {
      // If the user has already typed or we already loaded the key, just reveal it.
      if (personalForm.openaiApiKey) {
        setShowPersonalKey(true)
        return
      }

      // Use cached full key from the current view if available.
      if (personalView.openai_api_key_full) {
        setPersonalForm((prev) => ({
          ...prev,
          openaiApiKey: prev.openaiApiKey || personalView.openai_api_key_full || '',
        }))
        setShowPersonalKey(true)
        return
      }

      // Otherwise, fetch the full key once if it's set.
      if (personalView.openai_api_key_set) {
        try {
          const res = await fetch(`${API_BASE_URL}/api/settings/me?include_secrets=true`, {
            credentials: 'include',
          })
          if (res.ok) {
            const data = (await res.json()) as PersonalSettingsView
            setPersonalView(data)
            if (data.openai_api_key_full) {
              setPersonalForm((prev) => ({
                ...prev,
                openaiApiKey: prev.openaiApiKey || data.openai_api_key_full || '',
              }))
            }
          }
        } catch (e: any) {
          setError(e?.message || 'Failed to load personal secret')
        }
      }

      setShowPersonalKey(true)
    } else {
      setShowPersonalKey(false)
    }
  }

  const handleToggleSlackTokenVisibility = async () => {
    if (!workspaceView) return

    if (!showSlackToken) {
      // If we already have a value in the form (typed or previously loaded), just reveal it.
      if (workspaceForm.slackBotToken) {
        setShowSlackToken(true)
        return
      }

      // If the decrypted value is already present in the view, reuse it.
      if (workspaceView.slack.bot_token_value) {
        setWorkspaceForm((prev) => ({
          ...prev,
          slackBotToken: prev.slackBotToken || workspaceView.slack.bot_token_value || '',
        }))
        setShowSlackToken(true)
        return
      }

      // Otherwise fetch all workspace secrets once and populate any missing fields.
      if (workspaceView.slack.bot_token_set || workspaceView.notion.token_set) {
        try {
          const res = await fetch(`${API_BASE_URL}/api/settings/workspace?include_secrets=true`, {
            credentials: 'include',
          })
          if (res.ok) {
            const data = (await res.json()) as WorkspaceSettingsView
            setWorkspaceView(data)
            setWorkspaceForm((prev) => ({
              ...prev,
              slackBotToken: prev.slackBotToken || data.slack.bot_token_value || '',
              notionToken: prev.notionToken || data.notion.token_value || '',
            }))
          }
        } catch (e: any) {
          setError(e?.message || 'Failed to load Slack token')
        }
      }

      setShowSlackToken(true)
    } else {
      setShowSlackToken(false)
    }
  }

  const handleToggleNotionTokenVisibility = async () => {
    if (!workspaceView) return

    if (!showNotionToken) {
      // If we already have a value in the form (typed or previously loaded), just reveal it.
      if (workspaceForm.notionToken) {
        setShowNotionToken(true)
        return
      }

      // If the decrypted value is already present in the view, reuse it.
      if (workspaceView.notion.token_value) {
        setWorkspaceForm((prev) => ({
          ...prev,
          notionToken: prev.notionToken || workspaceView.notion.token_value || '',
        }))
        setShowNotionToken(true)
        return
      }

      // Otherwise fetch all workspace secrets once and populate any missing fields.
      if (workspaceView.notion.token_set || workspaceView.slack.bot_token_set) {
        try {
          const res = await fetch(`${API_BASE_URL}/api/settings/workspace?include_secrets=true`, {
            credentials: 'include',
          })
          if (res.ok) {
            const data = (await res.json()) as WorkspaceSettingsView
            setWorkspaceView(data)
            setWorkspaceForm((prev) => ({
              ...prev,
              slackBotToken: prev.slackBotToken || data.slack.bot_token_value || '',
              notionToken: prev.notionToken || data.notion.token_value || '',
            }))
          }
        } catch (e: any) {
          setError(e?.message || 'Failed to load Notion token')
        }
      }

      setShowNotionToken(true)
    } else {
      setShowNotionToken(false)
    }
  }

  const handleSavePersonal = async () => {
    if (!personalView || !personalDirty) return
    try {
      setSavingPersonal(true)
      setError(null)

      const payload: any = {}

      if (personalForm.openaiApiKey.trim()) {
        payload.openai_api_key = personalForm.openaiApiKey.trim()
      }

      if (personalForm.llmModel !== personalView.llm_model) {
        payload.llm_model = personalForm.llmModel || null
      }

      if ((personalForm.timezone || null) !== (personalView.timezone || null)) {
        payload.timezone = personalForm.timezone || null
      }

      const res = await fetch(`${API_BASE_URL}/api/settings/me`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        throw new Error('Failed to save personal settings')
      }
      const updated = (await res.json()) as PersonalSettingsView
      setPersonalView(updated)
      setPersonalForm({
        openaiApiKey: '',
        llmModel: updated.llm_model || '',
        timezone: updated.timezone || '',
      })
      setPersonalDirty(false)
      setShowPersonalKey(false)
    } catch (e: any) {
      setError(e?.message || 'Failed to save personal settings')
    } finally {
      setSavingPersonal(false)
    }
  }

  const handleCancelPersonal = () => {
    if (!personalView) return
    setPersonalForm({
      openaiApiKey: '',
      llmModel: personalView.llm_model || '',
      timezone: personalView.timezone || '',
    })
    setPersonalDirty(false)
    setShowPersonalKey(false)
  }

  const handleSaveWorkspace = async () => {
    if (!workspaceView || !workspaceDirty) return
    try {
      setSavingWorkspace(true)
      setError(null)

      const payload: any = {}

      // Slack
      const slack: any = {}
      if (workspaceForm.slackBotToken.trim()) {
        slack.bot_token = workspaceForm.slackBotToken.trim()
      }
      if (workspaceForm.slackMode !== workspaceView.slack.mode) {
        slack.mode = workspaceForm.slackMode
      }
      const readonlyList = workspaceForm.slackReadonly
        .split(',')
        .map((c) => c.trim())
        .filter(Boolean)
      if (readonlyList.join(',') !== workspaceView.slack.readonly_channels.join(',')) {
        slack.readonly_channels = readonlyList
      }
      const blockedList = workspaceForm.slackBlocked
        .split(',')
        .map((c) => c.trim())
        .filter(Boolean)
      if (blockedList.join(',') !== workspaceView.slack.blocked_channels.join(',')) {
        slack.blocked_channels = blockedList
      }
      if (slack && Object.keys(slack).length > 0) {
        payload.slack = slack
      }

      // Notion
      const notion: any = {}
      if (workspaceForm.notionToken.trim()) {
        notion.token = workspaceForm.notionToken.trim()
      }
      if (workspaceForm.notionParentPageId !== workspaceView.notion.parent_page_id) {
        notion.parent_page_id = workspaceForm.notionParentPageId || null
      }
      if (Object.keys(notion).length > 0) {
        payload.notion = notion
      }

      // Gmail
      const gmail: any = {}
      if (workspaceForm.gmailSendMode !== workspaceView.gmail.send_mode) {
        gmail.send_mode = workspaceForm.gmailSendMode
      }
      const sendDomains = workspaceForm.gmailAllowedSend
        .split(',')
        .map((d) => d.trim())
        .filter(Boolean)
      if (sendDomains.join(',') !== workspaceView.gmail.allowed_send_domains.join(',')) {
        gmail.allowed_send_domains = sendDomains
      }
      const readDomains = workspaceForm.gmailAllowedRead
        .split(',')
        .map((d) => d.trim())
        .filter(Boolean)
      if (readDomains.join(',') !== workspaceView.gmail.allowed_read_domains.join(',')) {
        gmail.allowed_read_domains = readDomains
      }
      if (workspaceForm.gmailDefaultLabel !== workspaceView.gmail.default_label) {
        gmail.default_label = workspaceForm.gmailDefaultLabel || null
      }
      if (Object.keys(gmail).length > 0) {
        payload.gmail = gmail
      }

      // Workspace info
      const workspaceInfo: any = {}
      if (workspaceForm.workspaceName !== workspaceView.workspace.name) {
        workspaceInfo.name = workspaceForm.workspaceName
      }
      if (workspaceForm.workspaceId !== workspaceView.workspace.id) {
        workspaceInfo.id = workspaceForm.workspaceId
      }
      if (Object.keys(workspaceInfo).length > 0) {
        payload.workspace = workspaceInfo
      }

      // Runtime / URLs + logging
      const runtime: any = {}
      if (workspaceForm.frontendBaseUrl !== workspaceView.runtime.frontend_base_url) {
        runtime.frontend_base_url = workspaceForm.frontendBaseUrl
      }
      if (workspaceForm.apiHost !== workspaceView.runtime.api_host) {
        runtime.api_host = workspaceForm.apiHost
      }
      if (workspaceForm.apiPort !== String(workspaceView.runtime.api_port ?? '')) {
        runtime.api_port = workspaceForm.apiPort ? Number(workspaceForm.apiPort) : null
      }
      if (workspaceForm.logLevel !== workspaceView.runtime.log_level) {
        runtime.log_level = workspaceForm.logLevel
      }
      if (workspaceForm.logFile !== workspaceView.runtime.log_file) {
        runtime.log_file = workspaceForm.logFile
      }
      if (workspaceForm.tier4RateLimit !== String(workspaceView.runtime.tier_4_rate_limit ?? '')) {
        runtime.tier_4_rate_limit = workspaceForm.tier4RateLimit
          ? Number(workspaceForm.tier4RateLimit)
          : null
      }
      if (workspaceForm.defaultRateLimit !== String(workspaceView.runtime.default_rate_limit ?? '')) {
        runtime.default_rate_limit = workspaceForm.defaultRateLimit
          ? Number(workspaceForm.defaultRateLimit)
          : null
      }
      if (workspaceForm.socketModeEnabled !== workspaceView.runtime.socket_mode_enabled) {
        runtime.socket_mode_enabled = workspaceForm.socketModeEnabled
      }
      if (workspaceForm.maxReconnectAttempts !== String(workspaceView.runtime.max_reconnect_attempts ?? '')) {
        runtime.max_reconnect_attempts = workspaceForm.maxReconnectAttempts
          ? Number(workspaceForm.maxReconnectAttempts)
          : null
      }
      if (Object.keys(runtime).length > 0) {
        payload.runtime = runtime
      }

      // Database/Storage
      const database: any = {}
      if (workspaceForm.workspaceName && workspaceView.database.database_url) {
        // No-op placeholder; database URL and paths can be wired later if needed.
      }

      if (Object.keys(database).length > 0) {
        payload.database = database
      }

      const res = await fetch(`${API_BASE_URL}/api/settings/workspace`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        throw new Error('Failed to save workspace settings')
      }
      const updated = (await res.json()) as WorkspaceSettingsView
      setWorkspaceView(updated)
      setWorkspaceForm({
        slackBotToken: '',
        slackMode: updated.slack.mode || 'standard',
        slackReadonly: updated.slack.readonly_channels.join(', '),
        slackBlocked: updated.slack.blocked_channels.join(', '),
        notionParentPageId: updated.notion.parent_page_id || '',
        notionToken: '',
        gmailSendMode: updated.gmail.send_mode || 'confirm',
        gmailAllowedSend: updated.gmail.allowed_send_domains.join(', '),
        gmailAllowedRead: updated.gmail.allowed_read_domains.join(', '),
        gmailDefaultLabel: updated.gmail.default_label || '',
        workspaceName: updated.workspace.name || '',
        workspaceId: updated.workspace.id || '',
        frontendBaseUrl: updated.runtime.frontend_base_url || '',
        apiHost: updated.runtime.api_host || '',
        apiPort: String(updated.runtime.api_port ?? ''),
        logLevel: updated.runtime.log_level || '',
        logFile: updated.runtime.log_file || '',
        tier4RateLimit: String(updated.runtime.tier_4_rate_limit ?? ''),
        defaultRateLimit: String(updated.runtime.default_rate_limit ?? ''),
        socketModeEnabled: updated.runtime.socket_mode_enabled,
        maxReconnectAttempts: String(updated.runtime.max_reconnect_attempts ?? ''),
      })
      setWorkspaceDirty(false)
      void reloadSuggestions()
    } catch (e: any) {
      setError(e?.message || 'Failed to save workspace settings')
    } finally {
      setSavingWorkspace(false)
    }
  }

  const handleCancelWorkspace = () => {
    if (!workspaceView) return
    setWorkspaceForm({
      slackBotToken: '',
      slackMode: workspaceView.slack.mode || 'standard',
      slackReadonly: workspaceView.slack.readonly_channels.join(', '),
      slackBlocked: workspaceView.slack.blocked_channels.join(', '),
      notionParentPageId: workspaceView.notion.parent_page_id || '',
      notionToken: '',
      gmailSendMode: workspaceView.gmail.send_mode || 'confirm',
      gmailAllowedSend: workspaceView.gmail.allowed_send_domains.join(', '),
      gmailAllowedRead: workspaceView.gmail.allowed_read_domains.join(', '),
      gmailDefaultLabel: workspaceView.gmail.default_label || '',
      workspaceName: workspaceView.workspace.name || '',
      workspaceId: workspaceView.workspace.id || '',
      frontendBaseUrl: workspaceView.runtime.frontend_base_url || '',
      apiHost: workspaceView.runtime.api_host || '',
      apiPort: String(workspaceView.runtime.api_port ?? ''),
      logLevel: workspaceView.runtime.log_level || '',
      logFile: workspaceView.runtime.log_file || '',
      tier4RateLimit: String(workspaceView.runtime.tier_4_rate_limit ?? ''),
      defaultRateLimit: String(workspaceView.runtime.default_rate_limit ?? ''),
      socketModeEnabled: workspaceView.runtime.socket_mode_enabled,
      maxReconnectAttempts: String(workspaceView.runtime.max_reconnect_attempts ?? ''),
    })
    setWorkspaceDirty(false)
    setShowSlackToken(false)
    setShowNotionToken(false)
  }

  if (!user) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">You are not signed in.</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Loading settings…</p>
      </div>
    )
  }

  return (
    <div className="h-full w-full flex items-start justify-center bg-background overflow-auto py-8">
      <div className="w-full max-w-5xl mx-4 space-y-6">
        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-2 text-xs text-destructive">
            {error}
          </div>
        )}

        {/* Account tile */}
        <div className="border border-border rounded-xl bg-card p-6 shadow-sm">
          <h2 className="text-lg font-semibold mb-4 text-foreground">Account</h2>
          <div className="flex items-center gap-4 mb-6">
            {user.picture_url ? (
              <img
                src={user.picture_url}
                alt={user.name}
                className="h-14 w-14 rounded-full border border-border object-cover"
              />
            ) : (
              <div className="h-14 w-14 rounded-full border border-border flex items-center justify-center text-lg font-semibold bg-background">
                {user.name?.charAt(0).toUpperCase() || user.email.charAt(0).toUpperCase()}
              </div>
            )}
            <div>
              <p className="text-sm font-medium text-foreground">{user.name}</p>
              <p className="text-xs text-muted-foreground">{user.email}</p>
            </div>
          </div>

          <div className="space-y-3 mb-6 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Gmail connection</span>
              <span className="text-xs font-medium px-2 py-0.5 rounded-full border border-border bg-background">
                {user.has_gmail_access ? 'Connected' : 'Not connected'}
              </span>
            </div>
            {!user.has_gmail_access && (
              <p className="text-xs text-muted-foreground">
                Connect Gmail to enable email pipelines and Gmail-powered project tracking.
              </p>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleReconnectGmail}
                className="inline-flex items-center justify-center rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted"
              >
                {user.has_gmail_access ? 'Refresh Google permissions' : 'Connect Gmail'}
              </button>
            </div>
          </div>

          <div className="border-t border-border pt-4 flex justify-between items-center">
            <p className="text-xs text-muted-foreground">
              Signed in with Google. Closing the browser tab does not fully sign you out.
            </p>
            <button
              type="button"
              onClick={logout}
              className="inline-flex items-center justify-center rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
            >
              Log out
            </button>
          </div>
        </div>

        {/* Personal Settings tile */}
        <div className="border border-border rounded-xl bg-card p-6 shadow-sm">
          <h2 className="text-lg font-semibold mb-4 text-foreground">Personal settings</h2>
          {personalView && (
            <div className="space-y-4 text-sm">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">
                  OpenAI API key
                </label>
                <input
                  type={showPersonalKey ? 'text' : 'password'}
                  autoComplete="off"
                  className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  placeholder={
                    personalView.openai_api_key_set
                      ? `Key set (ending with ${personalView.openai_api_key_last4})`
                      : 'Enter your OpenAI API key'
                  }
                  value={
                    showPersonalKey
                      ? personalForm.openaiApiKey
                      : personalView.openai_api_key_set && !personalForm.openaiApiKey
                        ? MASKED_SECRET
                        : personalForm.openaiApiKey
                  }
                  onChange={(e) => handlePersonalChange('openaiApiKey', e.target.value)}
                />
                <div className="mt-1 flex items-center justify-between">
                  <p className="text-[11px] text-muted-foreground">
                    This key is stored encrypted and only used for your own requests.
                  </p>
                  {personalView.openai_api_key_set && (
                    <button
                      type="button"
                      onClick={handleTogglePersonalKeyVisibility}
                      aria-label={showPersonalKey ? 'Hide API key' : 'Show API key'}
                      title={showPersonalKey ? 'Hide API key' : 'Show API key'}
                      className="inline-flex items-center justify-center text-[11px] text-primary hover:underline"
                    >
                      {showPersonalKey ? (
                        <EyeOff className="h-3 w-3" />
                      ) : (
                        <Eye className="h-3 w-3" />
                      )}
                    </button>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label
                    htmlFor="personal-default-model"
                    className="block text-xs font-medium text-muted-foreground mb-1"
                  >
                    Default model
                  </label>
                  <select
                    id="personal-default-model"
                    className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    value={personalForm.llmModel}
                    onChange={(e) => handlePersonalChange('llmModel', e.target.value)}
                  >
                    <option value="">Use backend default ({ConfigFallbacks.llmModel})</option>
                    <option value="gpt-4o-mini">gpt-4o-mini</option>
                    <option value="gpt-4.1">gpt-4.1</option>
                    <option value="gpt-4o">gpt-4o</option>
                    <option value="gpt-5-nano">gpt-5-nano</option>
                  </select>
                </div>
                <div>
                  <label
                    htmlFor="personal-timezone"
                    className="block text-xs font-medium text-muted-foreground mb-1"
                  >
                    Timezone (optional)
                  </label>
                  <>
                    <input
                      id="personal-timezone"
                      type="text"
                      list="timezone-options"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      placeholder="e.g. America/Los_Angeles"
                      value={personalForm.timezone}
                      onChange={(e) => handlePersonalChange('timezone', e.target.value)}
                    />
                    <datalist id="timezone-options">
                      {timezoneOptions.map((tz) => (
                        <option key={tz} value={tz} />
                      ))}
                    </datalist>
                  </>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={handleCancelPersonal}
                  disabled={!personalDirty || savingPersonal}
                  className="inline-flex items-center justify-center rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSavePersonal}
                  disabled={!personalDirty || savingPersonal}
                  className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {savingPersonal ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Workspace Settings tile */}
        {workspaceView && (
          <div className="border border-border rounded-xl bg-card p-6 shadow-sm">
            <h2 className="text-lg font-semibold mb-4 text-foreground">Workspace settings</h2>
            <p className="text-xs text-muted-foreground mb-4">
              Changes here affect all users in this workspace. For now, all users can edit these settings.
            </p>

            <div className="space-y-6 text-sm">
              {/* Slack */}
              <section>
                <h3 className="text-sm font-semibold text-foreground mb-2">Slack</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Bot token
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        type={showSlackToken ? 'text' : 'password'}
                        autoComplete="off"
                        className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        placeholder={
                          workspaceView.slack.bot_token_set
                            ? `Token set (ending with ${workspaceView.slack.bot_token_last4})`
                            : 'Enter Slack bot token'
                        }
                        value={
                          showSlackToken
                            ? workspaceForm.slackBotToken
                            : workspaceView.slack.bot_token_set && !workspaceForm.slackBotToken
                              ? MASKED_SECRET
                              : workspaceForm.slackBotToken
                        }
                        onChange={(event) => handleWorkspaceChange('slackBotToken', event.target.value)}
                      />
                      {workspaceView.slack.bot_token_set && (
                        <button
                          type="button"
                          onClick={handleToggleSlackTokenVisibility}
                          aria-label={showSlackToken ? 'Hide Slack bot token' : 'Show Slack bot token'}
                          title={showSlackToken ? 'Hide Slack bot token' : 'Show Slack bot token'}
                          className="inline-flex items-center justify-center text-[11px] text-primary hover:underline whitespace-nowrap"
                        >
                          {showSlackToken ? (
                            <EyeOff className="h-3 w-3" />
                          ) : (
                            <Eye className="h-3 w-3" />
                          )}
                        </button>
                      )}
                    </div>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Existing token is not shown by default; enter a new value to rotate it or use Show to reveal.
                    </p>
                  </div>
                  <div>
                    <label
                      htmlFor="slack-mode"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Mode
                    </label>
                    <select
                      id="slack-mode"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.slackMode}
                      onChange={(e) => handleWorkspaceChange('slackMode', e.target.value)}
                    >
                      <option value="read_only">read_only</option>
                      <option value="standard">standard</option>
                      <option value="admin">admin</option>
                    </select>
                  </div>
                  <div>
                    <label
                      htmlFor="slack-readonly-channels"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Read-only channels
                    </label>
                    <>
                      <input
                        id="slack-readonly-channels"
                        type="text"
                        list="slack-channel-options"
                        className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        placeholder="Comma-separated channel names or IDs"
                        value={workspaceForm.slackReadonly}
                        onChange={(e) => handleWorkspaceChange('slackReadonly', e.target.value)}
                      />
                      <datalist id="slack-channel-options">
                        {slackChannelOptions.map((ch) => (
                          <option key={ch.id} value={ch.name} />
                        ))}
                      </datalist>
                    </>
                  </div>
                  <div>
                    <label
                      htmlFor="slack-blocked-channels"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Blocked channels
                    </label>
                    <>
                      <input
                        id="slack-blocked-channels"
                        type="text"
                        list="slack-channel-options"
                        className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        placeholder="Comma-separated channel names or IDs"
                        value={workspaceForm.slackBlocked}
                        onChange={(e) => handleWorkspaceChange('slackBlocked', e.target.value)}
                      />
                      <datalist id="slack-channel-options">
                        {slackChannelOptions.map((ch) => (
                          <option key={ch.id} value={ch.name} />
                        ))}
                      </datalist>
                    </>
                  </div>
                </div>
              </section>

              {/* Notion */}
              <section>
                <h3 className="text-sm font-semibold text-foreground mb-2">Notion</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label
                      htmlFor="notion-token"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Notion token
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        id="notion-token"
                        type={showNotionToken ? 'text' : 'password'}
                        autoComplete="off"
                        className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        placeholder={
                          workspaceView.notion.token_set
                            ? `Token set (ending with ${workspaceView.notion.token_last4})`
                            : 'Enter Notion integration token'
                        }
                        title="Notion integration token"
                        value={
                          showNotionToken
                            ? workspaceForm.notionToken
                            : workspaceView.notion.token_set && !workspaceForm.notionToken
                              ? MASKED_SECRET
                              : workspaceForm.notionToken
                        }
                        onChange={(event) => handleWorkspaceChange('notionToken', event.target.value)}
                      />
                      {workspaceView.notion.token_set && (
                        <button
                          type="button"
                          onClick={handleToggleNotionTokenVisibility}
                          aria-label={showNotionToken ? 'Hide Notion token' : 'Show Notion token'}
                          title={showNotionToken ? 'Hide Notion token' : 'Show Notion token'}
                          className="inline-flex items-center justify-center text-[11px] text-primary hover:underline whitespace-nowrap"
                        >
                          {showNotionToken ? (
                            <EyeOff className="h-3 w-3" />
                          ) : (
                            <Eye className="h-3 w-3" />
                          )}
                        </button>
                      )}
                    </div>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Existing token is not shown by default; enter a new value to rotate it or use Show to reveal.
                    </p>
                  </div>
                  <div>
                    <label
                      htmlFor="notion-mode"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Mode
                    </label>
                    <select
                      id="notion-mode"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceView.notion.mode}
                      onChange={() => {
                        handleWorkspaceChange('notionParentPageId', workspaceForm.notionParentPageId)
                        // mode is currently read from backend; can be wired later
                      }}
                      disabled
                    >
                      <option value="standard">standard</option>
                      <option value="read_only">read_only</option>
                    </select>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Notion safety mode is currently configured on the backend.
                    </p>
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Parent page ID
                    </label>
                    <input
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      placeholder="Notion page ID used as the root for Slack→Notion workflows"
                      value={workspaceForm.notionParentPageId}
                      onChange={(e) => handleWorkspaceChange('notionParentPageId', e.target.value)}
                    />
                  </div>
                </div>
              </section>

              {/* Gmail policies */}
              <section>
                <h3 className="text-sm font-semibold text-foreground mb-2">Gmail policies</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label
                      htmlFor="gmail-send-mode"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Send mode
                    </label>
                    <select
                      id="gmail-send-mode"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.gmailSendMode}
                      onChange={(e) => handleWorkspaceChange('gmailSendMode', e.target.value)}
                    >
                      <option value="draft">draft (never send)</option>
                      <option value="confirm">confirm (default)</option>
                      <option value="auto_limited">auto_limited</option>
                    </select>
                  </div>
                  <div>
                    <label
                      htmlFor="gmail-default-label"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Default label
                    </label>
                    <>
                      <input
                        id="gmail-default-label"
                        type="text"
                        list="gmail-label-options"
                        className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        value={workspaceForm.gmailDefaultLabel}
                        onChange={(e) => handleWorkspaceChange('gmailDefaultLabel', e.target.value)}
                      />
                      <datalist id="gmail-label-options">
                        {gmailLabelOptions.map((label) => (
                          <option key={label} value={label} />
                        ))}
                      </datalist>
                    </>
                  </div>
                  <div>
                    <label
                      htmlFor="gmail-allowed-send-domains"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Allowed send domains
                    </label>
                    <input
                      id="gmail-allowed-send-domains"
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      placeholder="e.g. @company.com,@partner.com"
                      value={workspaceForm.gmailAllowedSend}
                      onChange={(e) => handleWorkspaceChange('gmailAllowedSend', e.target.value)}
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="gmail-allowed-read-domains"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Allowed read domains
                    </label>
                    <input
                      id="gmail-allowed-read-domains"
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      placeholder="e.g. @company.com"
                      value={workspaceForm.gmailAllowedRead}
                      onChange={(e) => handleWorkspaceChange('gmailAllowedRead', e.target.value)}
                    />
                  </div>
                </div>
              </section>

              {/* Workspace info */}
              <section>
                <h3 className="text-sm font-semibold text-foreground mb-2">Workspace info</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label
                      htmlFor="workspace-name"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Workspace name
                    </label>
                    <input
                      id="workspace-name"
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.workspaceName}
                      onChange={(e) => handleWorkspaceChange('workspaceName', e.target.value)}
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="workspace-id"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Workspace ID
                    </label>
                    <input
                      id="workspace-id"
                      type="text"
                      className="w-full rounded-md border border-border bg-muted px-3 py-1.5 text-sm text-muted-foreground"
                      value={workspaceForm.workspaceId}
                      onChange={(e) => handleWorkspaceChange('workspaceId', e.target.value)}
                    />
                  </div>
                </div>
              </section>

              {/* Runtime / URLs */}
              <section>
                <h3 className="text-sm font-semibold text-foreground mb-2">Runtime & URLs</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label
                      htmlFor="frontend-base-url"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Frontend base URL
                    </label>
                    <input
                      id="frontend-base-url"
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.frontendBaseUrl}
                      onChange={(e) => handleWorkspaceChange('frontendBaseUrl', e.target.value)}
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="api-host"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      API host & port
                    </label>
                    <div className="flex gap-2">
                      <input
                        id="api-host"
                        type="text"
                        className="w-2/3 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        placeholder="0.0.0.0"
                        value={workspaceForm.apiHost}
                        onChange={(e) => handleWorkspaceChange('apiHost', e.target.value)}
                      />
                      <input
                        id="api-port"
                        type="number"
                        className="w-1/3 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        placeholder="8000"
                        value={workspaceForm.apiPort}
                        onChange={(e) => handleWorkspaceChange('apiPort', e.target.value)}
                      />
                    </div>
                  </div>
                  <div>
                    <label
                      htmlFor="log-level"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Log level
                    </label>
                    <input
                      id="log-level"
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.logLevel}
                      onChange={(e) => handleWorkspaceChange('logLevel', e.target.value)}
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="log-file"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Log file
                    </label>
                    <input
                      id="log-file"
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.logFile}
                      onChange={(e) => handleWorkspaceChange('logFile', e.target.value)}
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="tier4-rate-limit"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Rate limits (Tier 4 / Default)
                    </label>
                    <div className="flex gap-2">
                      <input
                        id="tier4-rate-limit"
                        type="number"
                        className="w-1/2 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        title="Tier 4 rate limit"
                        value={workspaceForm.tier4RateLimit}
                        onChange={(e) => handleWorkspaceChange('tier4RateLimit', e.target.value)}
                      />
                      <input
                        id="default-rate-limit"
                        type="number"
                        className="w-1/2 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        title="Default rate limit"
                        value={workspaceForm.defaultRateLimit}
                        onChange={(e) => handleWorkspaceChange('defaultRateLimit', e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-2 mt-6">
                    <input
                      id="socket-mode-enabled"
                      type="checkbox"
                      className="h-3 w-3 rounded border-border text-primary focus:ring-primary"
                      checked={workspaceForm.socketModeEnabled}
                      onChange={(e) => handleWorkspaceChange('socketModeEnabled', e.target.checked)}
                    />
                    <label
                      htmlFor="socket-mode-enabled"
                      className="text-xs text-muted-foreground"
                    >
                      Socket mode enabled (requires app-level Slack Socket token)
                    </label>
                  </div>
                  <div>
                    <label
                      htmlFor="max-reconnect-attempts"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Max reconnect attempts
                    </label>
                    <input
                      id="max-reconnect-attempts"
                      type="number"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      title="Max reconnect attempts"
                      value={workspaceForm.maxReconnectAttempts}
                      onChange={(e) => handleWorkspaceChange('maxReconnectAttempts', e.target.value)}
                    />
                  </div>
                </div>
              </section>

              {/* AI infrastructure (read-only) */}
              <section>
                <h3 className="text-sm font-semibold text-foreground mb-2">AI infrastructure</h3>
                <p className="text-[11px] text-muted-foreground mb-2">
                  Embedding and reranker models are configured at deployment time and shown here for
                  reference. Changing them requires a backend/redeployment change.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                  <div className="rounded-md border border-border bg-muted px-3 py-2">
                    <div className="text-muted-foreground mb-1">Embedding model</div>
                    <div className="font-mono text-foreground break-all">
                      {workspaceView.ai_infra.embedding_model}
                    </div>
                  </div>
                  <div className="rounded-md border border-border bg-muted px-3 py-2">
                    <div className="text-muted-foreground mb-1">Reranker model</div>
                    <div className="font-mono text-foreground break-all">
                      {workspaceView.ai_infra.reranker_model}
                    </div>
                  </div>
                  <div className="rounded-md border border-border bg-muted px-3 py-2">
                    <div className="text-muted-foreground mb-1">Embedding batch size</div>
                    <div className="font-mono text-foreground">
                      {workspaceView.ai_infra.embedding_batch_size}
                    </div>
                  </div>
                  <div className="rounded-md border border-border bg-muted px-3 py-2">
                    <div className="text-muted-foreground mb-1">Use GPU</div>
                    <div className="font-mono text-foreground">
                      {workspaceView.ai_infra.use_gpu ? 'true' : 'false'}
                    </div>
                  </div>
                </div>
              </section>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={handleCancelWorkspace}
                  disabled={!workspaceDirty || savingWorkspace}
                  className="inline-flex items-center justify-center rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSaveWorkspace}
                  disabled={!workspaceDirty || savingWorkspace}
                  className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {savingWorkspace ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// Simple holder for backend defaults when user model is empty
const ConfigFallbacks = {
  llmModel: 'gpt-5-nano',
}

export default ProfileInterface
