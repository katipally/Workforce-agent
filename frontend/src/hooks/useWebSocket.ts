import { useEffect, useRef, useState, useCallback } from 'react'
import { useChatStore } from '../store/chatStore'
import { API_BASE_URL } from '../lib/api'

interface WebSocketHook {
  sendMessage: (query: string) => void
  isConnected: boolean
  connectionStatus: 'connecting' | 'connected' | 'disconnected' | 'error'
}

const wsBase = API_BASE_URL.startsWith('https')
  ? API_BASE_URL.replace(/^https/, 'wss')
  : API_BASE_URL.replace(/^http/, 'ws')

const WS_URL = `${wsBase}/api/chat/ws`
const RECONNECT_INTERVAL = 3000 // 3 seconds
const MAX_RECONNECT_ATTEMPTS = 5

export function useWebSocket(): WebSocketHook {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const [isConnected, setIsConnected] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected' | 'error'>('connecting')
  
  const {
    setStreamingMessage,
    appendStreamingToken,
    setSources,
    setIsStreaming,
    finishStreaming,
    addReasoningStep,
    clearReasoningSteps,
  } = useChatStore()
  
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return // Already connected
    }
    
    setConnectionStatus('connecting')
    console.log('Connecting to WebSocket...')
    
    const ws = new WebSocket(WS_URL)
    
    ws.onopen = () => {
      console.log('✓ WebSocket connected')
      setIsConnected(true)
      setConnectionStatus('connected')
      reconnectAttemptsRef.current = 0 // Reset reconnect counter
    }
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        
        if (data.type === 'token') {
          // Append streaming token
          appendStreamingToken(data.content)
        } else if (data.type === 'sources') {
          // Receive sources
          setSources(data.content)
        } else if (data.type === 'done') {
          // Streaming complete
          finishStreaming()
        } else if (data.type === 'status') {
          // Status message from backend (safe, high-level reasoning/steps)
          // Treat step messages and final reasoning summary as "thinking" entries.
          console.log('Status:', data.content)
          if (typeof data.content === 'string') {
            if (data.content.startsWith('Step ')) {
              addReasoningStep(data.content)
            } else if (data.content.startsWith('Reasoning Summary')) {
              addReasoningStep(data.content)
            }
          }
        } else if (data.type === 'error') {
          console.error('Server error:', data.content)
          setIsStreaming(false)
          // Show error to user
          finishStreaming()
          setStreamingMessage(`Error: ${data.content}`)
        }
      } catch (error) {
        console.error('Error parsing WebSocket message:', error)
      }
    }
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      setIsConnected(false)
      setConnectionStatus('error')
    }
    
    ws.onclose = (event) => {
      console.log('WebSocket disconnected', event.code, event.reason)
      setIsConnected(false)
      setConnectionStatus('disconnected')
      wsRef.current = null
      
      // Attempt reconnection if not exceeded max attempts
      if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttemptsRef.current++
        console.log(`Reconnecting... (attempt ${reconnectAttemptsRef.current}/${MAX_RECONNECT_ATTEMPTS})`)
        
        reconnectTimeoutRef.current = setTimeout(() => {
          connect()
        }, RECONNECT_INTERVAL)
      } else {
        console.error('Max reconnection attempts reached')
        setConnectionStatus('error')
      }
    }
    
    wsRef.current = ws
  }, [appendStreamingToken, setSources, setIsStreaming, finishStreaming, setStreamingMessage, addReasoningStep])
  
  useEffect(() => {
    connect()
    
    // Cleanup on unmount
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [connect])
  
  const sendMessage = useCallback((query: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      // Reset streaming state
      setStreamingMessage('')
      setSources([])
      setIsStreaming(true)
      clearReasoningSteps()
      
      // Get current session ID from store
      const { currentSessionId } = useChatStore.getState()
      
      // Send query with session ID
      try {
        wsRef.current.send(JSON.stringify({ 
          query,
          session_id: currentSessionId
        }))
        console.log('Query sent:', query.substring(0, 50) + '... (session:', currentSessionId + ')')
      } catch (error) {
        console.error('Error sending message:', error)
        setIsStreaming(false)
        setStreamingMessage('Error: Failed to send message')
      }
    } else {
      console.error('WebSocket is not connected. Status:', connectionStatus)
      setStreamingMessage('Error: Connection lost. Reconnecting...')
      
      // Try to reconnect
      if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
        connect()
      }
    }
  }, [setStreamingMessage, setSources, setIsStreaming, clearReasoningSteps, connectionStatus, connect])
  
  return {
    sendMessage,
    isConnected,
    connectionStatus,
  }
}
