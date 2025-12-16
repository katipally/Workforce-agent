import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { API_BASE_URL } from '../lib/api'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  reasoningSteps?: string[]
  timestamp: Date
}

export interface Source {
  type: 'slack' | 'gmail' | 'notion'
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
    title?: string
    page_id?: string
  }
}

export interface SourcePreferences {
  slack: boolean
  gmail: boolean
  notion: boolean
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
  currentReasoningSteps: string[]
  
  // Sessions list
  sessions: ChatSession[]
  
  // Per-session source preferences
  sessionSourcePrefs: Record<string, SourcePreferences>
  
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
  addReasoningStep: (step: string) => void
  clearReasoningSteps: () => void
  clearMessages: () => void
  setSessions: (sessions: ChatSession[]) => void
  createNewSession: () => void
  deleteSession: (sessionId: string) => void
  resetStore: () => void
  setSourcePreferencesForSession: (sessionId: string, prefs: SourcePreferences) => void
  toggleSourcePreference: (source: keyof SourcePreferences) => void
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
      currentReasoningSteps: [],
      sessions: [],
      sessionSourcePrefs: {},
      
      setCurrentSessionId: (sessionId: string) => {
        const { sessionMessages } = get()
        const messages = sessionMessages[sessionId] || []
        set({ currentSessionId: sessionId, messages })
      },
      
      loadSessionMessages: async (sessionId: string) => {
        try {
          const response = await fetch(`${API_BASE_URL}/api/chat/sessions/${sessionId}`, {
            credentials: 'include',
          })
          if (response.ok) {
            const data = await response.json()

            const messages: Message[] = (data.messages || []).map((msg: any, index: number) => ({
              id: `${data.session_id || sessionId}_${index}`,
              role: msg.role,
              content: msg.content,
              sources: msg.sources || [],
              reasoningSteps: [],
              timestamp: msg.created_at ? new Date(msg.created_at) : new Date(),
            }))

            set((state) => ({
              sessionMessages: { ...state.sessionMessages, [sessionId]: messages },
              // When we explicitly load a session, we always want to show its messages
              messages,
            }))
          } else {
            console.error('Failed to load session from backend:', response.status, response.statusText)
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
        const { streamingMessage, sources, currentSessionId, sessionMessages, currentReasoningSteps } = get()
        if (streamingMessage) {
          const newMessage: Message = {
            id: Date.now().toString(),
            role: 'assistant',
            content: streamingMessage,
            sources,
            reasoningSteps: currentReasoningSteps,
            timestamp: new Date(),
          }
          const currentMessages = sessionMessages[currentSessionId] || []
          const updatedMessages = [...currentMessages, newMessage]
          
          set({
            messages: updatedMessages,
            sessionMessages: { ...sessionMessages, [currentSessionId]: updatedMessages },
            streamingMessage: '',
            isStreaming: false,
            currentReasoningSteps: [],
          })
        }
      },

      addReasoningStep: (step) => {
        set((state) => ({
          currentReasoningSteps: [...state.currentReasoningSteps, step],
        }))
      },

      clearReasoningSteps: () => {
        set({ currentReasoningSteps: [] })
      },
      
      clearMessages: () => {
        set({ messages: [], streamingMessage: '', sources: [], isStreaming: false, currentReasoningSteps: [] })
      },
      
      setSessions: (sessions: ChatSession[]) => {
        set({ sessions })
      },
      
      createNewSession: () => {
        const newSessionId = generateSessionId()
        const nowIso = new Date().toISOString()
        set((state) => ({ 
          currentSessionId: newSessionId, 
          messages: [],
          streamingMessage: '',
          sources: [],
          isStreaming: false,
          currentReasoningSteps: [],
          // Show the new conversation immediately in the sidebar
          sessions: [
            {
              session_id: newSessionId,
              title: 'New Chat',
              created_at: nowIso,
              updated_at: nowIso,
            },
            ...state.sessions,
          ],
          // Initialize empty messages bucket for this session
          sessionMessages: {
            ...state.sessionMessages,
            [newSessionId]: [],
          },
        }))
      },
      
      deleteSession: (sessionId: string) => {
        const { sessions, sessionMessages, currentSessionId, sessionSourcePrefs } = get()
        const updatedSessions = sessions.filter(s => s.session_id !== sessionId)
        const updatedSessionMessages = { ...sessionMessages }
        delete updatedSessionMessages[sessionId]
        const updatedSourcePrefs = { ...sessionSourcePrefs }
        delete updatedSourcePrefs[sessionId]
        
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
          messages: newMessages,
          sessionSourcePrefs: updatedSourcePrefs,
        })
        
        // Delete from backend
        fetch(`${API_BASE_URL}/api/chat/sessions/${sessionId}`, {
          method: 'DELETE',
          credentials: 'include',
        }).catch(console.error)
      },

      resetStore: () => {
        const newSessionId = generateSessionId()
        const nowIso = new Date().toISOString()
        set({
          currentSessionId: newSessionId,
          sessionMessages: { [newSessionId]: [] },
          messages: [],
          streamingMessage: '',
          sources: [],
          isStreaming: false,
          currentReasoningSteps: [],
          sessions: [
            {
              session_id: newSessionId,
              title: 'New Chat',
              created_at: nowIso,
              updated_at: nowIso,
            },
          ],
          sessionSourcePrefs: {},
        })
      },
      setSourcePreferencesForSession: (sessionId, prefs) => {
        set((state) => ({
          sessionSourcePrefs: {
            ...state.sessionSourcePrefs,
            [sessionId]: prefs,
          },
        }))
      },
      toggleSourcePreference: (source) => {
        const { currentSessionId, sessionSourcePrefs } = get()
        const currentPrefs: SourcePreferences = sessionSourcePrefs[currentSessionId] || {
          slack: true,
          gmail: true,
          notion: true,
        }
        const updated: SourcePreferences = {
          ...currentPrefs,
          [source]: !currentPrefs[source],
        }
        set({
          sessionSourcePrefs: {
            ...sessionSourcePrefs,
            [currentSessionId]: updated,
          },
        })
      },
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        // Persist only lightweight metadata; messages themselves are loaded
        // on demand from the backend to keep startup fast even with many
        // long conversations.
        sessions: state.sessions,
        sessionSourcePrefs: state.sessionSourcePrefs,
      }),
    }
  )
)
