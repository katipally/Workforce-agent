import React, { useEffect, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { API_BASE_URL } from '../../lib/api'
import { SearchableSelect } from '../common/SearchableSelect'

type WorkspaceSettingsView = {
  system: {
    openai_api_key_set: boolean
    openai_api_key_last4: string
    llm_model: string
    timezone: string | null
    google_client_id: string
    google_client_secret_set: boolean
    google_client_secret_last4: string
    google_oauth_redirect_base: string
    session_secret_set: boolean
    session_secret_last4: string
  }
  slack: {
    bot_token_set: boolean
    bot_token_last4: string
    user_token_set: boolean
    user_token_last4: string
    app_token_set: boolean
    app_token_last4: string
    mode: string
    readonly_channels: string[]
    blocked_channels: string[]
    bot_token_value?: string
    user_token_value?: string
    app_token_value?: string
    app_id: string
    client_id: string
    client_secret: string
    signing_secret: string
    verification_token: string
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

  const [workspaceView, setWorkspaceView] = useState<WorkspaceSettingsView | null>(null)
  const [workspaceForm, setWorkspaceForm] = useState({
    globalOpenaiKey: '',
    globalLlmModel: '',
    globalTimezone: '' as string | '',
    googleClientId: '',
    googleClientSecret: '',
    googleRedirectBase: '',
    slackBotToken: '',
    slackAppToken: '',
    slackUserToken: '',
    slackMode: 'standard',
    slackReadonly: '',
    slackBlocked: '',
    slackAppId: '',
    slackClientId: '',
    slackClientSecret: '',
    slackSigningSecret: '',
    slackVerificationToken: '',
    notionParentPageId: '',
    notionToken: '',
    notionMode: 'standard',
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
    databaseUrl: '',
    dataDir: '',
    filesDir: '',
    exportDir: '',
    projectRegistryFile: '',
    aiEmbeddingModel: '',
    aiRerankerModel: '',
    aiEmbeddingBatchSize: '' as string | '',
    aiUseGpu: false,
  })
  const [workspaceDirty, setWorkspaceDirty] = useState(false)
  const [savingWorkspace, setSavingWorkspace] = useState(false)
  const [syncingWorkspaceFromEnv, setSyncingWorkspaceFromEnv] = useState(false)

  const [showGlobalOpenaiKey, setShowGlobalOpenaiKey] = useState(false)
  const [showGoogleClientSecret, setShowGoogleClientSecret] = useState(false)
  const [showSlackToken, setShowSlackToken] = useState(false)
  const [showNotionToken, setShowNotionToken] = useState(false)
  const [showSlackAdvanced, setShowSlackAdvanced] = useState(false)
  const [showSlackAppToken, setShowSlackAppToken] = useState(false)
  const [showSlackUserToken, setShowSlackUserToken] = useState(false)

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

        const workspaceRes = await fetch(`${API_BASE_URL}/api/settings/workspace`, {
          credentials: 'include',
        })

        if (!workspaceRes.ok) {
          throw new Error('Failed to load workspace settings')
        }

        const workspaceJson = (await workspaceRes.json()) as WorkspaceSettingsView

        setWorkspaceView(workspaceJson)
        setWorkspaceForm({
          globalOpenaiKey: '',
          globalLlmModel: workspaceJson.system.llm_model || '',
          globalTimezone: workspaceJson.system.timezone || '',
          googleClientId: workspaceJson.system.google_client_id || '',
          googleClientSecret: '',
          googleRedirectBase: workspaceJson.system.google_oauth_redirect_base || '',
          slackBotToken: '',
          slackAppToken: '',
          slackUserToken: '',
          slackMode: workspaceJson.slack.mode || 'standard',
          slackReadonly: workspaceJson.slack.readonly_channels.join(', '),
          slackBlocked: workspaceJson.slack.blocked_channels.join(', '),
          slackAppId: workspaceJson.slack.app_id || '',
          slackClientId: workspaceJson.slack.client_id || '',
          slackClientSecret: workspaceJson.slack.client_secret || '',
          slackSigningSecret: workspaceJson.slack.signing_secret || '',
          slackVerificationToken: workspaceJson.slack.verification_token || '',
          notionParentPageId: workspaceJson.notion.parent_page_id || '',
          notionToken: '',
          notionMode: workspaceJson.notion.mode || 'standard',
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
          databaseUrl: workspaceJson.database.database_url || '',
          dataDir: workspaceJson.database.data_dir || '',
          filesDir: workspaceJson.database.files_dir || '',
          exportDir: workspaceJson.database.export_dir || '',
          projectRegistryFile: workspaceJson.database.project_registry_file || '',
          aiEmbeddingModel: workspaceJson.ai_infra.embedding_model || '',
          aiRerankerModel: workspaceJson.ai_infra.reranker_model || '',
          aiEmbeddingBatchSize: String(workspaceJson.ai_infra.embedding_batch_size ?? ''),
          aiUseGpu: workspaceJson.ai_infra.use_gpu,
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

  const handleWorkspaceChange = (field: keyof typeof workspaceForm, value: string | boolean) => {
    setWorkspaceForm((prev) => ({ ...prev, [field]: value as any }))
    setWorkspaceDirty(true)
  }

  const handleToggleGlobalOpenaiKeyVisibility = async () => {
    if (!workspaceView) return

    if (!showGlobalOpenaiKey) {
      if (workspaceForm.globalOpenaiKey) {
        setShowGlobalOpenaiKey(true)
        return
      }

      if (workspaceView.system.openai_api_key_set) {
        try {
          const res = await fetch(`${API_BASE_URL}/api/settings/workspace?include_secrets=true`, {
            credentials: 'include',
          })
          if (res.ok) {
            const data = (await res.json()) as WorkspaceSettingsView
            setWorkspaceView(data)
            setWorkspaceForm((prev) => ({
              ...prev,
              globalOpenaiKey: prev.globalOpenaiKey || (data as any).system.openai_api_key_value || '',
            }))
          }
        } catch (e: any) {
          setError(e?.message || 'Failed to load global OpenAI key')
        }
      }

      setShowGlobalOpenaiKey(true)
    } else {
      setShowGlobalOpenaiKey(false)
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

  const handleToggleSlackAppTokenVisibility = async () => {
    if (!workspaceView) return

    if (!showSlackAppToken) {
      if (workspaceForm.slackAppToken) {
        setShowSlackAppToken(true)
        return
      }

      if (workspaceView.slack.app_token_value) {
        setWorkspaceForm((prev) => ({
          ...prev,
          slackAppToken: prev.slackAppToken || workspaceView.slack.app_token_value || '',
        }))
        setShowSlackAppToken(true)
        return
      }

      if (
        workspaceView.slack.app_token_set ||
        workspaceView.slack.bot_token_set ||
        workspaceView.slack.user_token_set ||
        workspaceView.notion.token_set
      ) {
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
              slackAppToken: prev.slackAppToken || data.slack.app_token_value || '',
              slackUserToken: prev.slackUserToken || data.slack.user_token_value || '',
            }))
          }
        } catch (e: any) {
          setError(e?.message || 'Failed to load Slack secret')
        }
      }

      setShowSlackAppToken(true)
    } else {
      setShowSlackAppToken(false)
    }
  }

  const handleToggleSlackUserTokenVisibility = async () => {
    if (!workspaceView) return

    if (!showSlackUserToken) {
      if (workspaceForm.slackUserToken) {
        setShowSlackUserToken(true)
        return
      }

      if (workspaceView.slack.user_token_value) {
        setWorkspaceForm((prev) => ({
          ...prev,
          slackUserToken: prev.slackUserToken || workspaceView.slack.user_token_value || '',
        }))
        setShowSlackUserToken(true)
        return
      }

      if (
        workspaceView.slack.user_token_set ||
        workspaceView.slack.bot_token_set ||
        workspaceView.slack.app_token_set ||
        workspaceView.notion.token_set
      ) {
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
              slackAppToken: prev.slackAppToken || data.slack.app_token_value || '',
              slackUserToken: prev.slackUserToken || data.slack.user_token_value || '',
            }))
          }
        } catch (e: any) {
          setError(e?.message || 'Failed to load Slack secret')
        }
      }

      setShowSlackUserToken(true)
    } else {
      setShowSlackUserToken(false)
    }
  }

  const handleSaveWorkspace = async () => {
    if (!workspaceView || !workspaceDirty) return
    try {
      setSavingWorkspace(true)
      setError(null)

      const payload: any = {}

      // System / global
      const system: any = {}
      if (workspaceForm.globalOpenaiKey.trim()) {
        system.openai_api_key = workspaceForm.globalOpenaiKey.trim()
      }
      if (workspaceForm.globalLlmModel !== workspaceView.system.llm_model) {
        system.llm_model = workspaceForm.globalLlmModel || null
      }
      if ((workspaceForm.globalTimezone || null) !== (workspaceView.system.timezone || null)) {
        system.timezone = workspaceForm.globalTimezone || null
      }
      if (workspaceForm.googleClientId !== workspaceView.system.google_client_id) {
        system.google_client_id = workspaceForm.googleClientId || null
      }
      if (workspaceForm.googleClientSecret.trim()) {
        system.google_client_secret = workspaceForm.googleClientSecret.trim()
      }
      if (
        workspaceForm.googleRedirectBase !==
        (workspaceView.system.google_oauth_redirect_base || '')
      ) {
        system.google_oauth_redirect_base = workspaceForm.googleRedirectBase || null
      }
      if (Object.keys(system).length > 0) {
        payload.system = system
      }

      // Slack
      const slack: any = {}
      if (workspaceForm.slackBotToken.trim()) {
        slack.bot_token = workspaceForm.slackBotToken.trim()
      }
      if (workspaceForm.slackAppToken.trim()) {
        slack.app_token = workspaceForm.slackAppToken.trim()
      }
      if (workspaceForm.slackUserToken.trim()) {
        slack.user_token = workspaceForm.slackUserToken.trim()
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
      if (workspaceForm.slackAppId !== (workspaceView.slack.app_id || '')) {
        slack.app_id = workspaceForm.slackAppId || null
      }
      if (workspaceForm.slackClientId !== (workspaceView.slack.client_id || '')) {
        slack.client_id = workspaceForm.slackClientId || null
      }
      if (workspaceForm.slackClientSecret !== (workspaceView.slack.client_secret || '')) {
        slack.client_secret = workspaceForm.slackClientSecret || null
      }
      if (workspaceForm.slackSigningSecret !== (workspaceView.slack.signing_secret || '')) {
        slack.signing_secret = workspaceForm.slackSigningSecret || null
      }
      if (workspaceForm.slackVerificationToken !== (workspaceView.slack.verification_token || '')) {
        slack.verification_token = workspaceForm.slackVerificationToken || null
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
      if (workspaceForm.notionMode !== workspaceView.notion.mode) {
        notion.mode = workspaceForm.notionMode
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
      if (workspaceForm.databaseUrl !== workspaceView.database.database_url) {
        database.database_url = workspaceForm.databaseUrl || null
      }
      if (workspaceForm.dataDir !== workspaceView.database.data_dir) {
        database.data_dir = workspaceForm.dataDir || null
      }
      if (workspaceForm.filesDir !== workspaceView.database.files_dir) {
        database.files_dir = workspaceForm.filesDir || null
      }
      if (workspaceForm.exportDir !== workspaceView.database.export_dir) {
        database.export_dir = workspaceForm.exportDir || null
      }
      if (workspaceForm.projectRegistryFile !== workspaceView.database.project_registry_file) {
        database.project_registry_file = workspaceForm.projectRegistryFile || null
      }
      if (Object.keys(database).length > 0) {
        payload.database = database
      }

      // AI infrastructure
      const aiInfra: any = {}
      if (workspaceForm.aiEmbeddingModel !== workspaceView.ai_infra.embedding_model) {
        aiInfra.embedding_model = workspaceForm.aiEmbeddingModel || null
      }
      if (workspaceForm.aiRerankerModel !== workspaceView.ai_infra.reranker_model) {
        aiInfra.reranker_model = workspaceForm.aiRerankerModel || null
      }
      if (
        workspaceForm.aiEmbeddingBatchSize !==
        String(workspaceView.ai_infra.embedding_batch_size ?? '')
      ) {
        aiInfra.embedding_batch_size = workspaceForm.aiEmbeddingBatchSize
          ? Number(workspaceForm.aiEmbeddingBatchSize)
          : null
      }
      if (workspaceForm.aiUseGpu !== workspaceView.ai_infra.use_gpu) {
        aiInfra.use_gpu = workspaceForm.aiUseGpu
      }
      if (Object.keys(aiInfra).length > 0) {
        payload.ai_infra = aiInfra
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
        globalOpenaiKey: '',
        globalLlmModel: updated.system.llm_model || '',
        globalTimezone: updated.system.timezone || '',
        googleClientId: updated.system.google_client_id || '',
        googleClientSecret: '',
        googleRedirectBase: updated.system.google_oauth_redirect_base || '',
        slackBotToken: '',
        slackAppToken: '',
        slackUserToken: '',
        slackMode: updated.slack.mode || 'standard',
        slackReadonly: updated.slack.readonly_channels.join(', '),
        slackBlocked: updated.slack.blocked_channels.join(', '),
        slackAppId: updated.slack.app_id || '',
        slackClientId: updated.slack.client_id || '',
        slackClientSecret: updated.slack.client_secret || '',
        slackSigningSecret: updated.slack.signing_secret || '',
        slackVerificationToken: updated.slack.verification_token || '',
        notionParentPageId: updated.notion.parent_page_id || '',
        notionToken: '',
        notionMode: updated.notion.mode || 'standard',
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
        databaseUrl: updated.database.database_url || '',
        dataDir: updated.database.data_dir || '',
        filesDir: updated.database.files_dir || '',
        exportDir: updated.database.export_dir || '',
        projectRegistryFile: updated.database.project_registry_file || '',
        aiEmbeddingModel: updated.ai_infra.embedding_model || '',
        aiRerankerModel: updated.ai_infra.reranker_model || '',
        aiEmbeddingBatchSize: String(updated.ai_infra.embedding_batch_size ?? ''),
        aiUseGpu: updated.ai_infra.use_gpu,
      })
      setWorkspaceDirty(false)
      void reloadSuggestions()
    } catch (e: any) {
      setError(e?.message || 'Failed to save workspace settings')
    } finally {
      setSavingWorkspace(false)
    }
  }

  const handleSyncWorkspaceFromEnv = async () => {
    if (!workspaceView) return
    try {
      setSyncingWorkspaceFromEnv(true)
      setError(null)

      const res = await fetch(`${API_BASE_URL}/api/settings/workspace/sync-from-env`, {
        method: 'POST',
        credentials: 'include',
      })

      if (!res.ok) {
        throw new Error('Failed to sync workspace settings from env')
      }

      const updated = (await res.json()) as WorkspaceSettingsView
      setWorkspaceView(updated)
      setWorkspaceForm({
        globalOpenaiKey: '',
        globalLlmModel: updated.system.llm_model || '',
        globalTimezone: updated.system.timezone || '',
        googleClientId: updated.system.google_client_id || '',
        googleClientSecret: '',
        googleRedirectBase: updated.system.google_oauth_redirect_base || '',
        slackBotToken: '',
        slackAppToken: '',
        slackUserToken: '',
        slackMode: updated.slack.mode || 'standard',
        slackReadonly: updated.slack.readonly_channels.join(', '),
        slackBlocked: updated.slack.blocked_channels.join(', '),
        slackAppId: updated.slack.app_id || '',
        slackClientId: updated.slack.client_id || '',
        slackClientSecret: updated.slack.client_secret || '',
        slackSigningSecret: updated.slack.signing_secret || '',
        slackVerificationToken: updated.slack.verification_token || '',
        notionParentPageId: updated.notion.parent_page_id || '',
        notionToken: '',
        notionMode: updated.notion.mode || 'standard',
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
        databaseUrl: updated.database.database_url || '',
        dataDir: updated.database.data_dir || '',
        filesDir: updated.database.files_dir || '',
        exportDir: updated.database.export_dir || '',
        projectRegistryFile: updated.database.project_registry_file || '',
        aiEmbeddingModel: updated.ai_infra.embedding_model || '',
        aiRerankerModel: updated.ai_infra.reranker_model || '',
        aiEmbeddingBatchSize: String(updated.ai_infra.embedding_batch_size ?? ''),
        aiUseGpu: updated.ai_infra.use_gpu,
      })
      setWorkspaceDirty(false)
      setShowSlackToken(false)
      setShowNotionToken(false)
      setShowSlackAppToken(false)
      setShowSlackUserToken(false)
      setShowGlobalOpenaiKey(false)
      setShowGoogleClientSecret(false)
      void reloadSuggestions()
    } catch (e: any) {
      setError(e?.message || 'Failed to sync workspace settings from env')
    } finally {
      setSyncingWorkspaceFromEnv(false)
    }
  }

  const handleCancelWorkspace = () => {
    if (!workspaceView) return
    setWorkspaceForm({
      globalOpenaiKey: '',
      globalLlmModel: workspaceView.system.llm_model || '',
      globalTimezone: workspaceView.system.timezone || '',
      googleClientId: workspaceView.system.google_client_id || '',
      googleClientSecret: '',
      googleRedirectBase: workspaceView.system.google_oauth_redirect_base || '',
      slackBotToken: '',
      slackAppToken: '',
      slackUserToken: '',
      slackMode: workspaceView.slack.mode || 'standard',
      slackReadonly: workspaceView.slack.readonly_channels.join(', '),
      slackBlocked: workspaceView.slack.blocked_channels.join(', '),
      slackAppId: workspaceView.slack.app_id || '',
      slackClientId: workspaceView.slack.client_id || '',
      slackClientSecret: workspaceView.slack.client_secret || '',
      slackSigningSecret: workspaceView.slack.signing_secret || '',
      slackVerificationToken: workspaceView.slack.verification_token || '',
      notionParentPageId: workspaceView.notion.parent_page_id || '',
      notionToken: '',
      notionMode: workspaceView.notion.mode || 'standard',
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
      databaseUrl: workspaceView.database.database_url || '',
      dataDir: workspaceView.database.data_dir || '',
      filesDir: workspaceView.database.files_dir || '',
      exportDir: workspaceView.database.export_dir || '',
      projectRegistryFile: workspaceView.database.project_registry_file || '',
      aiEmbeddingModel: workspaceView.ai_infra.embedding_model || '',
      aiRerankerModel: workspaceView.ai_infra.reranker_model || '',
      aiEmbeddingBatchSize: String(workspaceView.ai_infra.embedding_batch_size ?? ''),
      aiUseGpu: workspaceView.ai_infra.use_gpu,
    })
    setWorkspaceDirty(false)
    setShowSlackToken(false)
    setShowNotionToken(false)
    setShowSlackAppToken(false)
    setShowSlackUserToken(false)
    setShowGlobalOpenaiKey(false)
    setShowGoogleClientSecret(false)
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

        {/* Workspace Settings tile (includes system/global, Slack, Notion, Gmail, DB, AI, etc.) */}
        {workspaceView && (
          <div className="border border-border rounded-xl bg-card p-6 shadow-sm">
            <h2 className="text-lg font-semibold mb-4 text-foreground">Workspace settings</h2>
            <p className="text-xs text-muted-foreground mb-4">
              Changes here affect all users in this workspace. For now, all users can edit these settings.
            </p>

            <div className="space-y-6 text-sm">
              {/* System / Global configuration */}
              <section>
                <h3 className="text-sm font-semibold text-foreground mb-2">System configuration</h3>
                <p className="text-[11px] text-muted-foreground mb-2">
                  Global AI and OAuth settings for this workspace. Changes apply to all users.
                </p>

                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      OpenAI API key (global)
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        type={showGlobalOpenaiKey ? 'text' : 'password'}
                        autoComplete="off"
                        className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        placeholder={
                          workspaceView.system.openai_api_key_set
                            ? `Key set (ending with ${workspaceView.system.openai_api_key_last4})`
                            : 'Enter global OpenAI API key'
                        }
                        value={
                          showGlobalOpenaiKey
                            ? workspaceForm.globalOpenaiKey
                            : workspaceView.system.openai_api_key_set && !workspaceForm.globalOpenaiKey
                              ? MASKED_SECRET
                              : workspaceForm.globalOpenaiKey
                        }
                        onChange={(e) => handleWorkspaceChange('globalOpenaiKey', e.target.value)}
                      />
                      {workspaceView.system.openai_api_key_set && (
                        <button
                          type="button"
                          onClick={handleToggleGlobalOpenaiKeyVisibility}
                          aria-label={showGlobalOpenaiKey ? 'Hide OpenAI key' : 'Show OpenAI key'}
                          title={showGlobalOpenaiKey ? 'Hide OpenAI key' : 'Show OpenAI key'}
                          className="inline-flex items-center justify-center text-[11px] text-primary hover:underline whitespace-nowrap"
                        >
                          {showGlobalOpenaiKey ? (
                            <EyeOff className="h-3 w-3" />
                          ) : (
                            <Eye className="h-3 w-3" />
                          )}
                        </button>
                      )}
                    </div>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Used as the default OpenAI key for all users when calling the agent.
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label
                        htmlFor="global-default-model"
                        className="block text-xs font-medium text-muted-foreground mb-1"
                      >
                        Default LLM model
                      </label>
                      <input
                        id="global-default-model"
                        type="text"
                        className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        value={workspaceForm.globalLlmModel}
                        onChange={(e) => handleWorkspaceChange('globalLlmModel', e.target.value)}
                      />
                    </div>
                    <div>
                      <label
                        htmlFor="global-timezone"
                        className="block text-xs font-medium text-muted-foreground mb-1"
                      >
                        Default timezone
                      </label>
                      <input
                        id="global-timezone"
                        type="text"
                        list="timezone-options"
                        className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        placeholder="e.g. America/Los_Angeles"
                        value={workspaceForm.globalTimezone}
                        onChange={(e) => handleWorkspaceChange('globalTimezone', e.target.value)}
                      />
                      <datalist id="timezone-options">
                        {timezoneOptions.map((tz) => (
                          <option key={tz} value={tz} />
                        ))}
                      </datalist>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label
                        htmlFor="google-client-id"
                        className="block text-xs font-medium text-muted-foreground mb-1"
                      >
                        Google OAuth client ID
                      </label>
                      <input
                        id="google-client-id"
                        type="text"
                        className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        value={workspaceForm.googleClientId}
                        onChange={(e) => handleWorkspaceChange('googleClientId', e.target.value)}
                      />
                    </div>
                    <div>
                      <label
                        htmlFor="google-client-secret"
                        className="block text-xs font-medium text-muted-foreground mb-1"
                      >
                        Google OAuth client secret
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          id="google-client-secret"
                          type={showGoogleClientSecret ? 'text' : 'password'}
                          autoComplete="off"
                          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                          placeholder={
                            workspaceView.system.google_client_secret_set
                              ? `Secret set (ending with ${workspaceView.system.google_client_secret_last4})`
                              : 'Enter Google OAuth client secret'
                          }
                          value={
                            showGoogleClientSecret
                              ? workspaceForm.googleClientSecret
                              : workspaceView.system.google_client_secret_set && !workspaceForm.googleClientSecret
                                ? MASKED_SECRET
                                : workspaceForm.googleClientSecret
                          }
                          onChange={(e) => handleWorkspaceChange('googleClientSecret', e.target.value)}
                        />
                        {workspaceView.system.google_client_secret_set && (
                          <button
                            type="button"
                            onClick={() => setShowGoogleClientSecret((prev) => !prev)}
                            aria-label={
                              showGoogleClientSecret ? 'Hide Google client secret' : 'Show Google client secret'
                            }
                            title={showGoogleClientSecret ? 'Hide Google client secret' : 'Show Google client secret'}
                            className="inline-flex items-center justify-center text-[11px] text-primary hover:underline whitespace-nowrap"
                          >
                            {showGoogleClientSecret ? (
                              <EyeOff className="h-3 w-3" />
                            ) : (
                              <Eye className="h-3 w-3" />
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  <div>
                    <label
                      htmlFor="google-redirect-base"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Google OAuth redirect base
                    </label>
                    <input
                      id="google-redirect-base"
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.googleRedirectBase}
                      onChange={(e) => handleWorkspaceChange('googleRedirectBase', e.target.value)}
                    />
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Must match the base URL used in your Google Cloud OAuth redirect URI.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Session secret (read-only)
                    </label>
                    <input
                      type="password"
                      readOnly
                      className="w-full rounded-md border border-border bg-muted px-3 py-1.5 text-sm text-muted-foreground"
                      placeholder={
                        workspaceView.system.session_secret_set
                          ? `Configured (ending with ${workspaceView.system.session_secret_last4})`
                          : 'Not configured – set SESSION_SECRET in .env'
                      }
                      value=""
                    />
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Change this only in .env. Rotating it without migration will invalidate stored secrets.
                    </p>
                  </div>
                </div>
              </section>

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
                    <SearchableSelect
                      id="slack-mode"
                      value={workspaceForm.slackMode}
                      onChange={(next) => handleWorkspaceChange('slackMode', next)}
                      options={[
                        { value: 'read_only', label: 'read_only' },
                        { value: 'standard', label: 'standard' },
                        { value: 'admin', label: 'admin' },
                      ]}
                      searchPlaceholder="Search Slack modes…"
                      fullWidth
                      triggerClassName="px-3 py-1.5 text-sm"
                    />
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
                  <div className="md:col-span-2 border-t border-border pt-3 mt-1 space-y-3">
                    <button
                      type="button"
                      onClick={() => setShowSlackAdvanced((prev) => !prev)}
                      className="inline-flex items-center justify-center rounded-md border border-border bg-background px-2 py-1 text-[11px] font-medium text-foreground hover:bg-muted"
                      aria-controls="slack-advanced-panel"
                    >
                      {showSlackAdvanced ? 'Hide advanced Slack app configuration' : 'Show advanced Slack app configuration'}
                    </button>
                    {showSlackAdvanced && (
                      <div
                        id="slack-advanced-panel"
                        className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2"
                      >
                        <div>
                          <label
                            htmlFor="slack-app-token"
                            className="block text-xs font-medium text-muted-foreground mb-1"
                          >
                            App token (Socket Mode)
                          </label>
                          <div className="flex items-center gap-2">
                            <input
                              id="slack-app-token"
                              type={showSlackAppToken ? 'text' : 'password'}
                              autoComplete="off"
                              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                              placeholder={
                                workspaceView.slack.app_token_set
                                  ? `Token set (ending with ${workspaceView.slack.app_token_last4})`
                                  : 'Enter Slack app token (for Socket Mode)'
                              }
                              value={
                                showSlackAppToken
                                  ? workspaceForm.slackAppToken
                                  : workspaceView.slack.app_token_set && !workspaceForm.slackAppToken
                                    ? MASKED_SECRET
                                    : workspaceForm.slackAppToken
                              }
                              onChange={(e) => handleWorkspaceChange('slackAppToken', e.target.value)}
                            />
                            {workspaceView.slack.app_token_set && (
                              <button
                                type="button"
                                onClick={handleToggleSlackAppTokenVisibility}
                                aria-label={showSlackAppToken ? 'Hide Slack app token' : 'Show Slack app token'}
                                title={showSlackAppToken ? 'Hide Slack app token' : 'Show Slack app token'}
                                className="inline-flex items-center justify-center text-[11px] text-primary hover:underline whitespace-nowrap"
                              >
                                {showSlackAppToken ? (
                                  <EyeOff className="h-3 w-3" />
                                ) : (
                                  <Eye className="h-3 w-3" />
                                )}
                              </button>
                            )}
                          </div>
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            Required when using Slack Socket Mode for real-time events.
                          </p>
                        </div>
                        <div>
                          <label
                            htmlFor="slack-user-token"
                            className="block text-xs font-medium text-muted-foreground mb-1"
                          >
                            User token (optional)
                          </label>
                          <div className="flex items-center gap-2">
                            <input
                              id="slack-user-token"
                              type={showSlackUserToken ? 'text' : 'password'}
                              autoComplete="off"
                              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                              placeholder={
                                workspaceView.slack.user_token_set
                                  ? `Token set (ending with ${workspaceView.slack.user_token_last4})`
                                  : 'Enter Slack user token (optional)'
                              }
                              value={
                                showSlackUserToken
                                  ? workspaceForm.slackUserToken
                                  : workspaceView.slack.user_token_set && !workspaceForm.slackUserToken
                                    ? MASKED_SECRET
                                    : workspaceForm.slackUserToken
                              }
                              onChange={(e) => handleWorkspaceChange('slackUserToken', e.target.value)}
                            />
                            {workspaceView.slack.user_token_set && (
                              <button
                                type="button"
                                onClick={handleToggleSlackUserTokenVisibility}
                                aria-label={showSlackUserToken ? 'Hide Slack user token' : 'Show Slack user token'}
                                title={showSlackUserToken ? 'Hide Slack user token' : 'Show Slack user token'}
                                className="inline-flex items-center justify-center text-[11px] text-primary hover:underline whitespace-nowrap"
                              >
                                {showSlackUserToken ? (
                                  <EyeOff className="h-3 w-3" />
                                ) : (
                                  <Eye className="h-3 w-3" />
                                )}
                              </button>
                            )}
                          </div>
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            Used for actions that require a user context instead of the bot.
                          </p>
                        </div>
                        <div>
                          <label
                            htmlFor="slack-app-id"
                            className="block text-xs font-medium text-muted-foreground mb-1"
                          >
                            App ID
                          </label>
                          <input
                            id="slack-app-id"
                            type="text"
                            className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                            value={workspaceForm.slackAppId}
                            onChange={(e) => handleWorkspaceChange('slackAppId', e.target.value)}
                          />
                        </div>
                        <div>
                          <label
                            htmlFor="slack-client-id"
                            className="block text-xs font-medium text-muted-foreground mb-1"
                          >
                            Client ID
                          </label>
                          <input
                            id="slack-client-id"
                            type="text"
                            className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                            value={workspaceForm.slackClientId}
                            onChange={(e) => handleWorkspaceChange('slackClientId', e.target.value)}
                          />
                        </div>
                        <div>
                          <label
                            htmlFor="slack-client-secret"
                            className="block text-xs font-medium text-muted-foreground mb-1"
                          >
                            Client secret
                          </label>
                          <div className="flex items-center gap-2">
                            <input
                              id="slack-client-secret"
                              type="text"
                              autoComplete="off"
                              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                              value={workspaceForm.slackClientSecret}
                              onChange={(e) => handleWorkspaceChange('slackClientSecret', e.target.value)}
                            />
                          </div>
                        </div>
                        <div>
                          <label
                            htmlFor="slack-signing-secret"
                            className="block text-xs font-medium text-muted-foreground mb-1"
                          >
                            Signing secret
                          </label>
                          <div className="flex items-center gap-2">
                            <input
                              id="slack-signing-secret"
                              type="text"
                              autoComplete="off"
                              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                              value={workspaceForm.slackSigningSecret}
                              onChange={(e) => handleWorkspaceChange('slackSigningSecret', e.target.value)}
                            />
                          </div>
                        </div>
                        <div>
                          <label
                            htmlFor="slack-verification-token"
                            className="block text-xs font-medium text-muted-foreground mb-1"
                          >
                            Verification token
                          </label>
                          <div className="flex items-center gap-2">
                            <input
                              id="slack-verification-token"
                              type="text"
                              autoComplete="off"
                              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                              value={workspaceForm.slackVerificationToken}
                              onChange={(e) => handleWorkspaceChange('slackVerificationToken', e.target.value)}
                            />
                          </div>
                        </div>
                      </div>
                    )}
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
                    <SearchableSelect
                      id="notion-mode"
                      value={workspaceForm.notionMode}
                      onChange={(next) => handleWorkspaceChange('notionMode', next)}
                      options={[
                        { value: 'standard', label: 'standard' },
                        { value: 'read_only', label: 'read_only' },
                      ]}
                      searchPlaceholder="Search Notion modes…"
                      fullWidth
                      triggerClassName="px-3 py-1.5 text-sm"
                    />
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Controls how the agent interacts with Notion (read-only vs standard).
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

              {/* Gmail & Google */}
              <section>
                <h3 className="text-sm font-semibold text-foreground mb-2">Gmail &amp; Google</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label
                      htmlFor="gmail-send-mode"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Send mode
                    </label>
                    <SearchableSelect
                      id="gmail-send-mode"
                      value={workspaceForm.gmailSendMode}
                      onChange={(next) => handleWorkspaceChange('gmailSendMode', next)}
                      options={[
                        { value: 'draft', label: 'draft (never send)' },
                        { value: 'confirm', label: 'confirm (default)' },
                        { value: 'auto_limited', label: 'auto_limited' },
                      ]}
                      searchPlaceholder="Search Gmail send modes…"
                      fullWidth
                      triggerClassName="px-3 py-1.5 text-sm"
                    />
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

              {/* Database & storage */}
              <section>
                <h3 className="text-sm font-semibold text-foreground mb-2">Database & storage</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label
                      htmlFor="database-url"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Database URL
                    </label>
                    <input
                      id="database-url"
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.databaseUrl}
                      onChange={(e) => handleWorkspaceChange('databaseUrl', e.target.value)}
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="data-dir"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Data directory
                    </label>
                    <input
                      id="data-dir"
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.dataDir}
                      onChange={(e) => handleWorkspaceChange('dataDir', e.target.value)}
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="files-dir"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Files directory
                    </label>
                    <input
                      id="files-dir"
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.filesDir}
                      onChange={(e) => handleWorkspaceChange('filesDir', e.target.value)}
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="export-dir"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Export directory
                    </label>
                    <input
                      id="export-dir"
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.exportDir}
                      onChange={(e) => handleWorkspaceChange('exportDir', e.target.value)}
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label
                      htmlFor="project-registry-file"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Project registry file
                    </label>
                    <input
                      id="project-registry-file"
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.projectRegistryFile}
                      onChange={(e) => handleWorkspaceChange('projectRegistryFile', e.target.value)}
                    />
                  </div>
                </div>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Changes here are written to .env. Some changes may require a manual backend restart to
                  fully take effect.
                </p>
              </section>

              {/* AI infrastructure */}
              <section>
                <h3 className="text-sm font-semibold text-foreground mb-2">AI infrastructure</h3>
                <p className="text-[11px] text-muted-foreground mb-2">
                  Control embedding and reranker models used by the agent. Changes are applied on the next
                  request after saving.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label
                      htmlFor="ai-embedding-model"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Embedding model
                    </label>
                    <input
                      id="ai-embedding-model"
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.aiEmbeddingModel}
                      onChange={(e) => handleWorkspaceChange('aiEmbeddingModel', e.target.value)}
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="ai-reranker-model"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Reranker model
                    </label>
                    <input
                      id="ai-reranker-model"
                      type="text"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.aiRerankerModel}
                      onChange={(e) => handleWorkspaceChange('aiRerankerModel', e.target.value)}
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="ai-embedding-batch-size"
                      className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                      Embedding batch size
                    </label>
                    <input
                      id="ai-embedding-batch-size"
                      type="number"
                      className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      value={workspaceForm.aiEmbeddingBatchSize}
                      onChange={(e) => handleWorkspaceChange('aiEmbeddingBatchSize', e.target.value)}
                    />
                  </div>
                  <div className="flex items-center gap-2 mt-6">
                    <input
                      id="ai-use-gpu"
                      type="checkbox"
                      className="h-3 w-3 rounded border-border text-primary focus:ring-primary"
                      checked={workspaceForm.aiUseGpu}
                      onChange={(e) => handleWorkspaceChange('aiUseGpu', e.target.checked)}
                    />
                    <label htmlFor="ai-use-gpu" className="text-xs text-muted-foreground">
                      Use GPU for embeddings and reranking when available
                    </label>
                  </div>
                </div>
              </section>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={handleSyncWorkspaceFromEnv}
                  disabled={savingWorkspace || syncingWorkspaceFromEnv}
                  className="inline-flex items-center justify-center rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground disabled:opacity-50"
                >
                  {syncingWorkspaceFromEnv ? 'Syncing…' : 'Sync from env'}
                </button>
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
export default ProfileInterface
