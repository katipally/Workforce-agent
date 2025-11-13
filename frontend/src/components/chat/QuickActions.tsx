import { MessageSquare, Mail, FileText, Search, Zap, ArrowRight } from 'lucide-react'

interface QuickAction {
  id: string
  title: string
  description: string
  icon: React.ReactNode
  prompt: string
  category: 'slack' | 'gmail' | 'notion' | 'search'
}

const quickActions: QuickAction[] = [
  {
    id: 'slack-channels',
    title: 'List Slack Channels',
    description: 'See all available channels',
    icon: <MessageSquare className="h-5 w-5" />,
    prompt: 'Get all slack channel names',
    category: 'slack'
  },
  {
    id: 'slack-summary',
    title: 'Summarize Channel',
    description: 'Get activity summary',
    icon: <MessageSquare className="h-5 w-5" />,
    prompt: 'Summarize recent activity in #general',
    category: 'slack'
  },
  {
    id: 'gmail-inbox',
    title: 'Check Inbox',
    description: 'Recent emails',
    icon: <Mail className="h-5 w-5" />,
    prompt: 'Show me my recent emails',
    category: 'gmail'
  },
  {
    id: 'gmail-search',
    title: 'Search Emails',
    description: 'Find specific emails',
    icon: <Mail className="h-5 w-5" />,
    prompt: 'Search emails about',
    category: 'gmail'
  },
  {
    id: 'notion-create',
    title: 'Create Note',
    description: 'New Notion page',
    icon: <FileText className="h-5 w-5" />,
    prompt: 'Create a Notion page titled',
    category: 'notion'
  },
  {
    id: 'workspace-search',
    title: 'Search Everything',
    description: 'Cross-platform search',
    icon: <Search className="h-5 w-5" />,
    prompt: 'Search all platforms for',
    category: 'search'
  }
]

interface WorkflowTemplate {
  id: string
  title: string
  description: string
  steps: string[]
  prompt: string
}

const workflowTemplates: WorkflowTemplate[] = [
  {
    id: 'slack-to-notion',
    title: 'Slack → Notion',
    description: 'Save channel messages to Notion',
    steps: ['Get Slack messages', 'Summarize', 'Create Notion page'],
    prompt: 'Get messages from #channel-name and save summary to Notion'
  },
  {
    id: 'email-digest',
    title: 'Email Digest',
    description: 'Summarize emails and share',
    steps: ['Get emails', 'Generate summary', 'Send to Slack'],
    prompt: 'Get emails from person@email.com and send summary to #team'
  },
  {
    id: 'meeting-prep',
    title: 'Meeting Prep',
    description: 'Gather context for meetings',
    steps: ['Search Slack', 'Search Gmail', 'Create summary'],
    prompt: 'Search all platforms for "project-name" and create a summary'
  }
]

interface QuickActionsProps {
  onActionClick: (prompt: string) => void
  className?: string
}

export default function QuickActions({ onActionClick, className = '' }: QuickActionsProps) {
  const categoryColors = {
    slack: 'bg-purple-50 text-purple-600 hover:bg-purple-100',
    gmail: 'bg-red-50 text-red-600 hover:bg-red-100',
    notion: 'bg-blue-50 text-blue-600 hover:bg-blue-100',
    search: 'bg-green-50 text-green-600 hover:bg-green-100'
  }

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Quick Actions */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Zap className="h-5 w-5 text-yellow-500" />
          <h3 className="text-sm font-semibold text-gray-700">Quick Actions</h3>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {quickActions.map((action) => (
            <button
              key={action.id}
              onClick={() => onActionClick(action.prompt)}
              className={`
                flex items-start gap-3 p-3 rounded-lg border transition-all text-left
                ${categoryColors[action.category]}
              `}
              title={action.description}
            >
              <div className="mt-0.5">{action.icon}</div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{action.title}</div>
                <div className="text-xs opacity-75 truncate">{action.description}</div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Workflow Templates */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <ArrowRight className="h-5 w-5 text-blue-500" />
          <h3 className="text-sm font-semibold text-gray-700">Workflow Templates</h3>
        </div>
        <div className="space-y-2">
          {workflowTemplates.map((workflow) => (
            <button
              key={workflow.id}
              onClick={() => onActionClick(workflow.prompt)}
              className="
                w-full flex items-start gap-3 p-3 rounded-lg border border-gray-200
                bg-white hover:bg-gray-50 hover:border-gray-300 transition-all text-left
              "
            >
              <div className="flex-1">
                <div className="text-sm font-medium text-gray-900 mb-1">{workflow.title}</div>
                <div className="text-xs text-gray-500 mb-2">{workflow.description}</div>
                <div className="flex flex-wrap gap-1">
                  {workflow.steps.map((step, idx) => (
                    <span key={idx}>
                      <span className="text-xs bg-gray-100 px-2 py-0.5 rounded text-gray-600">
                        {step}
                      </span>
                      {idx < workflow.steps.length - 1 && (
                        <span className="text-xs text-gray-400 mx-1">→</span>
                      )}
                    </span>
                  ))}
                </div>
              </div>
              <ArrowRight className="h-4 w-4 text-gray-400 mt-1 flex-shrink-0" />
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
