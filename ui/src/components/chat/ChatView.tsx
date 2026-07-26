import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  ClipboardList,
  Loader2,
  MessageCircle,
  Send,
  Settings,
  TriangleAlert,
  X,
} from 'lucide-react'
import { listSpecs, runJourney, resumeHITL, resumeHandoff, SavedSpec, getSpec } from '../../api'
import { HandoffInfo, JourneySummary, RunResponse, SpecSummary, StepTrace } from '../../types'

type EngineType = 'legacy' | 'langgraph'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  traces?: StepTrace[]
  hitl_info?: RunResponse['hitl_info']
  handoff_info?: HandoffInfo
  timestamp: number
}

export default function ChatView() {
  const [specs, setSpecs] = useState<SavedSpec[]>([])
  const [loadingSpecs, setLoadingSpecs] = useState(true)
  const [selectedSpecPath, setSelectedSpecPath] = useState('')
  const [spec, setSpec] = useState<SpecSummary | null>(null)
  const [selectedJourney, setSelectedJourney] = useState<JourneySummary | null>(null)
  const [engine, setEngine] = useState<EngineType>('langgraph')
  const [threadId, setThreadId] = useState<string | undefined>(undefined)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [lastExecutionId, setLastExecutionId] = useState<string | null>(null)
  const [hitlPending, setHitlPending] = useState(false)
  const [handoffPending, setHandoffPending] = useState(false)
  // Track how many assistant messages we've already rendered (to extract only new ones)
  const prevAssistantCountRef = useRef(0)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Load specs on mount
  useEffect(() => {
    listSpecs()
      .then(setSpecs)
      .catch(() => setSpecs([]))
      .finally(() => setLoadingSpecs(false))
  }, [])

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Load spec details when selected
  const handleSpecSelect = useCallback(async (path: string) => {
    setSelectedSpecPath(path)
    setSelectedJourney(null)
    setError(null)
    try {
      const loaded = await getSpec(path)
      setSpec(loaded)
      if (loaded.journeys.length > 0) {
        setSelectedJourney(loaded.journeys[0])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load spec')
      setSpec(null)
    }
  }, [])

  // Send message
  const handleSend = useCallback(async () => {
    if (!input.trim() || !selectedJourney || !selectedSpecPath) return

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: input.trim(),
      timestamp: Date.now(),
    }

    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setSending(true)
    setError(null)

    try {
      const response = await runJourney({
        spec_path: selectedSpecPath,
        journey: selectedJourney.name,
        message: userMessage.content,
        engine,
        thread_id: threadId,
      })

      // Persist thread_id for multi-turn
      if (response.thread_id) {
        setThreadId(response.thread_id)
      }

      // Track execution_id for HITL/handoff resume
      setLastExecutionId(response.execution_id)
      if (response.handoff_info) {
        setHandoffPending(true)
        setHitlPending(false)
      } else if (response.hitl_info) {
        setHitlPending(true)
        setHandoffPending(false)
      }

      // Extract only NEW assistant messages from this turn.
      // The response contains the full conversation history — we only want
      // messages we haven't already displayed.
      const allAssistantMsgs = response.messages?.filter((m) => m.role === 'assistant') || []
      const newAssistantMsgs = allAssistantMsgs.slice(prevAssistantCountRef.current)
      prevAssistantCountRef.current = allAssistantMsgs.length

      const assistantContent =
        newAssistantMsgs.map((m) => m.content).join('\n') ||
        `Journey "${response.journey_name}" completed.`

      // Only show new traces (from this turn's steps)
      const prevStepCount = messages.filter(m => m.role === 'assistant')
        .reduce((acc, m) => acc + (m.traces?.length || 0), 0)
      const newTraces = (response.traces || []).slice(prevStepCount)

      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: assistantContent,
        traces: newTraces.length > 0 ? newTraces : response.traces,
        hitl_info: response.hitl_info,
        handoff_info: response.handoff_info,
        timestamp: Date.now(),
      }

      setMessages((prev) => [...prev, assistantMessage])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message')
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }, [input, selectedJourney, selectedSpecPath, engine, threadId])

  // HITL approve/reject
  const handleHITLDecision = useCallback(async (approved: boolean) => {
    if (!lastExecutionId) return
    setSending(true)
    setError(null)

    try {
      const response = await resumeHITL(lastExecutionId, approved, approved ? 'Approved' : 'Rejected')
      setHitlPending(false)

      // Extract new assistant messages from resume response
      const allAssistantMsgs = response.messages?.filter((m) => m.role === 'assistant') || []
      const newAssistantMsgs = allAssistantMsgs.slice(prevAssistantCountRef.current)
      prevAssistantCountRef.current = allAssistantMsgs.length

      const content = newAssistantMsgs.map((m) => m.content).join('\n') ||
        (approved ? 'Escalation approved — handing off.' : 'Escalation rejected.')

      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content,
        traces: response.traces,
        timestamp: Date.now(),
      }

      setMessages((prev) => [...prev, assistantMessage])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'HITL resume failed')
    } finally {
      setSending(false)
    }
  }, [lastExecutionId])

  // Handoff form submit
  const handleHandoffSubmit = useCallback(async (formData: Record<string, unknown>) => {
    if (!lastExecutionId) return
    setSending(true)
    setError(null)

    try {
      const response = await resumeHandoff(lastExecutionId, formData)
      setHandoffPending(false)

      // Persist thread_id
      if (response.thread_id) {
        setThreadId(response.thread_id)
      }
      setLastExecutionId(response.execution_id)

      // Check if new handoff or HITL after resume
      if (response.handoff_info) {
        setHandoffPending(true)
      } else if (response.hitl_info) {
        setHitlPending(true)
      }

      // Extract new assistant messages
      const allAssistantMsgs = response.messages?.filter((m) => m.role === 'assistant') || []
      const newAssistantMsgs = allAssistantMsgs.slice(prevAssistantCountRef.current)
      prevAssistantCountRef.current = allAssistantMsgs.length

      const content = newAssistantMsgs.map((m) => m.content).join('\n') ||
        'Form submitted. Continuing...'

      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content,
        traces: response.traces,
        hitl_info: response.hitl_info,
        handoff_info: response.handoff_info,
        timestamp: Date.now(),
      }

      setMessages((prev) => [...prev, assistantMessage])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Handoff submit failed')
    } finally {
      setSending(false)
    }
  }, [lastExecutionId])

  // New conversation
  const handleNewConversation = useCallback(() => {
    setMessages([])
    setThreadId(undefined)
    setError(null)
    setHitlPending(false)
    setHandoffPending(false)
    setLastExecutionId(null)
    prevAssistantCountRef.current = 0
  }, [])

  // Handle Enter key (Shift+Enter for newline)
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-12rem)] max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle bg-surface-1 rounded-t-lg">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-primary">Chat</h2>
          {/* Engine Badge */}
          <span
            className={`text-xs font-medium px-2 py-0.5 rounded-full ${
              engine === 'langgraph'
                ? 'bg-success/10 text-success'
                : 'bg-warning/10 text-warning'
            }`}
          >
            {engine === 'langgraph' ? 'LangGraph' : 'Legacy'}
          </span>
          {threadId && (
            <span className="text-xs text-muted font-mono">
              thread: {threadId.slice(0, 8)}...
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleNewConversation}
            className="px-3 py-1.5 text-xs font-medium text-secondary bg-surface-2 rounded-md hover:bg-border-subtle transition-colors"
          >
            New Conversation
          </button>
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-1.5 text-secondary hover:text-primary rounded-md hover:bg-surface-2 transition-colors"
            title="Settings"
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Settings Panel (collapsible) */}
      {showSettings && (
        <div className="px-4 py-3 bg-surface-1 border-b border-border-subtle space-y-3 animate-slide-in">
          {/* Engine Toggle */}
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium text-secondary">Engine:</label>
            <div className="inline-flex bg-surface-2 p-0.5 rounded-md">
              <button
                onClick={() => setEngine('langgraph')}
                className={`px-3 py-1 text-xs font-medium rounded transition-all ${
                  engine === 'langgraph'
                    ? 'bg-surface-0 text-primary shadow-1'
                    : 'text-secondary hover:text-primary'
                }`}
              >
                LangGraph
              </button>
              <button
                onClick={() => setEngine('legacy')}
                className={`px-3 py-1 text-xs font-medium rounded transition-all ${
                  engine === 'legacy'
                    ? 'bg-surface-0 text-primary shadow-1'
                    : 'text-secondary hover:text-primary'
                }`}
              >
                Legacy
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Spec & Journey Selectors */}
      <div className="px-4 py-3 bg-surface-1 border-b border-border-subtle">
        <div className="flex gap-3">
          {/* Spec Selector */}
          <div className="flex-1">
            <select
              value={selectedSpecPath}
              onChange={(e) => handleSpecSelect(e.target.value)}
              disabled={loadingSpecs}
              className="w-full px-3 py-2 text-sm border border-border rounded-md bg-surface-2 text-primary focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent"
            >
              <option value="">
                {loadingSpecs ? 'Loading specs...' : 'Select a spec...'}
              </option>
              {specs.map((s) => (
                <option key={s.path} value={s.path}>
                  {s.agent} ({s.journey_count} journeys)
                </option>
              ))}
            </select>
          </div>

          {/* Journey Selector */}
          <div className="flex-1">
            <select
              value={selectedJourney?.name || ''}
              onChange={(e) => {
                const j = spec?.journeys.find((j) => j.name === e.target.value) || null
                setSelectedJourney(j)
              }}
              disabled={!spec}
              className="w-full px-3 py-2 text-sm border border-border rounded-md bg-surface-2 text-primary focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent disabled:opacity-50"
            >
              <option value="">
                {spec ? 'Select a journey...' : 'Load a spec first'}
              </option>
              {spec?.journeys.map((j) => (
                <option key={j.name} value={j.name}>
                  {j.name} ({j.step_count} steps)
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 bg-surface-0">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-muted">
            <div className="text-center">
              <MessageCircle className="w-12 h-12 mx-auto mb-3 text-muted" strokeWidth={1.5} />
              <p className="text-sm">Select a spec and journey, then start chatting.</p>
              <p className="text-xs mt-1 text-muted">Multi-turn conversations persist via thread_id</p>
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <ChatBubble
            key={msg.id}
            message={msg}
            hitlPending={hitlPending && idx === messages.length - 1}
            handoffPending={handoffPending && idx === messages.length - 1}
            sending={sending}
            onHITLDecision={handleHITLDecision}
            onHandoffSubmit={handleHandoffSubmit}
          />
        ))}

        {sending && (
          <div className="flex justify-start">
            <div className="bg-surface-1 rounded-lg px-4 py-3 max-w-[75%]">
              <div className="flex items-center gap-2 text-sm text-muted">
                <Loader2 className="animate-spin w-3.5 h-3.5" />
                Processing...
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Error */}
      {error && (
        <div className="mx-4 mb-2 p-3 bg-danger/10 border border-danger/30 rounded-md text-sm text-danger">
          {error}
        </div>
      )}

      {/* Input Area */}
      <div className="px-4 py-3 border-t border-border-subtle bg-surface-1 rounded-b-lg">
        <div className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              selectedJourney
                ? `Message ${spec?.persona_name || 'agent'}... (Enter to send, Shift+Enter for newline)`
                : 'Select a spec and journey to begin...'
            }
            disabled={!selectedJourney || sending}
            rows={1}
            className="flex-1 px-4 py-2.5 bg-surface-2 border border-border rounded-lg text-sm text-primary placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent resize-none disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ minHeight: '42px', maxHeight: '120px' }}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement
              target.style.height = 'auto'
              target.style.height = Math.min(target.scrollHeight, 120) + 'px'
            }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || !selectedJourney || sending}
            className="px-4 py-2.5 bg-accent text-surface-0 rounded-lg font-medium hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            <Send className="w-4 h-4" />
            Send
          </button>
        </div>
      </div>
    </div>
  )
}

