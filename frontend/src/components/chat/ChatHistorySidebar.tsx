import { useEffect, useState } from 'react'
import { useChatStore, ChatSession } from '../../store/chatStore'
import { API_BASE_URL } from '../../lib/api'
import { MessageSquare, Plus, Trash2, Loader2 } from 'lucide-react'

export default function ChatHistorySidebar() {
  const { currentSessionId, setCurrentSessionId, createNewSession, setSessions, sessions, loadSessionMessages, deleteSession } = useChatStore()
  const [loading, setLoading] = useState(false)

  // Load sessions on mount
  useEffect(() => {
    loadSessions(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadSessions = async (createFreshNewChat: boolean = false) => {
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/sessions`, {
        credentials: 'include',
      })
      const data = await response.json()
      setSessions(data.sessions || [])

      // After loading existing sessions from the backend, create a fresh
      // local "New Chat" session so the user always has a brand-new
      // conversation ready at the top when the app first loads.
      if (createFreshNewChat) {
        createNewSession()
      }
    } catch (error) {
      console.error('Error loading sessions:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleNewChat = () => {
    // Create a new local session immediately so the sidebar updates.
    // The backend session row will be created lazily on first message send.
    createNewSession()
  }

  const handleSelectSession = async (sessionId: string) => {
    if (sessionId === currentSessionId) return

    try {
      // Load messages for this session from backend
      await loadSessionMessages(sessionId)
      // Switch to this session
      setCurrentSessionId(sessionId)
    } catch (error) {
      console.error('Error loading session:', error)
    }
  }

  const handleDeleteSession = async (sessionId: string, event: React.MouseEvent) => {
    event.stopPropagation()
    
    if (!confirm('Delete this conversation?')) return

    try {
      // Use store's deleteSession which handles everything
      deleteSession(sessionId)
      // Reload sessions list from backend
      await loadSessions(false)
    } catch (error) {
      console.error('Error deleting session:', error)
    }
  }

  return (
    <div className="flex h-full flex-col bg-gray-900 text-white">
      {/* Header */}
      <div className="border-b border-gray-800 p-4">
        <button
          onClick={handleNewChat}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </button>
      </div>

      {/* Sessions list */}
      <div className="flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-gray-400">
            No conversations yet
          </div>
        ) : (
          <div className="space-y-1">
            {sessions.map((session: ChatSession) => (
              <button
                key={session.session_id}
                onClick={() => handleSelectSession(session.session_id)}
                className={`group relative flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
                  session.session_id === currentSessionId
                    ? 'bg-gray-800 text-white'
                    : 'text-gray-300 hover:bg-gray-800/50'
                }`}
              >
                <MessageSquare className="mt-0.5 h-4 w-4 flex-shrink-0" />
                <div className="flex-1 overflow-hidden">
                  <div className="truncate text-sm font-medium">
                    {session.title || 'New Chat'}
                  </div>
                  <div className="truncate text-xs text-gray-500">
                    {new Date(session.updated_at).toLocaleDateString()}
                  </div>
                </div>
                <button
                  onClick={(e) => handleDeleteSession(session.session_id, e)}
                  className="flex-shrink-0 opacity-0 transition-opacity group-hover:opacity-100 hover:text-red-400"
                  title="Delete conversation"
                  aria-label="Delete conversation"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
