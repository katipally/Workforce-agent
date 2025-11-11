import { Source } from '../../store/chatStore'
import { Hash, Mail, FileText } from 'lucide-react'

interface SourcesSidebarProps {
  sources: Source[]
}

export default function SourcesSidebar({ sources }: SourcesSidebarProps) {
  if (sources.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="text-center">
          <FileText className="mx-auto h-12 w-12 text-gray-300" />
          <p className="mt-2 text-sm text-gray-500">
            Sources will appear here when the AI cites information
          </p>
        </div>
      </div>
    )
  }
  
  return (
    <div className="h-full overflow-y-auto p-6">
      <h3 className="mb-4 text-lg font-semibold text-gray-900">
        Sources ({sources.length})
      </h3>
      
      <div className="space-y-4">
        {sources.map((source, index) => (
          <SourceCard key={index} source={source} />
        ))}
      </div>
    </div>
  )
}

function SourceCard({ source }: { source: Source }) {
  const { type, text, metadata, rerank_score } = source
  
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm hover:shadow-md transition-shadow">
      <div className="mb-2 flex items-start justify-between">
        <div className="flex items-center gap-2">
          {type === 'slack' ? (
            <Hash className="h-4 w-4 text-purple-600" />
          ) : (
            <Mail className="h-4 w-4 text-blue-600" />
          )}
          <span className="text-xs font-semibold uppercase text-gray-600">
            {type}
          </span>
        </div>
        {rerank_score && (
          <span className="text-xs text-gray-500">
            {(rerank_score * 100).toFixed(0)}% match
          </span>
        )}
      </div>
      
      {type === 'slack' && metadata.channel && (
        <div className="mb-2 text-sm">
          <span className="font-medium text-gray-900">
            #{metadata.channel}
          </span>
          {metadata.user && (
            <span className="text-gray-600"> • {metadata.user}</span>
          )}
          {metadata.timestamp && (
            <span className="text-gray-500 text-xs">
              {' '}• {new Date(metadata.timestamp * 1000).toLocaleString()}
            </span>
          )}
        </div>
      )}
      
      {type === 'gmail' && (
        <div className="mb-2 space-y-1 text-sm">
          {metadata.from && (
            <div>
              <span className="text-gray-600">From:</span>{' '}
              <span className="font-medium text-gray-900">{metadata.from}</span>
            </div>
          )}
          {metadata.subject && (
            <div>
              <span className="text-gray-600">Subject:</span>{' '}
              <span className="font-medium text-gray-900">{metadata.subject}</span>
            </div>
          )}
          {metadata.date && (
            <div className="text-xs text-gray-500">
              {new Date(metadata.date).toLocaleString()}
            </div>
          )}
        </div>
      )}
      
      <p className="text-sm text-gray-700 line-clamp-3">{text}</p>
    </div>
  )
}
