import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  timestamp: Date
}

export interface Source {
  type: 'slack' | 'gmail'
  text: string
  score?: number
  rerank_score?: number
  metadata: {
    channel?: string
    user?: string
    timestamp?: number
    from?: string
    subject?: string
    date?: Date | string
  }
}

export interface ChatSession {
  session_id: string
  title: string
  created_at: string
  updated_at: string
}

// Map of session ID to messages
type SessionMessages = Record<string, Message[]>

interface ChatState {
  // Current session
  currentSessionId: string
  
  // Messages per session
  sessionMessages: SessionMessages
  
  // UI state
  streamingMessage: string
  sources: Source[]
  isStreaming: boolean
  
  // Sessions list
  sessions: ChatSession[]
  
  // Computed messages for current session
  messages: Message[]
  
  // Actions
  setCurrentSessionId: (sessionId: string) => void
  loadSessionMessages: (sessionId: string) => Promise<void>
  addMessage: (message: Omit<Message, 'id' | 'timestamp'>) => void
  setStreamingMessage: (content: string) => void
  appendStreamingToken: (token: string) => void
  setSources: (sources: Source[]) => void
  setIsStreaming: (isStreaming: boolean) => void
  finishStreaming: () => void
  clearMessages: () => void
  setSessions: (sessions: ChatSession[]) => void
  createNewSession: () => void
  deleteSession: (sessionId: string) => void
}

// Generate unique session ID
function generateSessionId(): string {
  return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      // Initialize with a new session
      currentSessionId: generateSessionId(),
      sessionMessages: {},
      messages: [],
      streamingMessage: '',
      sources: [],
      isStreaming: false,
      sessions: [],
      
      setCurrentSessionId: (sessionId: string) => {
        const { sessionMessages } = get()
        const messages = sessionMessages[sessionId] || []
        set({ currentSessionId: sessionId, messages })
      },
      
      loadSessionMessages: async (sessionId: string) => {
        try {
          const response = await fetch(`http://localhost:8000/api/chat/sessions/${sessionId}/messages`)
          if (response.ok) {
            const data = await response.json()
            // CRITICAL: Convert timestamp strings to Date objects
            const messages = (data.messages || []).map((msg: any) => ({
              ...msg,
              timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date()
            }))
            set((state) => ({
              sessionMessages: { ...state.sessionMessages, [sessionId]: messages },
              messages: state.currentSessionId === sessionId ? messages : state.messages
            }))
          }
        } catch (error) {
          console.error('Failed to load session messages:', error)
        }
      },
      
      addMessage: (message) => {
        const { currentSessionId, sessionMessages } = get()
        const newMessage: Message = {
          ...message,
          id: Date.now().toString(),
          timestamp: new Date(),
        }
        const currentMessages = sessionMessages[currentSessionId] || []
        const updatedMessages = [...currentMessages, newMessage]
        
        set({
          messages: updatedMessages,
          sessionMessages: { ...sessionMessages, [currentSessionId]: updatedMessages }
        })
      },
      
      setStreamingMessage: (content) => {
        set({ streamingMessage: content })
      },
      
      appendStreamingToken: (token: string) => {
        set((state) => ({
          streamingMessage: state.streamingMessage + token,
        }))
      },
      
      setSources: (sources) => {
        set({ sources })
      },
      
      setIsStreaming: (isStreaming) => {
        set({ isStreaming })
      },
      
      finishStreaming: () => {
        const { streamingMessage, sources, currentSessionId, sessionMessages } = get()
        if (streamingMessage) {
          const newMessage: Message = {
            id: Date.now().toString(),
            role: 'assistant',
            content: streamingMessage,
            sources,
            timestamp: new Date(),
          }
          const currentMessages = sessionMessages[currentSessionId] || []
          const updatedMessages = [...currentMessages, newMessage]
          
          set({
            messages: updatedMessages,
            sessionMessages: { ...sessionMessages, [currentSessionId]: updatedMessages },
            streamingMessage: '',
            isStreaming: false,
          })
        }
      },
      
      clearMessages: () => {
        set({ messages: [], streamingMessage: '', sources: [], isStreaming: false })
      },
      
      setSessions: (sessions: ChatSession[]) => {
        set({ sessions })
      },
      
      createNewSession: () => {
        const newSessionId = generateSessionId()
        set({ 
          currentSessionId: newSessionId, 
          messages: [],
          streamingMessage: '',
          sources: [],
          isStreaming: false
        })
      },
      
      deleteSession: (sessionId: string) => {
        const { sessions, sessionMessages, currentSessionId } = get()
        const updatedSessions = sessions.filter(s => s.session_id !== sessionId)
        const updatedSessionMessages = { ...sessionMessages }
        delete updatedSessionMessages[sessionId]
        
        // If deleting current session, switch to another or create new
        let newCurrentSessionId = currentSessionId
        let newMessages: Message[] = []
        
        if (sessionId === currentSessionId) {
          if (updatedSessions.length > 0) {
            newCurrentSessionId = updatedSessions[0].session_id
            newMessages = updatedSessionMessages[newCurrentSessionId] || []
          } else {
            newCurrentSessionId = generateSessionId()
          }
        } else {
          newMessages = sessionMessages[currentSessionId] || []
        }
        
        set({
          sessions: updatedSessions,
          sessionMessages: updatedSessionMessages,
          currentSessionId: newCurrentSessionId,
          messages: newMessages
        })
        
        // Delete from backend
        fetch(`http://localhost:8000/api/chat/sessions/${sessionId}`, {
          method: 'DELETE'
        }).catch(console.error)
      },
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        currentSessionId: state.currentSessionId,
        sessionMessages: state.sessionMessages,
        sessions: state.sessions
      }),
    }
  )
)
