import { RunResponse } from '../types'

interface ResultSummaryProps {
  result: RunResponse
}

export default function ResultSummary({ result }: ResultSummaryProps) {
  const statusConfig = getStatusConfig(result.status)

  return (
    <div className={`rounded-lg border-2 p-4 ${statusConfig.border} ${statusConfig.bg} animate-fade-in`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">{statusConfig.icon}</span>
          <span className={`font-semibold ${statusConfig.text}`}>
            {statusConfig.label}
          </span>
        </div>
        <div className="flex items-center gap-3 text-sm text-muted">
          <span>{result.traces.length} steps</span>
          <span>{result.execution_time_ms.toFixed(0)}ms</span>
        </div>
      </div>

      {/* Execution ID */}
      <div className="mt-2 text-xs text-muted">
        ID: <code className="bg-surface-0/40 px-1 rounded">{result.execution_id}</code>
      </div>
    </div>
  )
}

function getStatusConfig(status: string) {
  switch (status) {
    case 'completed':
      return {
        icon: '✅',
        label: 'Journey Completed',
        border: 'border-success/40',
        bg: 'bg-success/10',
        text: 'text-success',
      }
    case 'waiting_hitl':
      return {
        icon: '⏸️',
        label: 'Waiting for Human',
        border: 'border-warning/40',
        bg: 'bg-warning/10',
        text: 'text-warning',
      }
    case 'failed':
      return {
        icon: '❌',
        label: 'Execution Failed',
        border: 'border-danger/40',
        bg: 'bg-danger/10',
        text: 'text-danger',
      }
    default:
      return {
        icon: '⚙️',
        label: status,
        border: 'border-border',
        bg: 'bg-surface-1',
        text: 'text-secondary',
      }
  }
}
