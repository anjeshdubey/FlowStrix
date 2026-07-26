import { useState, useEffect, useRef } from 'react'
import { FileText, Loader2, Sparkles, TriangleAlert, Upload, X } from 'lucide-react'
import { uploadFile } from '../../api'

interface PromptEntryProps {
  onGenerate: (prompt: string) => void
  loading: boolean
}

const PLACEHOLDERS = [
  'Handle customer refund requests with eligibility check and manager approval for high-value items...',
  'Troubleshoot WiFi issues by guiding the customer through restart, cable check, and reconnect steps...',
  'Route incoming support tickets based on urgency, department, and customer tier...',
  'Onboard new employees by collecting info, provisioning accounts, and scheduling orientation...',
]

const QUICK_STARTS = [
  { emoji: '🛒', label: 'Customer Support', prompt: 'Handle customer support requests including refunds, exchanges, and complaints. Check eligibility, get manager approval for high-value items, and send confirmation.' },
  { emoji: '🔧', label: 'Tech Troubleshoot', prompt: 'Guide users through technical troubleshooting with step-by-step diagnostics, escalating to L2 support if basic steps fail.' },
  { emoji: '📋', label: 'Approval Flow', prompt: 'Route approval requests based on amount and type. Small requests auto-approve, medium need manager sign-off, large need VP approval.' },
  { emoji: '🎯', label: 'Lead Qualification', prompt: 'Qualify inbound leads by scoring based on company size, budget, timeline, and fit. Route hot leads to sales, nurture warm leads.' },
]

const ACCEPTED_TYPES = '.txt,.md,.yaml,.yml,.json,.docx,.pdf,.rtf'

export default function PromptEntry({ onGenerate, loading }: PromptEntryProps) {
  const [prompt, setPrompt] = useState('')
  const [placeholderIdx, setPlaceholderIdx] = useState(0)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadedFile, setUploadedFile] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const interval = setInterval(() => {
      setPlaceholderIdx((prev) => (prev + 1) % PLACEHOLDERS.length)
    }, 4000)
    return () => clearInterval(interval)
  }, [])

  const handleSubmit = () => {
    if (prompt.trim()) onGenerate(prompt.trim())
  }

  const processFile = async (file: File) => {
    setUploading(true)
    setUploadError(null)
    setUploadedFile(null)

    try {
      const result = await uploadFile(file)
      setPrompt(result.content)
      setUploadedFile(result.filename)
      if (result.truncated) {
        setUploadError(`File was truncated to ${result.char_count.toLocaleString()} chars (max 50k)`)
      }
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) processFile(file)
    // Reset so same file can be re-selected
    e.target.value = ''
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) processFile(file)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
  }

  return (
    <div className="flex flex-col items-center">
      {/* Hero */}
      <h1 className="text-3xl font-bold text-primary mb-2 text-center">
        Describe your agent journey
      </h1>
      <p className="text-secondary mb-8 text-center">
        Tell us what your agent should do — or upload a file with the workflow description
      </p>

      {/* Quick starts */}
      <div className="flex flex-wrap gap-2 justify-center mb-6 max-w-2xl">
        {QUICK_STARTS.map((qs) => (
          <button
            key={qs.label}
            onClick={() => {
              setPrompt(qs.prompt)
              setUploadedFile(null)
            }}
            className="px-3 py-1.5 text-sm bg-surface-1 border border-border-subtle rounded-lg hover:border-accent hover:bg-accent/10 transition-all flex items-center gap-1.5"
          >
            <span>{qs.emoji}</span>
            <span className="text-secondary">{qs.label}</span>
          </button>
        ))}
      </div>

      {/* Prompt input with drop zone */}
      <div
        className={`w-full max-w-2xl bg-surface-1 border-2 rounded-xl p-4 transition-all ${
          dragOver
            ? 'border-accent bg-accent/10 ring-2 ring-accent/20'
            : 'border-border-subtle focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20'
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        <textarea
          value={prompt}
          onChange={(e) => {
            setPrompt(e.target.value)
            if (uploadedFile) setUploadedFile(null)
          }}
          placeholder={PLACEHOLDERS[placeholderIdx]}
          rows={4}
          className="w-full text-sm text-primary placeholder:text-muted bg-transparent resize-none border-none focus:ring-0 outline-none leading-relaxed"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && e.metaKey) handleSubmit()
          }}
        />

        {/* Upload status */}
        {uploadedFile && (
          <div className="flex items-center gap-2 mt-2 px-2 py-1.5 bg-accent/10 border border-accent/30 rounded-md">
            <FileText className="w-4 h-4 text-accent flex-shrink-0" />
            <span className="text-xs text-accent font-medium truncate">{uploadedFile}</span>
            <button
              onClick={() => {
                setUploadedFile(null)
                setPrompt('')
              }}
              className="ml-auto text-muted hover:text-secondary"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Upload error */}
        {uploadError && (
          <div className="mt-2 text-xs text-warning flex items-center gap-1">
            <TriangleAlert className="w-3.5 h-3.5" />
            {uploadError}
          </div>
        )}

        {/* Drag overlay message */}
        {dragOver && (
          <div className="mt-2 text-center py-3">
            <p className="text-sm text-accent font-medium">Drop file here to upload</p>
          </div>
        )}

        <div className="flex items-center justify-between mt-3 pt-3 border-t border-border-subtle">
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted">
              {prompt.length > 0 ? `${prompt.length} chars` : '⌘+Enter to generate'}
            </span>

            {/* Upload button */}
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || loading}
              className="flex items-center gap-1 text-xs text-muted hover:text-accent transition-colors disabled:opacity-40"
              title="Upload a file (.txt, .md, .docx, .pdf, .yaml)"
            >
              {uploading ? (
                <Loader2 className="animate-spin w-3.5 h-3.5" />
              ) : (
                <Upload className="w-3.5 h-3.5" />
              )}
              <span>{uploading ? 'Reading...' : 'Upload file'}</span>
            </button>

            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_TYPES}
              onChange={handleFileSelect}
              className="hidden"
            />
          </div>

          <button
            onClick={handleSubmit}
            disabled={!prompt.trim() || loading}
            className="px-5 py-2 rounded-lg bg-accent text-surface-0 font-medium text-sm hover:brightness-110 transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="animate-spin w-4 h-4" />
                Generating...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Generate Journey
              </>
            )}
          </button>
        </div>
      </div>

      {/* Supported formats hint */}
      <p className="mt-3 text-xs text-muted text-center">
        Drag & drop or upload: .txt, .md, .docx, .pdf, .yaml, .json
      </p>
    </div>
  )
}
