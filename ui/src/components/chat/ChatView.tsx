import { useCallback, useEffect, useRef, useState } from 'react'
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
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-border-subtle bg-white dark:bg-surface-1 rounded-t-lg">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-primary">Chat</h2>
          {/* Engine Badge */}
          <span
            className={`text-xs font-medium px-2 py-0.5 rounded-full ${
              engine === 'langgraph'
                ? 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
                : 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400'
            }`}
          >
            {engine === 'langgraph' ? 'LangGraph' : 'Legacy'}
          </span>
          {threadId && (
            <span className="text-xs text-gray-400 dark:text-muted font-mono">
              thread: {threadId.slice(0, 8)}...
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleNewConversation}
            className="px-3 py-1.5 text-xs font-medium text-gray-600 dark:text-secondary bg-gray-100 dark:bg-surface-2 rounded-md hover:bg-gray-200 dark:hover:bg-surface-2/70 transition-colors"
          >
            New Conversation
          </button>
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-1.5 text-gray-500 dark:text-secondary hover:text-gray-700 dark:hover:text-primary rounded-md hover:bg-gray-100 dark:hover:bg-surface-2 transition-colors"
            title="Settings"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
        </div>
      </div>

      {/* Settings Panel (collapsible) */}
      {showSettings && (
        <div className="px-4 py-3 bg-gray-50 dark:bg-surface-2 border-b border-gray-200 dark:border-border-subtle space-y-3 animate-slide-in">
          {/* Engine Toggle */}
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium text-gray-700 dark:text-secondary">Engine:</label>
            <div className="inline-flex bg-gray-200 dark:bg-surface-1 p-0.5 rounded-md">
              <button
                onClick={() => setEngine('langgraph')}
                className={`px-3 py-1 text-xs font-medium rounded transition-all ${
                  engine === 'langgraph'
                    ? 'bg-white dark:bg-surface-2 text-gray-900 dark:text-primary shadow-sm'
                    : 'text-gray-600 dark:text-secondary hover:text-gray-900 dark:hover:text-primary'
                }`}
              >
                LangGraph
              </button>
              <button
                onClick={() => setEngine('legacy')}
                className={`px-3 py-1 text-xs font-medium rounded transition-all ${
                  engine === 'legacy'
                    ? 'bg-white dark:bg-surface-2 text-gray-900 dark:text-primary shadow-sm'
                    : 'text-gray-600 dark:text-secondary hover:text-gray-900 dark:hover:text-primary'
                }`}
              >
                Legacy
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Spec & Journey Selectors */}
      <div className="px-4 py-3 bg-gray-50 dark:bg-surface-2 border-b border-gray-200 dark:border-border-subtle">
        <div className="flex gap-3">
          {/* Spec Selector */}
          <div className="flex-1">
            <select
              value={selectedSpecPath}
              onChange={(e) => handleSpecSelect(e.target.value)}
              disabled={loadingSpecs}
              className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-border rounded-md bg-white dark:bg-surface-1 text-gray-900 dark:text-primary focus:outline-none focus:ring-2 focus:ring-forge-500 dark:focus:ring-accent focus:border-transparent"
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
              className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-border rounded-md bg-white dark:bg-surface-1 text-gray-900 dark:text-primary focus:outline-none focus:ring-2 focus:ring-forge-500 dark:focus:ring-accent focus:border-transparent disabled:opacity-50"
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
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 bg-white dark:bg-surface-0">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-gray-400 dark:text-muted">
            <div className="text-center">
              <svg className="w-12 h-12 mx-auto mb-3 text-gray-300 dark:text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              <p className="text-sm">Select a spec and journey, then start chatting.</p>
              <p className="text-xs mt-1 text-gray-300 dark:text-muted">Multi-turn conversations persist via thread_id</p>
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
            <div className="bg-gray-100 dark:bg-surface-1 rounded-lg px-4 py-3 max-w-[75%]">
              <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-secondary">
                <svg className="animate-spin w-3.5 h-3.5" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Processing...
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Error */}
      {error && (
        <div className="mx-4 mb-2 p-3 bg-red-50 dark:bg-danger/10 border border-red-200 dark:border-danger/30 rounded-md text-sm text-red-700 dark:text-danger">
          {error}
        </div>
      )}

      {/* Input Area */}
      <div className="px-4 py-3 border-t border-gray-200 dark:border-border-subtle bg-white dark:bg-surface-1 rounded-b-lg">
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
            className="flex-1 px-4 py-2.5 bg-white dark:bg-surface-2 text-gray-900 dark:text-primary border border-gray-300 dark:border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-forge-500 dark:focus:ring-accent focus:border-transparent resize-none disabled:opacity-50 disabled:cursor-not-allowed"
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
            className="px-4 py-2.5 bg-forge-600 dark:bg-accent text-white rounded-lg font-medium hover:bg-forge-700 dark:hover:bg-accent/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
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
              ? 'bg-forge-600 dark:bg-accent text-white'
              : 'bg-gray-100 dark:bg-surface-1 text-gray-900 dark:text-primary'
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
          <div className="p-3 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-lg text-sm">
            <div className="flex items-center gap-2 mb-1">
              <svg className="w-4 h-4 text-amber-600 dark:text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
              <span className="font-medium text-amber-800 dark:text-amber-300">Approval Required</span>
            </div>
            <p className="text-amber-700 dark:text-amber-400 text-xs mb-2">
              Step "{message.hitl_info.step_name}" needs {message.hitl_info.escalate_to} approval.
            </p>
            {hitlPending && onHITLDecision && (
              <div className="flex gap-2">
                <button
                  onClick={() => onHITLDecision(true)}
                  disabled={sending}
                  className="px-3 py-1.5 bg-green-600 text-white text-xs font-medium rounded-md hover:bg-green-700 disabled:opacity-50 transition-colors"
                >
                  Approve
                </button>
                <button
                  onClick={() => onHITLDecision(false)}
                  disabled={sending}
                  className="px-3 py-1.5 bg-red-600 text-white text-xs font-medium rounded-md hover:bg-red-700 disabled:opacity-50 transition-colors"
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
              className="flex items-center gap-1 text-xs text-gray-400 dark:text-muted hover:text-gray-600 dark:hover:text-secondary transition-colors"
            >
              <svg
                className={`w-3 h-3 transition-transform ${tracesExpanded ? 'rotate-90' : ''}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              {message.traces.length} step{message.traces.length !== 1 ? 's' : ''} executed
            </button>

            {tracesExpanded && (
              <div className="mt-1.5 pl-3 border-l-2 border-gray-200 dark:border-border-subtle space-y-1.5">
                {message.traces.map((trace, i) => (
                  <div key={i} className="text-xs">
                    <div className="flex items-center gap-2">
                      <StepStatusIcon status={trace.status} />
                      <span className="font-medium text-gray-700 dark:text-secondary">{trace.step_name}</span>
                      <span className="text-gray-400 dark:text-muted">{trace.step_type}</span>
                      {trace.duration_ms !== undefined && (
                        <span className="text-gray-400 dark:text-muted">{trace.duration_ms}ms</span>
                      )}
                    </div>
                    {trace.output_preview && (
                      <p className="mt-0.5 text-gray-500 dark:text-secondary pl-5 truncate">{trace.output_preview}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Timestamp */}
        <div className={`text-[10px] text-gray-300 dark:text-muted ${isUser ? 'text-right' : 'text-left'}`}>
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
    <div className="mt-2 p-4 bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/30 rounded-lg space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-indigo-800 dark:text-indigo-300">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        Please complete the following:
      </div>

      {handoffInfo.fields.map((field) => (
        <div key={field.id} className="space-y-1">
          {field.field_type !== 'checkbox' && (
            <label className="block text-xs font-medium text-gray-700 dark:text-secondary">
              {field.label}
              {field.required && <span className="text-red-500 dark:text-danger ml-0.5">*</span>}
            </label>
          )}

          {field.field_type === 'textarea' && (
            <textarea
              value={(formData[field.id] as string) || ''}
              onChange={(e) => handleChange(field.id, e.target.value)}
              placeholder={field.placeholder || ''}
              rows={2}
              className="w-full px-3 py-1.5 bg-white dark:bg-surface-2 text-gray-900 dark:text-primary border border-gray-300 dark:border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            />
          )}

          {field.field_type === 'text' && (
            <input
              type="text"
              value={(formData[field.id] as string) || ''}
              onChange={(e) => handleChange(field.id, e.target.value)}
              placeholder={field.placeholder || ''}
              className="w-full px-3 py-1.5 bg-white dark:bg-surface-2 text-gray-900 dark:text-primary border border-gray-300 dark:border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          )}

          {field.field_type === 'select' && (
            <select
              value={(formData[field.id] as string) || ''}
              onChange={(e) => handleChange(field.id, e.target.value)}
              className="w-full px-3 py-1.5 border border-gray-300 dark:border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white dark:bg-surface-2 text-gray-900 dark:text-primary"
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
                        ? 'border-indigo-400 dark:border-indigo-500/50 bg-indigo-100 dark:bg-indigo-500/15 text-indigo-800 dark:text-indigo-300'
                        : 'border-gray-200 dark:border-border-subtle bg-white dark:bg-surface-2 hover:border-gray-300 dark:hover:border-border text-gray-700 dark:text-secondary'
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
                className="mt-0.5 rounded border-gray-300 dark:border-border text-indigo-600 focus:ring-indigo-500"
              />
              <span className="text-xs text-gray-700 dark:text-secondary">{field.label}</span>
            </label>
          )}
        </div>
      ))}

      <button
        onClick={handleSubmit}
        disabled={loading}
        className="w-full py-2 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
      >
        {loading ? (
          <>
            <svg className="animate-spin w-3.5 h-3.5" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
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
      return (
        <svg className="w-3 h-3 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      )
    case 'failed':
      return (
        <svg className="w-3 h-3 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      )
    case 'waiting_hitl':
      return (
        <svg className="w-3 h-3 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      )
    default:
      return (
        <svg className="w-3 h-3 text-gray-400 dark:text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <circle cx="12" cy="12" r="3" />
        </svg>
      )
  }
}
