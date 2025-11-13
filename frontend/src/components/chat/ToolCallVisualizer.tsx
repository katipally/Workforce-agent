import { MessageSquare, Mail, FileText, Search, Loader2, CheckCircle, Settings } from 'lucide-react'

interface ToolCall {
  tool: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  result?: string
}

interface ToolCallVisualizerProps {
  toolCalls: ToolCall[]
  isVisible: boolean
}

const toolIcons: Record<string, React.ReactNode> = {
  get_all_slack_channels: <MessageSquare className="h-4 w-4" />,
  get_channel_messages: <MessageSquare className="h-4 w-4" />,
  send_slack_message: <MessageSquare className="h-4 w-4" />,
  get_emails_from_sender: <Mail className="h-4 w-4" />,
  send_gmail: <Mail className="h-4 w-4" />,
  create_notion_page: <FileText className="h-4 w-4" />,
  search_workspace: <Search className="h-4 w-4" />,
  default: <Settings className="h-4 w-4" />
}

const toolNames: Record<string, string> = {
  get_all_slack_channels: 'List Slack Channels',
  get_channel_messages: 'Get Channel Messages',
  send_slack_message: 'Send Slack Message',
  summarize_slack_channel: 'Summarize Channel',
  get_emails_from_sender: 'Get Emails from Sender',
  get_email_by_subject: 'Find Email by Subject',
  send_gmail: 'Send Email',
  search_gmail: 'Search Gmail',
  create_notion_page: 'Create Notion Page',
  list_notion_pages: 'List Notion Pages',
  search_workspace: 'Search Workspace'
}

export default function ToolCallVisualizer({ toolCalls, isVisible }: ToolCallVisualizerProps) {
  if (!isVisible || toolCalls.length === 0) return null

  const getStatusIcon = (status: ToolCall['status']) => {
    switch (status) {
      case 'pending':
        return <div className="h-2 w-2 bg-gray-400 rounded-full" />
      case 'running':
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'failed':
        return <div className="h-4 w-4 text-red-500">✕</div>
      default:
        return null
    }
  }

  const getStatusColor = (status: ToolCall['status']) => {
    switch (status) {
      case 'pending':
        return 'bg-gray-50 border-gray-200'
      case 'running':
        return 'bg-blue-50 border-blue-300'
      case 'completed':
        return 'bg-green-50 border-green-300'
      case 'failed':
        return 'bg-red-50 border-red-300'
      default:
        return 'bg-gray-50 border-gray-200'
    }
  }

  return (
    <div className="px-4 py-3 bg-gray-50 border-t border-gray-200">
      <div className="flex items-center gap-2 mb-2">
        <Settings className="h-4 w-4 text-gray-500" />
        <span className="text-xs font-semibold text-gray-600">AI Agent Tools</span>
      </div>
      <div className="space-y-2">
        {toolCalls.map((call, idx) => (
          <div
            key={idx}
            className={`flex items-center gap-3 px-3 py-2 rounded-lg border transition-all ${getStatusColor(call.status)}`}
          >
            <div className="flex-shrink-0">
              {toolIcons[call.tool] || toolIcons.default}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-gray-900 truncate">
                {toolNames[call.tool] || call.tool}
              </div>
              {call.result && (
                <div className="text-xs text-gray-500 truncate mt-0.5">{call.result}</div>
              )}
            </div>
            <div className="flex-shrink-0">{getStatusIcon(call.status)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
