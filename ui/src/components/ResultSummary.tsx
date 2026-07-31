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
        <div className="flex items-center gap-3 text-sm text-gray-500">
          <span>{result.traces.length} steps</span>
          <span>{result.execution_time_ms.toFixed(0)}ms</span>
        </div>
      </div>

      {/* Execution ID */}
      <div className="mt-2 text-xs text-gray-400">
        ID: <code className="bg-white/50 px-1 rounded">{result.execution_id}</code>
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
        border: 'border-green-300',
        bg: 'bg-green-50',
        text: 'text-green-700',
      }
    case 'waiting_hitl':
      return {
        icon: '⏸️',
        label: 'Waiting for Human',
        border: 'border-amber-300',
        bg: 'bg-amber-50',
        text: 'text-amber-700',
      }
    case 'failed':
      return {
        icon: '❌',
        label: 'Execution Failed',
        border: 'border-red-300',
        bg: 'bg-red-50',
        text: 'text-red-700',
      }
    default:
      return {
        icon: '⚙️',
        label: status,
        border: 'border-gray-300',
        bg: 'bg-gray-50',
        text: 'text-gray-700',
      }
  }
}
