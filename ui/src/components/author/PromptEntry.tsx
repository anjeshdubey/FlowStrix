import { useState, useEffect, useRef } from 'react'
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
      <h1 className="text-3xl font-bold text-gray-900 mb-2 text-center">
        Describe your agent journey
      </h1>
      <p className="text-gray-500 mb-8 text-center">
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
            className="px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-lg hover:border-forge-400 hover:bg-forge-50 transition-all flex items-center gap-1.5"
          >
            <span>{qs.emoji}</span>
            <span className="text-gray-700">{qs.label}</span>
          </button>
        ))}
      </div>

      {/* Prompt input with drop zone */}
      <div
        className={`w-full max-w-2xl bg-white border-2 rounded-xl p-4 transition-all ${
          dragOver
            ? 'border-forge-500 bg-forge-50 ring-2 ring-forge-100'
            : 'border-gray-200 focus-within:border-forge-500 focus-within:ring-2 focus-within:ring-forge-100'
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
          className="w-full text-sm text-gray-800 placeholder-gray-400 bg-transparent resize-none border-none focus:ring-0 outline-none leading-relaxed"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && e.metaKey) handleSubmit()
          }}
        />

        {/* Upload status */}
        {uploadedFile && (
          <div className="flex items-center gap-2 mt-2 px-2 py-1.5 bg-forge-50 border border-forge-200 rounded-md">
            <svg className="w-4 h-4 text-forge-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span className="text-xs text-forge-700 font-medium truncate">{uploadedFile}</span>
            <button
              onClick={() => {
                setUploadedFile(null)
                setPrompt('')
              }}
              className="ml-auto text-gray-400 hover:text-gray-600"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Upload error */}
        {uploadError && (
          <div className="mt-2 text-xs text-amber-600 flex items-center gap-1">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.268 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
            {uploadError}
          </div>
        )}

        {/* Drag overlay message */}
        {dragOver && (
          <div className="mt-2 text-center py-3">
            <p className="text-sm text-forge-600 font-medium">Drop file here to upload</p>
          </div>
        )}

        <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100">
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400">
              {prompt.length > 0 ? `${prompt.length} chars` : '⌘+Enter to generate'}
            </span>

            {/* Upload button */}
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || loading}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-forge-600 transition-colors disabled:opacity-40"
              title="Upload a file (.txt, .md, .docx, .pdf, .yaml)"
            >
              {uploading ? (
                <svg className="animate-spin w-3.5 h-3.5" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : (
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
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
            className="px-5 py-2 rounded-lg bg-forge-600 text-white font-medium text-sm hover:bg-forge-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? (
              <>
                <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Generating...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Generate Journey
              </>
            )}
          </button>
        </div>
      </div>

      {/* Supported formats hint */}
      <p className="mt-3 text-xs text-gray-400 text-center">
        Drag & drop or upload: .txt, .md, .docx, .pdf, .yaml, .json
      </p>
    </div>
  )
}
