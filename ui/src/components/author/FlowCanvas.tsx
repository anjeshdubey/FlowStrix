
export interface FlowStep {
  name: string
  type: string
  description: string
  prompt?: string
  condition?: string
  if_true?: string
  if_false?: string
  escalate_to?: string
}

interface FlowCanvasProps {
  steps: FlowStep[]
  agentName: string
  personaName: string
  onStepClick: (step: FlowStep, index: number) => void
  selectedStep: number | null
  showFullDescription?: boolean
}

const STEP_ICONS: Record<string, string> = {
  lookup: '🔍',
  reason: '🧠',
  respond: '💬',
  branch: '🔀',
  hitl: '🙋',
  tool: '🔧',
  wait: '⏳',
}

const STEP_COLORS: Record<string, { border: string; bg: string; ring: string }> = {
  lookup: { border: 'border-blue-300', bg: 'bg-blue-50', ring: 'ring-blue-200' },
  reason: { border: 'border-purple-300', bg: 'bg-purple-50', ring: 'ring-purple-200' },
  respond: { border: 'border-green-300', bg: 'bg-green-50', ring: 'ring-green-200' },
  branch: { border: 'border-amber-300', bg: 'bg-amber-50', ring: 'ring-amber-200' },
  hitl: { border: 'border-red-300', bg: 'bg-red-50', ring: 'ring-red-200' },
  tool: { border: 'border-cyan-300', bg: 'bg-cyan-50', ring: 'ring-cyan-200' },
  wait: { border: 'border-gray-300', bg: 'bg-gray-50', ring: 'ring-gray-200' },
}

export default function FlowCanvas({ steps, agentName, personaName, onStepClick, selectedStep, showFullDescription = false }: FlowCanvasProps) {
  return (
    <div className="flex flex-col items-center py-8 px-4">
      {/* Agent header */}
      <div className="mb-6 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-forge-50 border border-forge-200 rounded-full text-sm">
          <span className="w-2 h-2 bg-forge-500 rounded-full" />
          <span className="font-medium text-forge-700">{agentName}</span>
          <span className="text-forge-400">•</span>
          <span className="text-forge-500">{personaName}</span>
        </div>
      </div>

      {/* Start node */}
      <div className="w-12 h-12 rounded-full bg-forge-600 flex items-center justify-center shadow-lg mb-2">
        <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
          <path d="M8 5v14l11-7z" />
        </svg>
      </div>

      {/* Steps */}
      {steps.map((step, index) => (
        <div key={`${step.name}-${index}`} className="flex flex-col items-center">
          {/* Connector */}
          <div className="w-0.5 h-8 bg-gray-300 relative">
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-0 h-0 border-t-[6px] border-t-gray-300 border-l-[4px] border-l-transparent border-r-[4px] border-r-transparent" />
          </div>

          {/* Step node */}
          <button
            onClick={() => onStepClick(step, index)}
            className={`group relative ${showFullDescription ? 'w-80' : 'w-64'} p-4 rounded-xl border-2 transition-all hover:scale-[1.02] hover:shadow-lg ${
              selectedStep === index
                ? `${STEP_COLORS[step.type]?.border || 'border-gray-300'} ${STEP_COLORS[step.type]?.bg || 'bg-gray-50'} ring-2 ${STEP_COLORS[step.type]?.ring || 'ring-gray-200'} shadow-md`
                : 'border-gray-200 bg-white hover:border-gray-300'
            }`}
          >
            {/* Step type badge */}
            <div className="absolute -top-2.5 left-4">
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide ${
                STEP_COLORS[step.type]?.bg || 'bg-gray-100'
              } border ${STEP_COLORS[step.type]?.border || 'border-gray-200'}`}>
                <span>{STEP_ICONS[step.type] || '⚙️'}</span>
                {step.type}
              </span>
            </div>

            {/* Step content */}
            <div className="mt-1">
              <h4 className="font-semibold text-sm text-gray-900">{step.name}</h4>
              <p className={`text-xs text-gray-500 mt-1 ${showFullDescription ? '' : 'line-clamp-2'}`}>{step.description}</p>
            </div>

            {/* Branch indicators */}
            {step.type === 'branch' && (
              <div className="flex gap-2 mt-2">
                <span className="text-[10px] bg-green-100 text-green-700 px-1.5 py-0.5 rounded">
                  ✓ {step.if_true}
                </span>
                <span className="text-[10px] bg-red-100 text-red-700 px-1.5 py-0.5 rounded">
                  ✗ {step.if_false}
                </span>
              </div>
            )}

            {/* HITL indicator */}
            {step.type === 'hitl' && step.escalate_to && (
              <div className="mt-2">
                <span className="text-[10px] bg-red-100 text-red-700 px-1.5 py-0.5 rounded">
                  → {step.escalate_to}
                </span>
              </div>
            )}
          </button>
        </div>
      ))}

      {/* End node */}
      <div className="w-0.5 h-8 bg-gray-300 relative">
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-0 h-0 border-t-[6px] border-t-gray-300 border-l-[4px] border-l-transparent border-r-[4px] border-r-transparent" />
      </div>
      <div className="w-12 h-12 rounded-full bg-gray-800 flex items-center justify-center shadow-lg">
        <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
        </svg>
      </div>
    </div>
  )
}
