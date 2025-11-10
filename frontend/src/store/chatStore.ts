import { create } from 'zustand'

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

interface ChatState {
  messages: Message[]
  streamingMessage: string
  sources: Source[]
  isStreaming: boolean
  
  addMessage: (message: Omit<Message, 'id' | 'timestamp'>) => void
  setStreamingMessage: (content: string) => void
  appendStreamingToken: (token: string) => void
  setSources: (sources: Source[]) => void
  setIsStreaming: (isStreaming: boolean) => void
  finishStreaming: () => void
  clearMessages: () => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  streamingMessage: '',
  sources: [],
  isStreaming: false,
  
  addMessage: (message) => {
    const newMessage: Message = {
      ...message,
      id: Date.now().toString(),
      timestamp: new Date(),
    }
    set((state) => ({
      messages: [...state.messages, newMessage],
    }))
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
    const { streamingMessage, sources } = get()
    if (streamingMessage) {
      const newMessage: Message = {
        id: Date.now().toString(),
        role: 'assistant',
        content: streamingMessage,
        sources,
        timestamp: new Date(),
      }
      set((state) => ({
        messages: [...state.messages, newMessage],
        streamingMessage: '',
        isStreaming: false,
      }))
    }
  },
  
  clearMessages: () => {
    set({ messages: [], streamingMessage: '', sources: [], isStreaming: false })
  },
}))
