import { CheckCircle2, Play } from 'lucide-react'

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

const STEP_COLORS: Record<string, { border: string; bg: string; ring: string; text: string }> = {
  lookup: { border: 'border-info/40', bg: 'bg-info/10', ring: 'ring-info/30', text: 'text-info' },
  reason: { border: 'border-accent/40', bg: 'bg-accent/10', ring: 'ring-accent/30', text: 'text-accent' },
  respond: { border: 'border-success/40', bg: 'bg-success/10', ring: 'ring-success/30', text: 'text-success' },
  branch: { border: 'border-warning/40', bg: 'bg-warning/10', ring: 'ring-warning/30', text: 'text-warning' },
  hitl: { border: 'border-danger/40', bg: 'bg-danger/10', ring: 'ring-danger/30', text: 'text-danger' },
  tool: { border: 'border-info/40', bg: 'bg-info/10', ring: 'ring-info/30', text: 'text-info' },
  wait: { border: 'border-border', bg: 'bg-surface-2', ring: 'ring-border', text: 'text-muted' },
}

export default function FlowCanvas({ steps, agentName, personaName, onStepClick, selectedStep, showFullDescription = false }: FlowCanvasProps) {
  return (
    <div className="flex flex-col items-center py-8 px-4">
      {/* Agent header */}
      <div className="mb-6 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-accent/10 border border-accent/30 rounded-full text-sm">
          <span className="w-2 h-2 bg-accent rounded-full" />
          <span className="font-medium text-accent">{agentName}</span>
          <span className="text-accent/50">•</span>
          <span className="text-accent/80">{personaName}</span>
        </div>
      </div>

      {/* Start node */}
      <div className="w-12 h-12 rounded-full bg-accent flex items-center justify-center shadow-glow-accent mb-2">
        <Play className="w-5 h-5 text-surface-0" fill="currentColor" />
      </div>

      {/* Steps */}
      {steps.map((step, index) => (
        <div key={`${step.name}-${index}`} className="flex flex-col items-center">
          {/* Connector */}
          <div className="w-0.5 h-8 bg-border relative">
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-0 h-0 border-t-[6px] border-t-border border-l-[4px] border-l-transparent border-r-[4px] border-r-transparent" />
          </div>

          {/* Step node */}
          <button
            onClick={() => onStepClick(step, index)}
            className={`group relative ${showFullDescription ? 'w-80' : 'w-64'} p-4 rounded-xl border-2 transition-all hover:scale-[1.02] hover:shadow-2 ${
              selectedStep === index
                ? `${STEP_COLORS[step.type]?.border || 'border-border'} ${STEP_COLORS[step.type]?.bg || 'bg-surface-2'} ring-2 ${STEP_COLORS[step.type]?.ring || 'ring-border'} shadow-2`
                : 'border-border-subtle bg-surface-1 hover:border-border'
            }`}
          >
            {/* Step type badge */}
            <div className="absolute -top-2.5 left-4">
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide ${
                STEP_COLORS[step.type]?.bg || 'bg-surface-2'
              } ${STEP_COLORS[step.type]?.text || 'text-secondary'} border ${STEP_COLORS[step.type]?.border || 'border-border-subtle'}`}>
                <span>{STEP_ICONS[step.type] || '⚙️'}</span>
                {step.type}
              </span>
            </div>

            {/* Step content */}
            <div className="mt-1">
              <h4 className="font-semibold text-sm text-primary">{step.name}</h4>
              <p className={`text-xs text-secondary mt-1 ${showFullDescription ? '' : 'line-clamp-2'}`}>{step.description}</p>
            </div>

            {/* Branch indicators */}
            {step.type === 'branch' && (
              <div className="flex gap-2 mt-2">
                <span className="text-[10px] bg-success/10 text-success px-1.5 py-0.5 rounded">
                  ✓ {step.if_true}
                </span>
                <span className="text-[10px] bg-danger/10 text-danger px-1.5 py-0.5 rounded">
                  ✗ {step.if_false}
                </span>
              </div>
            )}

            {/* HITL indicator */}
            {step.type === 'hitl' && step.escalate_to && (
              <div className="mt-2">
                <span className="text-[10px] bg-danger/10 text-danger px-1.5 py-0.5 rounded">
                  → {step.escalate_to}
                </span>
              </div>
            )}
          </button>
        </div>
      ))}

      {/* End node */}
      <div className="w-0.5 h-8 bg-border relative">
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-0 h-0 border-t-[6px] border-t-border border-l-[4px] border-l-transparent border-r-[4px] border-r-transparent" />
      </div>
      <div className="w-12 h-12 rounded-full bg-surface-2 flex items-center justify-center shadow-2">
        <CheckCircle2 className="w-5 h-5 text-primary" />
      </div>
    </div>
  )
}
