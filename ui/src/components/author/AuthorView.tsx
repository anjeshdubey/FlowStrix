import { useCallback, useState } from 'react'
import { ghostwrite, saveSpec } from '../../api'
import { GhostwriteResponse } from '../../types'
import PromptEntry from './PromptEntry'
import FlowCanvas, { FlowStep } from './FlowCanvas'
import StepEditor from './StepEditor'
import YAMLPreview from './YAMLPreview'

// Demo: simulates ghostwriter generating a journey from NL
// In production this would call POST /api/ghostwrite
function generateJourneyFromPrompt(prompt: string): { agentName: string; personaName: string; personaDesc: string; steps: FlowStep[]; yaml: string } {
  // Smart demo: detect what the user is asking for
  const lower = prompt.toLowerCase()

  if (lower.includes('refund') || lower.includes('support') || lower.includes('customer')) {
    return {
      agentName: 'customer_support',
      personaName: 'Alex',
      personaDesc: 'Friendly and efficient customer support agent',
      steps: [
        { name: 'lookup_orders', type: 'lookup', description: 'Fetch customer order history from CRM', prompt: 'Retrieve recent orders for the customer' },
        { name: 'evaluate_eligibility', type: 'reason', description: 'Determine if the refund request is eligible based on policy', prompt: 'Evaluate whether this refund request meets our policy criteria. Consider: purchase date (within 30 days), item condition, and customer history.' },
        { name: 'check_amount', type: 'branch', description: 'Route based on refund amount', condition: '${refund_amount} > 500', if_true: 'require_approval', if_false: 'process_refund' },
        { name: 'require_approval', type: 'hitl', description: 'High-value refund requires manager approval', escalate_to: 'manager_queue' },
        { name: 'process_refund', type: 'tool', description: 'Execute the refund transaction', prompt: 'Process refund for the given order' },
        { name: 'send_confirmation', type: 'respond', description: 'Send friendly confirmation to the customer', prompt: 'Confirm the refund has been processed. Include the amount, expected timeline (3-5 business days), and ask if there is anything else you can help with.' },
      ],
      yaml: generateYAML('customer_support', 'Alex', 'Friendly and efficient customer support agent', 'handle_refund', prompt),
    }
  }

  if (lower.includes('troubleshoot') || lower.includes('wifi') || lower.includes('tech')) {
    return {
      agentName: 'tech_support',
      personaName: 'Sam',
      personaDesc: 'Patient tech support specialist who explains things simply',
      steps: [
        { name: 'greet_and_ask_device', type: 'respond', description: 'Greet warmly and ask about their device', prompt: 'Greet the customer and ask what device they are using.' },
        { name: 'wait_for_device', type: 'wait', description: 'Wait for user to describe their device' },
        { name: 'parse_device_info', type: 'reason', description: 'Extract device type and platform from response', prompt: 'Extract the device type and platform from the customer response.' },
        { name: 'guide_restart', type: 'respond', description: 'Walk through restart steps', prompt: 'Guide the customer through restarting their router.' },
        { name: 'wait_for_result', type: 'wait', description: 'Wait for user to confirm result' },
        { name: 'check_resolved', type: 'branch', description: 'Check if issue is resolved', condition: '${resolved}', if_true: 'celebrate_fix', if_false: 'escalate_l2' },
        { name: 'celebrate_fix', type: 'respond', description: 'Celebrate that the issue is fixed', prompt: 'Congratulate the customer that their issue is resolved.' },
        { name: 'escalate_l2', type: 'hitl', description: 'Escalate to Level 2 support', escalate_to: 'level_2_support' },
      ],
      yaml: generateYAML('tech_support', 'Sam', 'Patient tech support specialist', 'wifi_troubleshooting', prompt),
    }
  }

  if (lower.includes('approval') || lower.includes('route') || lower.includes('approve')) {
    return {
      agentName: 'approval_router',
      personaName: 'Router',
      personaDesc: 'Efficient approval routing agent',
      steps: [
        { name: 'classify_request', type: 'reason', description: 'Classify the request type and determine routing', prompt: 'Classify this approval request by type, urgency, and required approval level.' },
        { name: 'check_amount_tier', type: 'branch', description: 'Route by amount tier', condition: '${amount} > 10000', if_true: 'vp_approval', if_false: 'manager_approval' },
        { name: 'manager_approval', type: 'hitl', description: 'Route to manager for approval', escalate_to: 'manager_queue' },
        { name: 'vp_approval', type: 'hitl', description: 'Route to VP for high-value approval', escalate_to: 'vp_queue' },
        { name: 'notify_requestor', type: 'respond', description: 'Notify the requestor of the decision', prompt: 'Inform the requestor about the approval decision and next steps.' },
      ],
      yaml: generateYAML('approval_router', 'Router', 'Efficient approval routing agent', 'route_approval', prompt),
    }
  }

  // Default: generic flow
  return {
    agentName: 'custom_agent',
    personaName: 'Agent',
    personaDesc: 'AI agent built from your description',
    steps: [
      { name: 'understand_request', type: 'reason', description: 'Analyze and understand the incoming request', prompt: 'Analyze the user request and extract key information needed to proceed.' },
      { name: 'check_conditions', type: 'branch', description: 'Evaluate conditions to determine path', condition: '${eligible}', if_true: 'execute_action', if_false: 'explain_denial' },
      { name: 'execute_action', type: 'tool', description: 'Execute the primary action', prompt: 'Execute the required action based on the analysis.' },
      { name: 'explain_denial', type: 'respond', description: 'Explain why the request cannot proceed', prompt: 'Politely explain why the request cannot be fulfilled and suggest alternatives.' },
      { name: 'send_response', type: 'respond', description: 'Send final response to user', prompt: 'Provide a clear, helpful response summarizing what was done.' },
    ],
    yaml: generateYAML('custom_agent', 'Agent', 'AI agent built from your description', 'main_journey', prompt),
  }
}

