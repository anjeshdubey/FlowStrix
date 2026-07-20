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
      <div className="p-4 bg-white rounded-lg border border-gray-200">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-semibold text-gray-900">{spec.agent}</h3>
          <div className="flex gap-2 text-xs">
            <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
              {spec.journeys.length} journey{spec.journeys.length !== 1 ? 's' : ''}
            </span>
            {spec.knowledge_sources > 0 && (
              <span className="bg-purple-50 text-purple-600 px-2 py-0.5 rounded">
                {spec.knowledge_sources} knowledge
              </span>
            )}
            {spec.simulations > 0 && (
              <span className="bg-blue-50 text-blue-600 px-2 py-0.5 rounded">
                {spec.simulations} simulations
              </span>
            )}
          </div>
        </div>
        <p className="text-sm text-gray-500">
          Persona: <span className="text-gray-700">{spec.persona_name}</span> — {spec.persona_description}
        </p>
      </div>

      {/* Journey Selection */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Journey</label>
        <div className="grid gap-2">
          {spec.journeys.map((j) => (
            <button
              key={j.name}
              onClick={() => setSelectedJourney(j)}
              className={`text-left p-3 rounded-lg border transition-all ${
                selectedJourney?.name === j.name
                  ? 'border-forge-500 bg-forge-50 ring-1 ring-forge-500'
                  : 'border-gray-200 bg-white hover:border-gray-300'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm text-gray-900">{j.name}</span>
                <span className="text-xs text-gray-400">
                  {j.step_count} steps
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-0.5">{j.description}</p>
              <div className="flex gap-1 mt-1.5">
                {j.step_types.map((t, i) => (
                  <span key={i} className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
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
        <label className="block text-sm font-medium text-gray-700 mb-1">Message</label>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Enter user message (e.g., 'I want a refund for my headphones')"
          rows={2}
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-forge-500 focus:border-transparent resize-none"
        />
      </div>

      {/* Context Input */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Context (JSON)</label>
        <textarea
          value={contextStr}
          onChange={(e) => {
            setContextStr(e.target.value)
            setContextError(null)
          }}
          placeholder='{"customer_id": "cust_123"}'
          rows={2}
          className={`w-full px-3 py-2 border rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-forge-500 focus:border-transparent resize-none ${
            contextError ? 'border-red-300' : 'border-gray-300'
          }`}
        />
        {contextError && (
          <p className="mt-1 text-xs text-red-600">{contextError}</p>
        )}
      </div>

      {/* Run Button */}
      <button
        onClick={handleRun}
        disabled={!selectedJourney || disabled}
        className="w-full py-2.5 bg-forge-600 text-white rounded-md font-medium hover:bg-forge-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
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