// --- Chat Bubble Component ---

function ChatBubble({ message, hitlPending, handoffPending, sending, onHITLDecision, onHandoffSubmit }: {
  message: ChatMessage
  hitlPending?: boolean
  handoffPending?: boolean
  sending?: boolean
  onHITLDecision?: (approved: boolean) => void
  onHandoffSubmit?: (formData: Record<string, unknown>) => void
}) {
  const [tracesExpanded, setTracesExpanded] = useState(false)
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] space-y-1`}>
        {/* Bubble */}
        <div
          className={`rounded-lg px-4 py-2.5 text-sm whitespace-pre-wrap ${
            isUser
              ? 'bg-accent text-surface-0'
              : 'bg-surface-1 text-primary'
          }`}
        >
          {message.content}
        </div>

        {/* Handoff Form inline */}
        {message.handoff_info && handoffPending && onHandoffSubmit && (
          <InlineChatHandoffForm
            handoffInfo={message.handoff_info}
            onSubmit={onHandoffSubmit}
            loading={sending || false}
          />
        )}

        {/* HITL Approval inline */}
        {message.hitl_info && !message.handoff_info && (
          <div className="p-3 bg-warning/10 border border-warning/30 rounded-lg text-sm">
            <div className="flex items-center gap-2 mb-1">
              <TriangleAlert className="w-4 h-4 text-warning" />
              <span className="font-medium text-warning">Approval Required</span>
            </div>
            <p className="text-warning/80 text-xs mb-2">
              Step "{message.hitl_info.step_name}" needs {message.hitl_info.escalate_to} approval.
            </p>
            {hitlPending && onHITLDecision && (
              <div className="flex gap-2">
                <button
                  onClick={() => onHITLDecision(true)}
                  disabled={sending}
                  className="px-3 py-1.5 bg-success text-surface-0 text-xs font-medium rounded-md hover:brightness-110 disabled:opacity-50 transition-all"
                >
                  Approve
                </button>
                <button
                  onClick={() => onHITLDecision(false)}
                  disabled={sending}
                  className="px-3 py-1.5 bg-danger text-surface-0 text-xs font-medium rounded-md hover:brightness-110 disabled:opacity-50 transition-all"
                >
                  Reject
                </button>
              </div>
            )}
          </div>
        )}

        {/* Step Traces (collapsible) */}
        {message.traces && message.traces.length > 0 && (
          <div className="mt-1">
            <button
              onClick={() => setTracesExpanded(!tracesExpanded)}
              className="flex items-center gap-1 text-xs text-muted hover:text-secondary transition-colors"
            >
              <ChevronRight className={`w-3 h-3 transition-transform ${tracesExpanded ? 'rotate-90' : ''}`} />
              {message.traces.length} step{message.traces.length !== 1 ? 's' : ''} executed
            </button>

            {tracesExpanded && (
              <div className="mt-1.5 pl-3 border-l-2 border-border-subtle space-y-1.5">
                {message.traces.map((trace, i) => (
                  <div key={i} className="text-xs">
                    <div className="flex items-center gap-2">
                      <StepStatusIcon status={trace.status} />
                      <span className="font-medium text-secondary">{trace.step_name}</span>
                      <span className="text-muted">{trace.step_type}</span>
                      {trace.duration_ms !== undefined && (
                        <span className="text-muted">{trace.duration_ms}ms</span>
                      )}
                    </div>
                    {trace.output_preview && (
                      <p className="mt-0.5 text-muted pl-5 truncate">{trace.output_preview}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Timestamp */}
        <div className={`text-[10px] text-muted ${isUser ? 'text-right' : 'text-left'}`}>
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  )
}

// --- Inline Handoff Form for Chat ---

function InlineChatHandoffForm({ handoffInfo, onSubmit, loading }: {
  handoffInfo: HandoffInfo
  onSubmit: (formData: Record<string, unknown>) => void
  loading: boolean
}) {
  const [formData, setFormData] = useState<Record<string, unknown>>(() => {
    const initial: Record<string, unknown> = {}
    for (const field of handoffInfo.fields) {
      if (field.prefilled_value !== null && field.prefilled_value !== undefined) {
        initial[field.id] = field.prefilled_value
      } else if (field.field_type === 'checkbox') {
        initial[field.id] = false
      } else if (field.field_type === 'multiselect') {
        initial[field.id] = []
      } else {
        initial[field.id] = ''
      }
    }
    return initial
  })

  const handleChange = (fieldId: string, value: unknown) => {
    setFormData((prev) => ({ ...prev, [fieldId]: value }))
  }

  const handleSubmit = () => {
    onSubmit(formData)
  }

  return (
    <div className="mt-2 p-4 bg-accent/10 border border-accent/30 rounded-lg space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-accent">
        <ClipboardList className="w-4 h-4" />
        Please complete the following:
      </div>

      {handoffInfo.fields.map((field) => (
        <div key={field.id} className="space-y-1">
          {field.field_type !== 'checkbox' && (
            <label className="block text-xs font-medium text-secondary">
              {field.label}
              {field.required && <span className="text-danger ml-0.5">*</span>}
            </label>
          )}

          {field.field_type === 'textarea' && (
            <textarea
              value={(formData[field.id] as string) || ''}
              onChange={(e) => handleChange(field.id, e.target.value)}
              placeholder={field.placeholder || ''}
              rows={2}
              className="w-full px-3 py-1.5 bg-surface-2 border border-border rounded-md text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent resize-none"
            />
          )}

          {field.field_type === 'text' && (
            <input
              type="text"
              value={(formData[field.id] as string) || ''}
              onChange={(e) => handleChange(field.id, e.target.value)}
              placeholder={field.placeholder || ''}
              className="w-full px-3 py-1.5 bg-surface-2 border border-border rounded-md text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent"
            />
          )}

          {field.field_type === 'select' && (
            <select
              value={(formData[field.id] as string) || ''}
              onChange={(e) => handleChange(field.id, e.target.value)}
              className="w-full px-3 py-1.5 bg-surface-2 border border-border rounded-md text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent"
            >
              <option value="">{field.placeholder || 'Select...'}</option>
              {field.options.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          )}

          {field.field_type === 'multiselect' && (
            <div className="flex flex-wrap gap-1.5">
              {field.options.map((opt) => {
                const selected = Array.isArray(formData[field.id]) &&
                  (formData[field.id] as string[]).includes(opt)
                return (
                  <label
                    key={opt}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border cursor-pointer text-xs transition-colors ${
                      selected
                        ? 'border-accent bg-accent/10 text-accent'
                        : 'border-border-subtle bg-surface-2 hover:border-border text-secondary'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={(e) => {
                        const current = (formData[field.id] as string[]) || []
                        if (e.target.checked) {
                          handleChange(field.id, [...current, opt])
                        } else {
                          handleChange(field.id, current.filter((v) => v !== opt))
                        }
                      }}
                      className="sr-only"
                    />
                    {opt}
                  </label>
                )
              })}
            </div>
          )}

          {field.field_type === 'checkbox' && (
            <label className="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={Boolean(formData[field.id])}
                onChange={(e) => handleChange(field.id, e.target.checked)}
                className="mt-0.5 rounded border-border bg-surface-2 text-accent focus:ring-accent"
              />
              <span className="text-xs text-secondary">{field.label}</span>
            </label>
          )}
        </div>
      ))}

      <button
        onClick={handleSubmit}
        disabled={loading}
        className="w-full py-2 bg-accent text-surface-0 text-sm font-medium rounded-md hover:brightness-110 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
      >
        {loading ? (
          <>
            <Loader2 className="animate-spin w-3.5 h-3.5" />
            Submitting...
          </>
        ) : (
          'Submit'
        )}
      </button>
    </div>
  )
}

// --- Step Status Icon ---

function StepStatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'completed':
      return <Check className="w-3 h-3 text-success" />
    case 'failed':
      return <X className="w-3 h-3 text-danger" />
    case 'waiting_hitl':
      return <CheckCircle2 className="w-3 h-3 text-warning" />
    default:
      return <Circle className="w-3 h-3 text-muted" />
  }
}
