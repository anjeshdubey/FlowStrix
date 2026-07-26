import { useState } from 'react'
import { Loader2, Play } from 'lucide-react'
import { JourneySummary, RunRequest, SpecSummary } from '../types'

interface JourneyRunnerProps {
  spec: SpecSummary
  specPath: string
  onRun: (request: RunRequest) => void
  disabled: boolean
  initialJourneyName?: string
  initialMessage?: string
}

export default function JourneyRunner({
  spec,
  specPath,
  onRun,
  disabled,
  initialJourneyName,
  initialMessage,
}: JourneyRunnerProps) {
  const [selectedJourney, setSelectedJourney] = useState<JourneySummary | null>(
    spec.journeys.find((j) => j.name === initialJourneyName) ?? (spec.journeys.length > 0 ? spec.journeys[0] : null)
  )
  const [message, setMessage] = useState(initialMessage ?? '')
  const [contextStr, setContextStr] = useState('{"customer_id": "cust_123"}')
  const [contextError, setContextError] = useState<string | null>(null)

  const handleRun = () => {
    if (!selectedJourney) return

    let context: Record<string, unknown> = {}
    if (contextStr.trim()) {
      try {
        context = JSON.parse(contextStr)
        setContextError(null)
      } catch {
        setContextError('Invalid JSON')
        return
      }
    }

    onRun({
      spec_path: specPath,
      journey: selectedJourney.name,
      message: message || undefined,
      context,
    })
  }

  return (
    <div className="space-y-4">
      {/* Spec Info */}
      <div className="p-4 bg-surface-1 rounded-lg border border-border-subtle">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-semibold text-primary">{spec.agent}</h3>
          <div className="flex gap-2 text-xs">
            <span className="bg-surface-2 text-secondary px-2 py-0.5 rounded">
              {spec.journeys.length} journey{spec.journeys.length !== 1 ? 's' : ''}
            </span>
            {spec.knowledge_sources > 0 && (
              <span className="bg-accent/10 text-accent px-2 py-0.5 rounded">
                {spec.knowledge_sources} knowledge
              </span>
            )}
            {spec.simulations > 0 && (
              <span className="bg-accent/10 text-accent px-2 py-0.5 rounded">
                {spec.simulations} simulations
              </span>
            )}
          </div>
        </div>
        <p className="text-sm text-muted">
          Persona: <span className="text-secondary">{spec.persona_name}</span> — {spec.persona_description}
        </p>
      </div>

      {/* Journey Selection */}
      <div>
        <label className="block text-sm font-medium text-secondary mb-1">Journey</label>
        <div className="grid gap-2">
          {spec.journeys.map((j) => (
            <button
              key={j.name}
              onClick={() => setSelectedJourney(j)}
              className={`text-left p-3 rounded-lg border transition-all ${
                selectedJourney?.name === j.name
                  ? 'border-accent bg-accent/10 ring-1 ring-accent'
                  : 'border-border-subtle bg-surface-1 hover:border-border'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm text-primary">{j.name}</span>
                <span className="text-xs text-muted">
                  {j.step_count} steps
                </span>
              </div>
              <p className="text-xs text-muted mt-0.5">{j.description}</p>
              <div className="flex gap-1 mt-1.5">
                {j.step_types.map((t, i) => (
                  <span key={i} className="text-[10px] bg-surface-2 text-muted px-1.5 py-0.5 rounded">
                    {t}
                  </span>
                ))}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Message Input */}
      <div>
        <label className="block text-sm font-medium text-secondary mb-1">Message</label>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Enter user message (e.g., 'I want a refund for my headphones')"
          rows={2}
          className="w-full px-3 py-2 bg-surface-1 border border-border rounded-md text-sm text-primary placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent resize-none"
        />
      </div>

      {/* Context Input */}
      <div>
        <label className="block text-sm font-medium text-secondary mb-1">Context (JSON)</label>
        <textarea
          value={contextStr}
          onChange={(e) => {
            setContextStr(e.target.value)
            setContextError(null)
          }}
          placeholder='{"customer_id": "cust_123"}'
          rows={2}
          className={`w-full px-3 py-2 bg-surface-1 border rounded-md text-sm font-mono text-primary placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent resize-none ${
            contextError ? 'border-danger' : 'border-border'
          }`}
        />
        {contextError && (
          <p className="mt-1 text-xs text-danger">{contextError}</p>
        )}
      </div>

      {/* Run Button */}
      <button
        onClick={handleRun}
        disabled={!selectedJourney || disabled}
        className="w-full py-2.5 bg-accent text-surface-0 rounded-md font-medium hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {disabled ? (
          <>
            <Loader2 size={16} className="animate-spin" />
            Running...
          </>
        ) : (
          <>
            <Play size={16} />
            Execute Journey
          </>
        )}
      </button>
    </div>
  )
}
