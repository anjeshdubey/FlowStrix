import { useState } from 'react'
import { JourneySummary, RunRequest, SpecSummary } from '../types'

interface JourneyRunnerProps {
  spec: SpecSummary
  specPath: string
  onRun: (request: RunRequest) => void
  disabled: boolean
}

export default function JourneyRunner({ spec, specPath, onRun, disabled }: JourneyRunnerProps) {
  const [selectedJourney, setSelectedJourney] = useState<JourneySummary | null>(
    spec.journeys.length > 0 ? spec.journeys[0] : null
  )
  const [message, setMessage] = useState('')
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
      <div className="p-4 bg-white dark:bg-surface-1 rounded-lg border border-gray-200 dark:border-border-subtle">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-semibold text-gray-900 dark:text-primary">{spec.agent}</h3>
          <div className="flex gap-2 text-xs">
            <span className="bg-gray-100 dark:bg-surface-2 text-gray-600 dark:text-secondary px-2 py-0.5 rounded">
              {spec.journeys.length} journey{spec.journeys.length !== 1 ? 's' : ''}
            </span>
            {spec.knowledge_sources > 0 && (
              <span className="bg-purple-50 dark:bg-purple-500/15 text-purple-600 dark:text-purple-400 px-2 py-0.5 rounded">
                {spec.knowledge_sources} knowledge
              </span>
            )}
            {spec.simulations > 0 && (
              <span className="bg-blue-50 dark:bg-info/15 text-blue-600 dark:text-info px-2 py-0.5 rounded">
                {spec.simulations} simulations
              </span>
            )}
          </div>
        </div>
        <p className="text-sm text-gray-500 dark:text-secondary">
          Persona: <span className="text-gray-700 dark:text-primary">{spec.persona_name}</span> — {spec.persona_description}
        </p>
      </div>

      {/* Journey Selection */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-secondary mb-1">Journey</label>
        <div className="grid gap-2">
          {spec.journeys.map((j) => (
            <button
              key={j.name}
              onClick={() => setSelectedJourney(j)}
              className={`text-left p-3 rounded-lg border transition-all ${
                selectedJourney?.name === j.name
                  ? 'border-forge-500 dark:border-accent bg-forge-50 dark:bg-accent/10 ring-1 ring-forge-500 dark:ring-accent'
                  : 'border-gray-200 dark:border-border-subtle bg-white dark:bg-surface-1 hover:border-gray-300 dark:hover:border-border'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm text-gray-900 dark:text-primary">{j.name}</span>
                <span className="text-xs text-gray-400 dark:text-muted">
                  {j.step_count} steps
                </span>
              </div>
              <p className="text-xs text-gray-500 dark:text-secondary mt-0.5">{j.description}</p>
              <div className="flex gap-1 mt-1.5">
                {j.step_types.map((t, i) => (
                  <span key={i} className="text-[10px] bg-gray-100 dark:bg-surface-2 text-gray-500 dark:text-secondary px-1.5 py-0.5 rounded">
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
        <label className="block text-sm font-medium text-gray-700 dark:text-secondary mb-1">Message</label>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Enter user message (e.g., 'I want a refund for my headphones')"
          rows={2}
          className="w-full px-3 py-2 bg-white dark:bg-surface-1 text-gray-900 dark:text-primary border border-gray-300 dark:border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-forge-500 dark:focus:ring-accent focus:border-transparent resize-none"
        />
      </div>

      {/* Context Input */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-secondary mb-1">Context (JSON)</label>
        <textarea
          value={contextStr}
          onChange={(e) => {
            setContextStr(e.target.value)
            setContextError(null)
          }}
          placeholder='{"customer_id": "cust_123"}'
          rows={2}
          className={`w-full px-3 py-2 bg-white dark:bg-surface-1 text-gray-900 dark:text-primary border rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-forge-500 dark:focus:ring-accent focus:border-transparent resize-none ${
            contextError ? 'border-red-300 dark:border-danger' : 'border-gray-300 dark:border-border'
          }`}
        />
        {contextError && (
          <p className="mt-1 text-xs text-red-600 dark:text-danger">{contextError}</p>
        )}
      </div>

      {/* Run Button */}
      <button
        onClick={handleRun}
        disabled={!selectedJourney || disabled}
        className="w-full py-2.5 bg-forge-600 dark:bg-accent text-white rounded-md font-medium hover:bg-forge-700 dark:hover:bg-accent/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {disabled ? (
          <>
            <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Running...
          </>
        ) : (
          <>
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Execute Journey
          </>
        )}
      </button>
    </div>
  )
}
