import { useCallback, useEffect, useState } from 'react'
import { getSpecDetail, getSpecYaml, listSpecs, saveSpec, SavedSpec } from '../../api'
import { JourneyDetail, SpecDetail } from '../../types'
import FlowCanvas, { FlowStep } from '../author/FlowCanvas'
import StepEditor from '../author/StepEditor'
import YAMLPreview from '../author/YAMLPreview'

type DiscoverStage = 'grid' | 'canvas'

export default function DiscoverView() {
  const [stage, setStage] = useState<DiscoverStage>('grid')
  const [specs, setSpecs] = useState<SavedSpec[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Canvas state
  const [activeSpec, setActiveSpec] = useState<SpecDetail | null>(null)
  const [activeSpecPath, setActiveSpecPath] = useState<string>('')
  const [activeJourney, setActiveJourney] = useState<JourneyDetail | null>(null)
  const [steps, setSteps] = useState<FlowStep[]>([])
  const [selectedStep, setSelectedStep] = useState<number | null>(null)
  const [loadingSpec, setLoadingSpec] = useState(false)
  const [showYaml, setShowYaml] = useState(false)
  const [yaml, setYaml] = useState('')
  const [loadingYaml, setLoadingYaml] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)

  // Load specs on mount
  useEffect(() => {
    listSpecs()
      .then(setSpecs)
      .catch(() => setSpecs([]))
      .finally(() => setLoading(false))
  }, [])

  const handleSpecClick = useCallback(async (spec: SavedSpec) => {
    setLoadingSpec(true)
    setError(null)
    setShowYaml(false)
    setYaml('')
    setSaveMessage(null)
    try {
      const detail = await getSpecDetail(spec.path)
      setActiveSpec(detail)
      setActiveSpecPath(spec.path)
      // Auto-select first journey
      if (detail.journeys.length > 0) {
        selectJourney(detail.journeys[0])
      }
      setStage('canvas')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load spec')
    } finally {
      setLoadingSpec(false)
    }
  }, [])

  const selectJourney = (journey: JourneyDetail) => {
    setActiveJourney(journey)
    setSteps(
      journey.steps.map((s) => ({
        name: s.name,
        type: s.type,
        description: s.description,
        prompt: s.prompt,
        condition: s.condition,
        if_true: s.if_true,
        if_false: s.if_false,
        escalate_to: s.escalate_to,
      }))
    )
    setSelectedStep(null)
  }

  const handleStepClick = useCallback((_step: FlowStep, index: number) => {
    setSelectedStep((prev) => (prev === index ? null : index))
  }, [])

  const handleBack = useCallback(() => {
    setStage('grid')
    setActiveSpec(null)
    setActiveSpecPath('')
    setActiveJourney(null)
    setSteps([])
    setSelectedStep(null)
    setShowYaml(false)
    setYaml('')
    setSaveMessage(null)
  }, [])

  const handleShowYaml = useCallback(async () => {
    if (showYaml) {
      setShowYaml(false)
      return
    }
    if (!activeSpecPath) return
    setLoadingYaml(true)
    try {
      const result = await getSpecYaml(activeSpecPath)
      setYaml(result.yaml_content)
      setShowYaml(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load YAML')
    } finally {
      setLoadingYaml(false)
    }
  }, [showYaml, activeSpecPath])

  const handleSaveSpec = useCallback(async () => {
    if (!yaml || !activeSpecPath) return
    setSaving(true)
    setSaveMessage(null)
    try {
      const filename = activeSpecPath.split('/').pop() || 'spec.yaml'
      const result = await saveSpec(filename, yaml)
      setSaveMessage(result.message)
    } catch (err) {
      setSaveMessage(`Failed: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setSaving(false)
    }
  }, [yaml, activeSpecPath])

  // --- Grid View ---
  if (stage === 'grid') {
    return (
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-primary mb-1">Discover Workflows</h1>
          <p className="text-gray-500 dark:text-secondary">Browse and inspect your saved agent workflows</p>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center h-48 text-gray-400 dark:text-muted">
            <div className="flex items-center gap-2">
              <svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Loading workflows...
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && specs.length === 0 && (
          <div className="flex flex-col items-center justify-center h-48 text-gray-400 dark:text-muted">
            <svg className="w-12 h-12 mb-3 text-gray-300 dark:text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            <p className="text-sm">No workflows yet. Create one in Author mode!</p>
          </div>
        )}

        {/* Spec Cards Grid */}
        {!loading && specs.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {specs.map((spec) => (
              <SpecCard
                key={spec.path}
                spec={spec}
                onClick={() => handleSpecClick(spec)}
                loading={loadingSpec}
              />
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="p-3 bg-red-50 dark:bg-danger/10 border border-red-200 dark:border-danger/30 rounded-lg text-sm text-red-700 dark:text-danger">
            <strong>Error:</strong> {error}
          </div>
        )}
      </div>
    )
  }

  // --- Canvas View ---
  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <button
          onClick={handleBack}
          className="flex items-center gap-1.5 text-sm text-gray-500 dark:text-secondary hover:text-gray-700 dark:hover:text-primary transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          All Workflows
        </button>

        {/* Spec info + actions */}
        <div className="flex items-center gap-2">
          {activeSpec && (
            <div className="text-right mr-3">
              <span className="text-sm font-semibold text-gray-900 dark:text-primary">{activeSpec.agent}</span>
              <span className="text-xs text-gray-500 dark:text-secondary ml-2">{activeSpec.persona_name}</span>
            </div>
          )}
          <button
            onClick={handleShowYaml}
            disabled={loadingYaml}
            className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
              showYaml ? 'bg-gray-900 dark:bg-surface-2 text-white dark:text-primary border-gray-900 dark:border-border' : 'bg-white dark:bg-surface-1 text-gray-700 dark:text-secondary border-gray-200 dark:border-border-subtle hover:bg-gray-50 dark:hover:bg-surface-2'
            }`}
          >
            {loadingYaml ? 'Loading...' : showYaml ? 'Hide YAML' : 'Show YAML'}
          </button>
          <button
            onClick={handleSaveSpec}
            disabled={saving || !yaml}
            className="px-3 py-1.5 text-sm bg-forge-600 dark:bg-accent text-white rounded-lg hover:bg-forge-700 dark:hover:bg-accent/90 transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving...' : saveMessage ? '✓ Saved' : 'Save Spec'}
          </button>
        </div>
      </div>

      {/* Save confirmation */}
      {saveMessage && (
        <div className={`text-xs px-3 py-1.5 rounded-md ${
          saveMessage.startsWith('Failed') ? 'bg-red-50 dark:bg-danger/10 text-red-700 dark:text-danger' : 'bg-green-50 dark:bg-success/10 text-green-700 dark:text-success'
        }`}>
          {saveMessage}
        </div>
      )}

      {/* Journey tabs (if multiple journeys) */}
      {activeSpec && activeSpec.journeys.length > 1 && (
        <div className="flex gap-2">
          {activeSpec.journeys.map((j) => (
            <button
              key={j.name}
              onClick={() => selectJourney(j)}
              className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                activeJourney?.name === j.name
                  ? 'bg-forge-600 dark:bg-accent text-white border-forge-600 dark:border-accent'
                  : 'bg-white dark:bg-surface-1 text-gray-700 dark:text-secondary border-gray-200 dark:border-border-subtle hover:bg-gray-50 dark:hover:bg-surface-2'
              }`}
            >
              {j.name}
              <span className="ml-1 text-xs opacity-70">({j.steps.length})</span>
            </button>
          ))}
        </div>
      )}

      {/* Journey description banner */}
      {activeJourney && (
        <div className="flex items-start gap-3 p-3 bg-forge-50 dark:bg-accent/10 border border-forge-200 dark:border-accent/30 rounded-lg">
          <div className="flex-shrink-0 mt-0.5">
            <svg className="w-5 h-5 text-forge-600 dark:text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900 dark:text-primary">{activeJourney.name}</p>
            <p className="text-xs text-gray-600 dark:text-secondary mt-0.5">{activeJourney.description}</p>
            <p className="text-xs text-gray-400 dark:text-muted mt-1">Trigger: {activeJourney.trigger_description}</p>
          </div>
          <div className="flex-shrink-0">
            <span className="text-xs font-semibold text-forge-700 dark:text-accent bg-forge-100 dark:bg-accent/15 px-2 py-0.5 rounded-full">
              {activeJourney.steps.length} steps
            </span>
          </div>
        </div>
      )}

      {/* Canvas + Editor/YAML layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Canvas */}
        <div className={`${selectedStep !== null || showYaml ? 'lg:col-span-7' : 'lg:col-span-12'}`}>
          <div className="bg-white dark:bg-surface-1 border border-gray-200 dark:border-border-subtle rounded-xl overflow-hidden">
            <div className="bg-gray-50 dark:bg-surface-2 border-b border-gray-200 dark:border-border-subtle px-4 py-2 flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 dark:text-secondary uppercase tracking-wide">Journey Canvas</span>
              <span className="text-xs text-gray-400 dark:text-muted">{steps.length} steps</span>
            </div>
            <div className="overflow-y-auto max-h-[65vh] bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] dark:bg-[radial-gradient(#2e323a_1px,transparent_1px)] [background-size:20px_20px]">
              <FlowCanvas
                steps={steps}
                agentName={activeSpec?.agent || ''}
                personaName={activeSpec?.persona_name || ''}
                onStepClick={handleStepClick}
                selectedStep={selectedStep}
                showFullDescription
              />
            </div>
          </div>
        </div>

        {/* Right panel: Step Editor and/or YAML */}
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

// --- Spec Card Component ---

interface SpecCardProps {
  spec: SavedSpec
  onClick: () => void
  loading: boolean
}

function SpecCard({ spec, onClick, loading }: SpecCardProps) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="group bg-white dark:bg-surface-1 border-2 border-gray-200 dark:border-border-subtle hover:border-forge-400 dark:hover:border-accent hover:shadow-lg rounded-2xl p-5 transition-all text-left w-full disabled:opacity-60"
    >
      {/* Icon & header */}
      <div className="flex items-start justify-between mb-3">
        <div className="w-11 h-11 bg-forge-100 dark:bg-accent/15 rounded-xl flex items-center justify-center group-hover:bg-forge-500 dark:group-hover:bg-accent transition-colors">
          <svg className="w-5 h-5 text-forge-600 dark:text-accent group-hover:text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
        </div>
        {spec.journey_count > 0 && (
          <span className="text-xs font-bold text-forge-600 dark:text-accent bg-forge-50 dark:bg-accent/10 px-2 py-0.5 rounded-full">
            {spec.journey_count} {spec.journey_count === 1 ? 'journey' : 'journeys'}
          </span>
        )}
      </div>

      {/* Title */}
      <h3 className="font-bold text-gray-900 dark:text-primary mb-1 truncate">{spec.agent}</h3>
      <p className="text-sm text-gray-500 dark:text-secondary mb-3 truncate">
        {spec.persona_name ? `Persona: ${spec.persona_name}` : spec.path}
      </p>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-gray-100 dark:border-border-subtle">
        <span className="text-xs text-gray-400 dark:text-muted truncate">{spec.path}</span>
        <span className="text-xs text-forge-600 dark:text-accent font-medium opacity-0 group-hover:opacity-100 transition-opacity">
          View Canvas →
        </span>
      </div>
    </button>
  )
}
