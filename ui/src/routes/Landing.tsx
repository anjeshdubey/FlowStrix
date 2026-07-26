import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Zap } from 'lucide-react'
import { listSpecs, SavedSpec, getSpec } from '../api'
import { useHealth } from '../context/HealthContext'
import DagHero from '../components/landing/DagHero'

const PROVIDER_LABELS: Record<string, string> = {
  together: 'Together',
  groq: 'Groq',
  gemini: 'Gemini',
  anthropic: 'Anthropic',
}

function providerLabel(provider?: string) {
  if (!provider) return 'Gateway'
  return PROVIDER_LABELS[provider] ?? provider
}

export default function Landing() {
  const navigate = useNavigate()
  const health = useHealth()
  const [specs, setSpecs] = useState<SavedSpec[]>([])

  useEffect(() => {
    listSpecs()
      .then(setSpecs)
      .catch(() => setSpecs([]))
  }, [])

  const handleRunDemo = async () => {
    const candidate = specs.find((s) => s.agent.includes('customer_support')) ?? specs[0]
    if (!candidate) {
      navigate('/agents')
      return
    }
    try {
      const detail = await getSpec(candidate.path)
      const refundJourney = detail.journeys.find((j) => j.name.toLowerCase().includes('refund')) ?? detail.journeys[0]
      const params = new URLSearchParams({ demo: '1' })
      if (refundJourney) {
        params.set('journey', refundJourney.name)
        params.set('message', 'I want a refund for my headphones')
      }
      navigate(`/agents/${encodeURIComponent(candidate.path)}/journeys?${params.toString()}`)
    } catch {
      navigate(`/agents/${encodeURIComponent(candidate.path)}/journeys`)
    }
  }

  return (
    <div className="min-h-screen bg-surface-0 text-primary flex flex-col">
      <div className="flex items-center justify-between px-14 py-8">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-accent flex items-center justify-center shadow-glow-accent">
            <Zap size={14} className="text-surface-0" fill="currentColor" />
          </div>
          <span className="font-bold text-4 text-primary tracking-tight">FlowStrix</span>
        </div>

        <div className="flex items-center gap-2 rounded-full border border-border bg-surface-1 px-3.5 py-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${health?.gateway_configured ? 'bg-success' : 'bg-warning'}`} />
          <span className="font-mono text-1 text-secondary">
            {health?.gateway_configured
              ? health.model
                ? `${providerLabel(health.provider)} · ${health.model}`
                : 'Gateway Connected'
              : health
              ? 'No Gateway'
              : 'Checking…'}
          </span>
        </div>
      </div>

      <div className="flex-1 flex items-center px-14 gap-10 max-w-[1440px] mx-auto w-full">
        <div className="flex-none w-[520px] flex flex-col gap-7">
          <h1 className="text-6 leading-tight font-bold tracking-tight text-primary">
            Workflow automation, rebuilt for agents —{' '}
            <span className="text-accent">deterministic gates around probabilistic reasoning.</span>
          </h1>
          <p className="text-3 leading-relaxed text-secondary max-w-[460px]">
            Agents are declared as journeys in YAML, executed with full step-by-step traces, and tested with
            simulation suites before they ever touch a customer.
          </p>
          <div className="flex items-center gap-5 mt-2">
            <button
              onClick={handleRunDemo}
              className="px-[26px] py-3.5 bg-accent text-surface-0 font-bold text-3 rounded-md shadow-glow-accent hover:brightness-110"
            >
              Run the refund demo →
            </button>
            <button
              onClick={() => navigate('/agents')}
              className="px-2 py-3.5 bg-transparent text-secondary font-medium text-3 hover:text-primary"
            >
              Browse agents
            </button>
          </div>
        </div>

        <div className="flex-1 flex items-center justify-center h-full">
          <DagHero />
        </div>
      </div>

      <div className="h-[52px] flex-none border-t border-border-subtle flex items-center justify-center gap-6">
        <a href={`${import.meta.env.BASE_URL}engineering/`} className="text-1 text-muted hover:text-secondary no-underline">
          Architecture
        </a>
        <span className="text-border-strong text-1">·</span>
        <a
          href="https://github.com/anjeshdubey/FlowStrix"
          target="_blank"
          rel="noreferrer"
          className="text-1 text-muted hover:text-secondary no-underline"
        >
          GitHub
        </a>
      </div>
    </div>
  )
}
