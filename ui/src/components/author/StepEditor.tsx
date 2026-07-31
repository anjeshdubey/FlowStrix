import { FlowStep } from './FlowCanvas'

interface StepEditorProps {
  step: FlowStep
  index: number
  onClose: () => void
}

export default function StepEditor({ step, index, onClose }: StepEditorProps) {
  return (
    <div className="bg-white dark:bg-surface-1 border border-gray-200 dark:border-border-subtle rounded-xl shadow-lg overflow-hidden animate-slide-in">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 dark:bg-surface-2 border-b border-gray-200 dark:border-border-subtle">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-secondary">
            Step {index + 1}
          </span>
          <span className="text-xs bg-forge-100 dark:bg-accent/15 text-forge-700 dark:text-accent px-2 py-0.5 rounded-full font-medium">
            {step.type}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 text-gray-400 dark:text-muted hover:text-gray-600 dark:hover:text-secondary transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Name */}
        <div>
          <label className="block text-xs font-semibold text-gray-600 dark:text-secondary uppercase tracking-wide mb-1">
            Name
          </label>
          <input
            type="text"
            defaultValue={step.name}
            className="w-full px-3 py-2 bg-white dark:bg-surface-2 text-gray-900 dark:text-primary border border-gray-200 dark:border-border-subtle rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-forge-500 dark:focus:ring-accent focus:border-transparent"
          />
        </div>

        {/* Description */}
        <div>
          <label className="block text-xs font-semibold text-gray-600 dark:text-secondary uppercase tracking-wide mb-1">
            Description
          </label>
          <textarea
            defaultValue={step.description}
            rows={2}
            className="w-full px-3 py-2 bg-white dark:bg-surface-2 text-gray-900 dark:text-primary border border-gray-200 dark:border-border-subtle rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-forge-500 dark:focus:ring-accent focus:border-transparent resize-none"
          />
        </div>

        {/* Prompt (for reason/respond steps) */}
        {(step.type === 'reason' || step.type === 'respond') && step.prompt && (
          <div>
            <label className="block text-xs font-semibold text-gray-600 dark:text-secondary uppercase tracking-wide mb-1">
              Prompt
            </label>
            <textarea
              defaultValue={step.prompt}
              rows={4}
              className="w-full px-3 py-2 bg-white dark:bg-surface-2 text-gray-900 dark:text-primary border border-gray-200 dark:border-border-subtle rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-forge-500 dark:focus:ring-accent focus:border-transparent resize-none"
            />
          </div>
        )}

        {/* Condition (for branch steps) */}
        {step.type === 'branch' && (
          <>
            <div>
              <label className="block text-xs font-semibold text-gray-600 dark:text-secondary uppercase tracking-wide mb-1">
                Condition
              </label>
              <input
                type="text"
                defaultValue={step.condition}
                className="w-full px-3 py-2 bg-white dark:bg-surface-2 text-gray-900 dark:text-primary border border-gray-200 dark:border-border-subtle rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-forge-500 dark:focus:ring-accent focus:border-transparent"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-green-600 dark:text-success uppercase tracking-wide mb-1">
                  If True →
                </label>
                <input
                  type="text"
                  defaultValue={step.if_true}
                  className="w-full px-3 py-2 bg-white dark:bg-surface-2 text-gray-900 dark:text-primary border border-green-200 dark:border-success/30 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-red-600 dark:text-danger uppercase tracking-wide mb-1">
                  If False →
                </label>
                <input
                  type="text"
                  defaultValue={step.if_false}
                  className="w-full px-3 py-2 bg-white dark:bg-surface-2 text-gray-900 dark:text-primary border border-red-200 dark:border-danger/30 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                />
              </div>
            </div>
          </>
        )}

        {/* Escalation (for hitl steps) */}
        {step.type === 'hitl' && (
          <div>
            <label className="block text-xs font-semibold text-gray-600 dark:text-secondary uppercase tracking-wide mb-1">
              Escalate To
            </label>
            <input
              type="text"
              defaultValue={step.escalate_to}
              className="w-full px-3 py-2 bg-white dark:bg-surface-2 text-gray-900 dark:text-primary border border-gray-200 dark:border-border-subtle rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-forge-500 dark:focus:ring-accent focus:border-transparent"
            />
          </div>
        )}
      </div>

      {/* Footer hint */}
      <div className="px-4 py-3 bg-gray-50 dark:bg-surface-2 border-t border-gray-100 dark:border-border-subtle">
        <p className="text-xs text-gray-400 dark:text-muted">
          Changes are reflected in the YAML preview. Save to persist.
        </p>
      </div>
    </div>
  )
}