function generateYAML(agent: string, persona: string, desc: string, journey: string, _prompt: string): string {
  return `version: '1.0'
agent: ${agent}
persona:
  name: ${persona}
  description: ${desc}
  tone: professional, friendly
  guardrails:
    - Never share internal system details
    - Always confirm before taking actions
journeys:
  - name: ${journey}
    description: Generated from natural language description
    trigger:
      description: Activates on user request
    steps:
      # Steps generated by Ghostwriter
      # Edit individual steps in the canvas
      ...
knowledge: []
simulations: []`
}

type AuthorStage = 'prompt' | 'canvas'

export default function AuthorView() {
  const [stage, setStage] = useState<AuthorStage>('prompt')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [steps, setSteps] = useState<FlowStep[]>([])
  const [agentName, setAgentName] = useState('')
  const [personaName, setPersonaName] = useState('')
  const [yaml, setYaml] = useState('')
  const [confidence, setConfidence] = useState(0)
  const [explanation, setExplanation] = useState('')
  const [selectedStep, setSelectedStep] = useState<number | null>(null)
  const [showYaml, setShowYaml] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)

  const handleGenerate = useCallback(async (prompt: string) => {
    setLoading(true)
    setError(null)

    try {
      // Try real Ghostwriter API first
      const response: GhostwriteResponse = await ghostwrite({ description: prompt })

      // Use first journey's steps (or all journeys combined)
      const allSteps: FlowStep[] = []
      for (const journey of response.journeys) {
        for (const s of journey.steps) {
          allSteps.push({
            name: s.name,
            type: s.type,
            description: s.description,
            prompt: s.prompt,
            condition: s.condition,
            if_true: s.if_true,
            if_false: s.if_false,
            escalate_to: s.escalate_to,
          })
        }
      }

      setSteps(allSteps)
      setAgentName(response.agent_name)
      setPersonaName(response.persona_name)
      setYaml(response.yaml_output)
      setConfidence(response.confidence)
      setExplanation(response.explanation)
      setStage('canvas')
      setSelectedStep(null)
    } catch (err) {
      // Fallback to client-side demo generation
      const errMsg = err instanceof Error ? err.message : 'Unknown error'
      if (errMsg.includes('Gateway not configured') || errMsg.includes('503')) {
        // No LLM available — use demo fallback
        const result = generateJourneyFromPrompt(prompt)
        setSteps(result.steps)
        setAgentName(result.agentName)
        setPersonaName(result.personaName)
        setYaml(result.yaml)
        setConfidence(0.7)
        setExplanation('Generated using client-side demo (no LLM gateway configured)')
        setStage('canvas')
        setSelectedStep(null)
      } else {
        setError(errMsg)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  const handleStepClick = useCallback((_step: FlowStep, index: number) => {
    setSelectedStep(selectedStep === index ? null : index)
  }, [selectedStep])

  const handleBackToPrompt = useCallback(() => {
    setStage('prompt')
    setSteps([])
    setSelectedStep(null)
    setShowYaml(false)
  }, [])

  if (stage === 'prompt') {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh]">
        <PromptEntry onGenerate={handleGenerate} loading={loading} />
        {error && (
          <div className="mt-4 p-3 bg-red-50 dark:bg-danger/10 border border-red-200 dark:border-danger/30 rounded-lg text-sm text-red-700 dark:text-danger max-w-2xl w-full">
            <strong>Error:</strong> {error}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Confidence & Explanation banner */}
      {explanation && (
        <div className="flex items-start gap-3 p-3 bg-forge-50 dark:bg-accent/10 border border-forge-200 dark:border-accent/30 rounded-lg">
          <div className="flex-shrink-0 mt-0.5">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white ${
              confidence >= 0.8 ? 'bg-green-500 dark:bg-success' : confidence >= 0.6 ? 'bg-amber-500 dark:bg-warning' : 'bg-red-500 dark:bg-danger'
            }`}>
              {Math.round(confidence * 100)}
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-700 dark:text-secondary whitespace-pre-line line-clamp-3">{explanation}</p>
          </div>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <button
          onClick={handleBackToPrompt}
          className="flex items-center gap-1.5 text-sm text-gray-500 dark:text-secondary hover:text-gray-700 dark:hover:text-primary transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          New Journey
        </button>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowYaml(!showYaml)}
            className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
              showYaml ? 'bg-gray-900 dark:bg-surface-2 text-white dark:text-primary border-gray-900 dark:border-border' : 'bg-white dark:bg-surface-1 text-gray-700 dark:text-secondary border-gray-200 dark:border-border-subtle hover:bg-gray-50 dark:hover:bg-surface-2'
            }`}
          >
            {showYaml ? 'Hide YAML' : 'Show YAML'}
          </button>
          <button
            onClick={async () => {
              if (!yaml || !agentName) return
              setSaving(true)
              setSaveMessage(null)
              try {
                const filename = `${agentName}.yaml`
                const result = await saveSpec(filename, yaml)
                setSaveMessage(result.message)
              } catch (err) {
                setSaveMessage(`Failed: ${err instanceof Error ? err.message : 'Unknown error'}`)
              } finally {
                setSaving(false)
              }
            }}
            disabled={saving || !yaml}
            className="px-3 py-1.5 text-sm bg-forge-600 dark:bg-accent text-white rounded-lg hover:bg-forge-700 dark:hover:bg-accent/90 transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving...' : saveMessage ? '✓ Saved' : 'Save Spec'}
          </button>
        </div>
      </div>

      {/* Canvas + Editor layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Canvas (or Canvas + YAML) */}
        <div className={`${selectedStep !== null ? 'lg:col-span-7' : showYaml ? 'lg:col-span-7' : 'lg:col-span-12'}`}>
          <div className="bg-white dark:bg-surface-1 border border-gray-200 dark:border-border-subtle rounded-xl overflow-hidden">
            <div className="bg-gray-50 dark:bg-surface-2 border-b border-gray-200 dark:border-border-subtle px-4 py-2 flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 dark:text-secondary uppercase tracking-wide">Journey Canvas</span>
              <span className="text-xs text-gray-400 dark:text-muted">{steps.length} steps</span>
            </div>
            <div className="overflow-y-auto max-h-[65vh] bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] dark:bg-[radial-gradient(#2e323a_1px,transparent_1px)] [background-size:20px_20px]">
              <FlowCanvas
                steps={steps}
                agentName={agentName}
                personaName={personaName}
                onStepClick={handleStepClick}
                selectedStep={selectedStep}
              />
            </div>
          </div>
        </div>

        {/* Right panel: Step Editor or YAML */}
        {(selectedStep !== null || showYaml) && (
          <div className="lg:col-span-5 space-y-4">
            {selectedStep !== null && (
              <StepEditor
                step={steps[selectedStep]}
                index={selectedStep}
                onClose={() => setSelectedStep(null)}
              />
            )}
            {showYaml && <YAMLPreview yaml={yaml} />}
          </div>
        )}
      </div>
    </div>
  )
}
