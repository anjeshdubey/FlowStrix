import { useOutletContext } from 'react-router-dom'
import { Activity } from 'lucide-react'
import ResultSummary from '../components/ResultSummary'
import StepTimeline from '../components/StepTimeline'
import { AgentWorkspaceContext } from './AgentWorkspace'

export default function TracesPage() {
  const { execution } = useOutletContext<AgentWorkspaceContext>()
  const { result, steps } = execution

  if (!result || steps.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-muted text-2">
        <div className="text-center">
          <Activity size={44} className="mx-auto mb-3 text-muted" strokeWidth={1.5} />
          <p>Run a journey from the Journeys tab to see its execution trace here.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-3xl space-y-6">
      <ResultSummary result={result} />
      <StepTimeline steps={steps} />
    </div>
  )
}
