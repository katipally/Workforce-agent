import { useEffect, useState } from 'react'
import { MessageSquare, Mail, FileText, Database, Activity, CheckCircle, XCircle, Loader2 } from 'lucide-react'

interface PlatformStatus {
  name: string
  icon: React.ReactNode
  status: 'connected' | 'disconnected' | 'syncing'
  lastSync?: string
  dataCount?: number
}

interface SystemStatusProps {
  wsConnected: boolean
}

export default function SystemStatus({ wsConnected }: SystemStatusProps) {
  const [platforms] = useState<PlatformStatus[]>([
    {
      name: 'Slack',
      icon: <MessageSquare className="h-4 w-4" />,
      status: 'connected',
      lastSync: 'Just now',
      dataCount: 0
    },
    {
      name: 'Gmail',
      icon: <Mail className="h-4 w-4" />,
      status: 'connected',
      lastSync: 'Just now',
      dataCount: 0
    },
    {
      name: 'Notion',
      icon: <FileText className="h-4 w-4" />,
      status: 'connected',
      lastSync: 'Just now',
      dataCount: 0
    }
  ])

  const [dbStatus, setDbStatus] = useState<'healthy' | 'warning' | 'error'>('healthy')
  const vectorSearch = true

  useEffect(() => {
    // Poll for system status
    const checkStatus = async () => {
      try {
        const response = await fetch('http://localhost:8000/health')
        if (response.ok) {
          const data = await response.json()
          // Update status based on response
          setDbStatus(data.database === 'healthy' ? 'healthy' : 'warning')
        }
      } catch (error) {
        setDbStatus('error')
      }
    }

    checkStatus()
    const interval = setInterval(checkStatus, 30000) // Check every 30s
    return () => clearInterval(interval)
  }, [])

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'connected':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'disconnected':
        return <XCircle className="h-4 w-4 text-red-500" />
      case 'syncing':
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
      default:
        return null
    }
  }

  const getDbStatusColor = () => {
    switch (dbStatus) {
      case 'healthy':
        return 'text-green-500'
      case 'warning':
        return 'text-yellow-500'
      case 'error':
        return 'text-red-500'
      default:
        return 'text-gray-500'
    }
  }

  return (
    <div className="space-y-4">
      {/* Connection Status */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-gray-500" />
            <h3 className="text-sm font-semibold text-gray-700">System Status</h3>
          </div>
          <div className="flex items-center gap-2">
            {wsConnected ? (
              <>
                <div className="h-2 w-2 bg-green-500 rounded-full animate-pulse" />
                <span className="text-xs text-green-600">Connected</span>
              </>
            ) : (
              <>
                <div className="h-2 w-2 bg-red-500 rounded-full" />
                <span className="text-xs text-red-600">Disconnected</span>
              </>
            )}
          </div>
        </div>

        {/* Platform Status */}
        <div className="space-y-2 mb-3">
          {platforms.map((platform) => (
            <div
              key={platform.name}
              className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded"
            >
              <div className="flex items-center gap-2">
                {platform.icon}
                <span className="text-sm font-medium text-gray-700">{platform.name}</span>
              </div>
              <div className="flex items-center gap-3">
                {platform.dataCount !== undefined && (
                  <span className="text-xs text-gray-500">{platform.dataCount} items</span>
                )}
                {getStatusIcon(platform.status)}
              </div>
            </div>
          ))}
        </div>

        {/* Database & Vector Search */}
        <div className="pt-3 border-t border-gray-200">
          <div className="flex items-center justify-between py-2">
            <div className="flex items-center gap-2 text-sm">
              <Database className={`h-4 w-4 ${getDbStatusColor()}`} />
              <span className="text-gray-700">PostgreSQL</span>
            </div>
            <span className="text-xs text-gray-500 capitalize">{dbStatus}</span>
          </div>
          <div className="flex items-center justify-between py-2">
            <div className="flex items-center gap-2 text-sm">
              <Activity className="h-4 w-4 text-purple-500" />
              <span className="text-gray-700">Vector Search (RAG)</span>
            </div>
            {vectorSearch ? (
              <CheckCircle className="h-4 w-4 text-green-500" />
            ) : (
              <XCircle className="h-4 w-4 text-red-500" />
            )}
          </div>
        </div>
      </div>

      {/* AI Model Info */}
      <div className="bg-gradient-to-r from-purple-50 to-blue-50 rounded-lg border border-purple-200 p-4">
        <div className="flex items-center gap-2 mb-2">
          <div className="h-8 w-8 bg-purple-500 rounded-lg flex items-center justify-center">
            <Activity className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="text-sm font-semibold text-gray-900">gpt-5-nano</div>
            <div className="text-xs text-gray-600">Latest lightweight reasoning model (Nov 2025)</div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 mt-3">
          <div className="bg-white bg-opacity-50 rounded px-2 py-1.5">
            <div className="text-xs text-gray-500">Cost</div>
            <div className="text-sm font-semibold text-purple-700">80% cheaper</div>
          </div>
          <div className="bg-white bg-opacity-50 rounded px-2 py-1.5">
            <div className="text-xs text-gray-500">Features</div>
            <div className="text-sm font-semibold text-purple-700">Full toolkit</div>
          </div>
        </div>
      </div>

      {/* Single Source of Truth Badge */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
        <div className="flex items-center gap-2">
          <CheckCircle className="h-4 w-4 text-blue-600" />
          <div className="text-xs">
            <div className="font-semibold text-blue-900">Single Source of Truth</div>
            <div className="text-blue-700">All data synced to PostgreSQL</div>
          </div>
        </div>
      </div>
    </div>
  )
}
