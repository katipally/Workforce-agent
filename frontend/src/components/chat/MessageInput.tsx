import { useState, KeyboardEvent, useRef, DragEvent } from 'react'
import { Send, Paperclip, X, FileText, AlertCircle } from 'lucide-react'

interface MessageInputProps {
  onSendMessage: (message: string, files?: File[]) => void
  disabled?: boolean
}

interface AttachedFile {
  file: File
  preview?: string
  type: 'image' | 'document'
}

// Validation constants
const MAX_MESSAGE_LENGTH = 5000
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB
const MAX_FILES = 5
const ALLOWED_FILE_TYPES = [
  'image/jpeg', 'image/png', 'image/gif', 'image/webp',
  'application/pdf', 'text/plain', 'text/csv',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // .docx
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', // .xlsx
  'application/json'
]

export default function MessageInput({
  onSendMessage,
  disabled = false,
}: MessageInputProps) {
  const [input, setInput] = useState('')
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  
  const handleSend = () => {
    // Validation
    if (!input.trim() && attachedFiles.length === 0) {
      setError('Please enter a message or attach a file')
      return
    }
    
    if (input.length > MAX_MESSAGE_LENGTH) {
      setError(`Message too long (max ${MAX_MESSAGE_LENGTH} characters)`)
      return
    }
    
    if (disabled) return
    
    setError(null)
    const files = attachedFiles.map(af => af.file)
    onSendMessage(input.trim(), files)
    setInput('')
    setAttachedFiles([])
    
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }
  
  const handleFileSelect = (files: FileList | null) => {
    if (!files) return
    
    setError(null)
    
    // Validate number of files
    if (attachedFiles.length + files.length > MAX_FILES) {
      setError(`Maximum ${MAX_FILES} files allowed`)
      return
    }
    
    const newFiles: AttachedFile[] = []
    const validFiles: File[] = []
    
    Array.from(files).forEach(file => {
      // Validate file size
      if (file.size > MAX_FILE_SIZE) {
        setError(`${file.name} is too large (max 10MB)`)
        return
      }
      
      // Validate file type
      if (!ALLOWED_FILE_TYPES.includes(file.type)) {
        setError(`${file.name} file type not allowed. Allowed: images, PDF, text, Word, Excel, JSON`)
        return
      }
      
      validFiles.push(file)
      const isImage = file.type.startsWith('image/')
      
      if (isImage) {
        // Create preview for images
        const reader = new FileReader()
        reader.onload = (e) => {
          newFiles.push({
            file,
            preview: e.target?.result as string,
            type: 'image'
          })
          if (newFiles.length === validFiles.length) {
            setAttachedFiles(prev => [...prev, ...newFiles])
          }
        }
        reader.readAsDataURL(file)
      } else {
        newFiles.push({
          file,
          type: 'document'
        })
        if (newFiles.length === validFiles.length) {
          setAttachedFiles(prev => [...prev, ...newFiles])
        }
      }
    })
  }
  
  const handleRemoveFile = (index: number) => {
    setAttachedFiles(prev => prev.filter((_, i) => i !== index))
  }
  
  const handleDragOver = (e: DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }
  
  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }
  
  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    handleFileSelect(e.dataTransfer.files)
  }
  
  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }
  
  const handleInputChange = (value: string) => {
    setInput(value)
    setError(null)
    
    // Auto-resize textarea
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px'
    }
  }
  
  const remainingChars = MAX_MESSAGE_LENGTH - input.length
  const isNearLimit = remainingChars < 500
  
  return (
    <div className="space-y-2">
      {/* File attachments preview */}
      {attachedFiles.length > 0 && (
        <div className="flex flex-wrap gap-2 px-2">
          {attachedFiles.map((attached, index) => (
            <div
              key={index}
              className="relative group rounded-lg border border-gray-300 bg-white overflow-hidden"
            >
              {attached.type === 'image' && attached.preview ? (
                <div className="relative">
                  <img
                    src={attached.preview}
                    alt={attached.file.name}
                    className="h-20 w-20 object-cover"
                  />
                  <button
                    onClick={() => handleRemoveFile(index)}
                    className="absolute top-1 right-1 rounded-full bg-black/50 p-1 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Remove image"
                    aria-label="Remove image"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2 p-2">
                  <FileText className="h-8 w-8 text-gray-400" />
                  <div className="max-w-[100px]">
                    <div className="truncate text-xs font-medium">{attached.file.name}</div>
                    <div className="text-xs text-gray-500">
                      {(attached.file.size / 1024).toFixed(1)} KB
                    </div>
                  </div>
                  <button
                    onClick={() => handleRemoveFile(index)}
                    className="ml-2 text-gray-400 hover:text-red-500"
                    title="Remove file"
                    aria-label="Remove file"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      
      {/* Error message */}
      {error && (
        <div className="flex items-center gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}
      
      {/* Input area with drag and drop */}
      <div
        className={`flex gap-4 relative ${isDragging ? 'ring-2 ring-blue-500 rounded-lg' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {isDragging && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-blue-50 border-2 border-dashed border-blue-400 rounded-lg">
            <p className="text-blue-600 font-medium">Drop files here</p>
          </div>
        )}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:bg-gray-100 disabled:cursor-not-allowed transition-colors"
          title="Attach file"
          aria-label="Attach file"
        >
          <Paperclip className="h-5 w-5" />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={(e) => handleFileSelect(e.target.files)}
          className="hidden"
          accept="image/*,.pdf,.doc,.docx,.txt,.csv,.json"
          title="File upload"
          aria-label="File upload input"
        />
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask me anything about your Slack, Gmail, or Notion data..."
            disabled={disabled}
            rows={1}
            className="w-full resize-none rounded-lg border border-gray-300 px-4 py-3 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 disabled:bg-gray-100 disabled:cursor-not-allowed min-h-[48px] max-h-[200px]"
          />
          {/* Character counter */}
          {input.length > 0 && (
            <div className={`absolute bottom-2 right-2 text-xs ${
              isNearLimit ? 'text-orange-500 font-medium' : 'text-gray-400'
            }`}>
              {remainingChars} / {MAX_MESSAGE_LENGTH}
            </div>
          )}
        </div>
        <button
          onClick={handleSend}
          disabled={(!input.trim() && attachedFiles.length === 0) || disabled || input.length > MAX_MESSAGE_LENGTH}
          className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          aria-label="Send message"
          title="Send message (Enter)"
        >
          <Send className="h-5 w-5" />
        </button>
      </div>
    </div>
  )
}
