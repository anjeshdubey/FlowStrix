import { useEffect } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import { Zap } from 'lucide-react'
import { getSpec } from '../api'
import ContextViewer from '../components/ContextViewer'
import HandoffForm from '../components/HandoffForm'
import HITLPanel from '../components/HITLPanel'
import JourneyRunner from '../components/JourneyRunner'
import MessageThread from '../components/MessageThread'
import ResultSummary from '../components/ResultSummary'
import SpecLoader from '../components/SpecLoader'
import StepTimeline from '../components/StepTimeline'
import { AgentWorkspaceContext } from './AgentWorkspace'

export default function JourneysPage() {
  const { agentPath, execution } = useOutletContext<AgentWorkspaceContext>()
  const [searchParams] = useSearchParams()
  const demoJourney = searchParams.get('journey') ?? undefined
  const demoMessage = searchParams.get('message') ?? undefined
  const {
    status,
    spec,
    specPath,
    steps,
    result,
    error,
    hitlLoading,
    handoffLoading,
    handleSpecLoaded,
    handleRun,
    handleHITLDecision,
    handleHandoffSubmit,
    handleReset,
  } = execution

  // A CTA (e.g. the landing page's demo link) can deep-link straight into a
  // preloaded spec so the run form arrives prefilled instead of empty.
  useEffect(() => {
    if (!agentPath || spec || !searchParams.get('demo')) return
    getSpec(agentPath)
      .then((loaded) => handleSpecLoaded(loaded, agentPath))
      .catch(() => {})
  }, [agentPath, spec, searchParams, handleSpecLoaded])

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
      <div className="lg:col-span-5 space-y-6">
        <SpecLoader onSpecLoaded={handleSpecLoaded} />

        {spec && (
          <JourneyRunner
            spec={spec}
            specPath={specPath}
            onRun={handleRun}
            disabled={status === 'running'}
            initialJourneyName={demoJourney}
            initialMessage={demoMessage}
          />
        )}

        {(status === 'completed' || status === 'failed') && (
          <button
            onClick={handleReset}
            className="w-full py-2 text-2 text-secondary border border-border rounded-md hover:bg-surface-1"
          >
            Reset & Run Again
          </button>
        )}
      </div>

      <div className="lg:col-span-7 space-y-6">
        {status === 'idle' && (
          <div className="flex items-center justify-center h-64 text-muted text-2">
            <div className="text-center">
              <Zap size={44} className="mx-auto mb-3 text-muted" strokeWidth={1.5} />
              <p>Load a spec and execute a journey to see results here.</p>
            </div>
          </div>
        )}

        {status === 'ready' && steps.length === 0 && !result && (
          <div className="flex items-center justify-center h-64 text-muted text-2">
            <div className="text-center">
              <Zap size={44} className="mx-auto mb-3 text-accent" strokeWidth={1.5} />
              <p>
                Ready — hit <strong>Execute Journey</strong> to run.
              </p>
            </div>
          </div>
        )}

        {(status === 'running' || steps.length > 0 || result) && (
          <div className="space-y-6">
            {result && <ResultSummary result={result} />}

            <StepTimeline steps={steps} />

            {status === 'waiting_hitl' && result?.handoff_info && (
              <HandoffForm handoffInfo={result.handoff_info} onSubmit={handleHandoffSubmit} loading={handoffLoading} />
            )}

            {status === 'waiting_hitl' && result?.hitl_info && !result?.handoff_info && (
              <HITLPanel hitlInfo={result.hitl_info} onDecision={handleHITLDecision} loading={hitlLoading} />
            )}

            {result && <MessageThread messages={result.messages} />}

            {result && Object.keys(result.context_data).length > 0 && <ContextViewer data={result.context_data} />}
          </div>
        )}

        {error && (
          <div className="p-4 bg-danger/10 border border-danger/30 rounded-lg text-2 text-danger animate-slide-in">
            <strong>Error:</strong> {error}
          </div>
        )}
      </div>
    </div>
  )
}
