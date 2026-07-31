
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
  lookup: { border: 'border-blue-300 dark:border-blue-500/40', bg: 'bg-blue-50 dark:bg-blue-500/10', ring: 'ring-blue-200 dark:ring-blue-500/30' },
  reason: { border: 'border-purple-300 dark:border-purple-500/40', bg: 'bg-purple-50 dark:bg-purple-500/10', ring: 'ring-purple-200 dark:ring-purple-500/30' },
  respond: { border: 'border-green-300 dark:border-success/40', bg: 'bg-green-50 dark:bg-success/10', ring: 'ring-green-200 dark:ring-success/30' },
  branch: { border: 'border-amber-300 dark:border-warning/40', bg: 'bg-amber-50 dark:bg-warning/10', ring: 'ring-amber-200 dark:ring-warning/30' },
  hitl: { border: 'border-red-300 dark:border-danger/40', bg: 'bg-red-50 dark:bg-danger/10', ring: 'ring-red-200 dark:ring-danger/30' },
  tool: { border: 'border-cyan-300 dark:border-cyan-500/40', bg: 'bg-cyan-50 dark:bg-cyan-500/10', ring: 'ring-cyan-200 dark:ring-cyan-500/30' },
  wait: { border: 'border-gray-300 dark:border-border', bg: 'bg-gray-50 dark:bg-surface-1', ring: 'ring-gray-200 dark:ring-border' },
}

export default function FlowCanvas({ steps, agentName, personaName, onStepClick, selectedStep, showFullDescription = false }: FlowCanvasProps) {
  return (
    <div className="flex flex-col items-center py-8 px-4">
      {/* Agent header */}
      <div className="mb-6 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-forge-50 dark:bg-accent/10 border border-forge-200 dark:border-accent/30 rounded-full text-sm">
          <span className="w-2 h-2 bg-forge-500 dark:bg-accent rounded-full" />
          <span className="font-medium text-forge-700 dark:text-accent">{agentName}</span>
          <span className="text-forge-400 dark:text-accent/60">•</span>
          <span className="text-forge-500 dark:text-accent/80">{personaName}</span>
        </div>
      </div>

      {/* Start node */}
      <div className="w-12 h-12 rounded-full bg-forge-600 dark:bg-accent flex items-center justify-center shadow-lg mb-2">
        <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
          <path d="M8 5v14l11-7z" />
        </svg>
      </div>

      {/* Steps */}
      {steps.map((step, index) => (
        <div key={`${step.name}-${index}`} className="flex flex-col items-center">
          {/* Connector */}
          <div className="w-0.5 h-8 bg-gray-300 dark:bg-border relative">
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-0 h-0 border-t-[6px] border-t-gray-300 dark:border-t-border border-l-[4px] border-l-transparent border-r-[4px] border-r-transparent" />
          </div>

          {/* Step node */}
          <button
            onClick={() => onStepClick(step, index)}
            className={`group relative ${showFullDescription ? 'w-80' : 'w-64'} p-4 rounded-xl border-2 transition-all hover:scale-[1.02] hover:shadow-lg ${
              selectedStep === index
                ? `${STEP_COLORS[step.type]?.border || 'border-gray-300 dark:border-border'} ${STEP_COLORS[step.type]?.bg || 'bg-gray-50 dark:bg-surface-1'} ring-2 ${STEP_COLORS[step.type]?.ring || 'ring-gray-200 dark:ring-border'} shadow-md`
                : 'border-gray-200 dark:border-border-subtle bg-white dark:bg-surface-1 hover:border-gray-300 dark:hover:border-border'
            }`}
          >
            {/* Step type badge */}
            <div className="absolute -top-2.5 left-4">
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide ${
                STEP_COLORS[step.type]?.bg || 'bg-gray-100 dark:bg-surface-2'
              } border ${STEP_COLORS[step.type]?.border || 'border-gray-200 dark:border-border-subtle'}`}>
                <span>{STEP_ICONS[step.type] || '⚙️'}</span>
                {step.type}
              </span>
            </div>

            {/* Step content */}
            <div className="mt-1">
              <h4 className="font-semibold text-sm text-gray-900 dark:text-primary">{step.name}</h4>
              <p className={`text-xs text-gray-500 dark:text-secondary mt-1 ${showFullDescription ? '' : 'line-clamp-2'}`}>{step.description}</p>
            </div>

            {/* Branch indicators */}
            {step.type === 'branch' && (
              <div className="flex gap-2 mt-2">
                <span className="text-[10px] bg-green-100 dark:bg-success/15 text-green-700 dark:text-success px-1.5 py-0.5 rounded">
                  ✓ {step.if_true}
                </span>
                <span className="text-[10px] bg-red-100 dark:bg-danger/15 text-red-700 dark:text-danger px-1.5 py-0.5 rounded">
                  ✗ {step.if_false}
                </span>
              </div>
            )}

            {/* HITL indicator */}
            {step.type === 'hitl' && step.escalate_to && (
              <div className="mt-2">
                <span className="text-[10px] bg-red-100 dark:bg-danger/15 text-red-700 dark:text-danger px-1.5 py-0.5 rounded">
                  → {step.escalate_to}
                </span>
              </div>
            )}
          </button>
        </div>
      ))}

      {/* End node */}
      <div className="w-0.5 h-8 bg-gray-300 dark:bg-border relative">
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-0 h-0 border-t-[6px] border-t-gray-300 dark:border-t-border border-l-[4px] border-l-transparent border-r-[4px] border-r-transparent" />
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
