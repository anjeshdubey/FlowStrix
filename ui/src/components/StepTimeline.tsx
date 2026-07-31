import { StepState } from '../types'

interface StepTimelineProps {
  steps: StepState[]
}

const STEP_TYPE_ICONS: Record<string, string> = {
  lookup: '🔍',
  reason: '🧠',
  respond: '💬',
  branch: '🔀',
  hitl: '🙋',
  tool: '🔧',
  wait: '⏳',
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  hitl: 'Awaiting Human',
}

export default function StepTimeline({ steps }: StepTimelineProps) {
  if (steps.length === 0) return null

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-secondary uppercase tracking-wide">
        Execution Steps
      </h3>

      <div className="space-y-2">
        {steps.map((step, index) => (
          <div
            key={`${step.step_name}-${index}`}
            className={`step-card animate-slide-in ${getCardClass(step.status)}`}
            style={{ animationDelay: `${index * 100}ms` }}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {/* Status indicator */}
                <div className={`w-2.5 h-2.5 rounded-full ${getStatusDotClass(step.status)}`}>
                  {step.status === 'running' && (
                    <div className="w-2.5 h-2.5 rounded-full bg-forge-500 animate-ping" />
                  )}
                </div>

                {/* Step icon */}
                <span className="text-sm">{STEP_TYPE_ICONS[step.step_type] || '⚙️'}</span>

                {/* Step name */}
                <span className="font-medium text-sm">{step.step_name}</span>

                {/* Step type badge */}
                <span className="text-[10px] bg-white/60 px-1.5 py-0.5 rounded border border-current/10">
                  {step.step_type}
                </span>
              </div>

              <div className="flex items-center gap-2 text-xs">
                {step.duration_ms !== undefined && (
                  <span className="text-gray-400">
                    {step.duration_ms.toFixed(0)}ms
                  </span>
                )}
                <span className="font-medium">{STATUS_LABELS[step.status]}</span>
              </div>
            </div>

            {/* Output preview */}
            {step.output_preview && (
              <div className="mt-2 text-xs font-mono bg-white/50 rounded p-2 truncate">
                {step.output_preview}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function getCardClass(status: string): string {
  switch (status) {
    case 'running': return 'step-card-running'
    case 'completed': return 'step-card-completed'
    case 'failed': return 'step-card-failed'
    case 'hitl': return 'step-card-hitl'
    default: return 'step-card-pending'
  }
}

function getStatusDotClass(status: string): string {
  switch (status) {
    case 'running': return 'bg-forge-500'
    case 'completed': return 'bg-green-500'
    case 'failed': return 'bg-red-500'
    case 'hitl': return 'bg-amber-500'
    default: return 'bg-gray-300'
  }
}
