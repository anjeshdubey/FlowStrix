// --- API Types (mirrors flowstrix/api/models.py) ---

export interface RunRequest {
  spec_path: string
  journey: string
  message?: string
  context?: Record<string, unknown>
  model?: string
  engine?: 'legacy' | 'langgraph'
  thread_id?: string
}

export interface StepTrace {
  step_name: string
  step_type: string
  status: string
  duration_ms?: number
  output_preview?: string
}

export interface HITLInfo {
  escalation_type: string
  escalate_to: string
  context: Record<string, unknown>
  step_name: string
}

export interface HandoffField {
  id: string
  label: string
  field_type: string
  required: boolean
  options: string[]
  placeholder: string
  validation: string | null
  prefilled_value: unknown | null
}

export interface HandoffInfo {
  step_name: string
  transition_message: string
  output_key: string
  fields: HandoffField[]
}

export interface RunResponse {
  execution_id: string
  status: string
  journey_name: string
  traces: StepTrace[]
  context_data: Record<string, unknown>
  messages: Array<{ role: string; content: string }>
  hitl_info?: HITLInfo
  handoff_info?: HandoffInfo
  execution_time_ms: number
  thread_id?: string
}

export interface ExecutionSummary {
  id: string
  spec_path: string
  journey_name: string
  status: string
  created_at: number
}

export interface StepEvent {
  event: string
  step_name?: string
  step_type?: string
  status?: string
  output_preview?: string
  timestamp: number
}

export interface JourneySummary {
  name: string
  description: string
  trigger_description: string
  step_count: number
  step_types: string[]
}

export interface JourneyStepDetail {
  name: string
  type: string
  description: string
  prompt?: string
  condition?: string
  if_true?: string
  if_false?: string
  escalate_to?: string
}

export interface JourneyDetail {
  name: string
  description: string
  trigger_description: string
  steps: JourneyStepDetail[]
}

export interface SpecDetail {
  agent: string
  persona_name: string
  persona_description: string
  journeys: JourneyDetail[]
  knowledge_sources: number
  simulations: number
}

export interface SpecSummary {
  agent: string
  persona_name: string
  persona_description: string
  journeys: JourneySummary[]
  knowledge_sources: number
  simulations: number
}

export interface HealthResponse {
  status: string
  version: string
  model?: string
  provider?: string
  gateway_configured: boolean
}

// --- Ghostwriter Types ---

export interface GhostwriteRequest {
  description: string
  agent_name?: string
  persona_name?: string
  tools_available?: string[]
  knowledge_docs?: string[]
}

export interface GhostwriteStepResponse {
  name: string
  type: string
  description: string
  prompt?: string
  condition?: string
  if_true?: string
  if_false?: string
  escalate_to?: string
  output_key?: string
  tool?: string
}

export interface GhostwriteJourneyResponse {
  name: string
  description: string
  trigger_description: string
  steps: GhostwriteStepResponse[]
}

export interface GhostwriteResponse {
  agent_name: string
  persona_name: string
  persona_description: string
  journeys: GhostwriteJourneyResponse[]
  yaml_output: string
  explanation: string
  confidence: number
}

// --- UI State ---

export type ExecutionStatus = 'idle' | 'loading_spec' | 'ready' | 'running' | 'completed' | 'waiting_hitl' | 'failed'

export interface StepState {
  step_name: string
  step_type: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'hitl'
  duration_ms?: number
  output_preview?: string
}
