import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, Info, Layers, Loader2, Workflow } from 'lucide-react'
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
          <h1 className="text-2xl font-bold text-gray-900 mb-1">Discover Workflows</h1>
          <p className="text-gray-500">Browse and inspect your saved agent workflows</p>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center h-48 text-gray-400">
            <div className="flex items-center gap-2">
              <Loader2 className="animate-spin w-5 h-5" />
              Loading workflows...
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && specs.length === 0 && (
          <div className="flex flex-col items-center justify-center h-48 text-gray-400">
            <Layers className="w-12 h-12 mb-3 text-gray-300" strokeWidth={1.5} />
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
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
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
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          All Workflows
        </button>

        {/* Spec info + actions */}
        <div className="flex items-center gap-2">
          {activeSpec && (
            <div className="text-right mr-3">
              <span className="text-sm font-semibold text-gray-900">{activeSpec.agent}</span>
              <span className="text-xs text-gray-500 ml-2">{activeSpec.persona_name}</span>
            </div>
          )}
          <button
            onClick={handleShowYaml}
            disabled={loadingYaml}
            className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
              showYaml ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
            }`}
          >
            {loadingYaml ? 'Loading...' : showYaml ? 'Hide YAML' : 'Show YAML'}
          </button>
          <button
            onClick={handleSaveSpec}
            disabled={saving || !yaml}
            className="px-3 py-1.5 text-sm bg-forge-600 text-white rounded-lg hover:bg-forge-700 transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving...' : saveMessage ? '✓ Saved' : 'Save Spec'}
          </button>
        </div>
      </div>

      {/* Save confirmation */}
      {saveMessage && (
        <div className={`text-xs px-3 py-1.5 rounded-md ${
          saveMessage.startsWith('Failed') ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
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
                  ? 'bg-forge-600 text-white border-forge-600'
                  : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
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
        <div className="flex items-start gap-3 p-3 bg-forge-50 border border-forge-200 rounded-lg">
          <div className="flex-shrink-0 mt-0.5">
            <Info className="w-5 h-5 text-forge-600" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900">{activeJourney.name}</p>
            <p className="text-xs text-gray-600 mt-0.5">{activeJourney.description}</p>
            <p className="text-xs text-gray-400 mt-1">Trigger: {activeJourney.trigger_description}</p>
          </div>
          <div className="flex-shrink-0">
            <span className="text-xs font-semibold text-forge-700 bg-forge-100 px-2 py-0.5 rounded-full">
              {activeJourney.steps.length} steps
            </span>
          </div>
        </div>
      )}

      {/* Canvas + Editor/YAML layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Canvas */}
        <div className={`${selectedStep !== null || showYaml ? 'lg:col-span-7' : 'lg:col-span-12'}`}>
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <div className="bg-gray-50 border-b border-gray-200 px-4 py-2 flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Journey Canvas</span>
              <span className="text-xs text-gray-400">{steps.length} steps</span>
            </div>
            <div
              className="overflow-y-auto max-h-[65vh]"
              style={{ backgroundImage: 'radial-gradient(#e5e7eb 1px, transparent 1px)', backgroundSize: '20px 20px' }}
            >
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
      className="group bg-white border-2 border-gray-200 hover:border-forge-400 hover:shadow-lg rounded-2xl p-5 transition-all text-left w-full disabled:opacity-60"
    >
      {/* Icon & header */}
      <div className="flex items-start justify-between mb-3">
        <div className="w-11 h-11 bg-forge-100 rounded-xl flex items-center justify-center group-hover:bg-forge-500 transition-colors">
          <Workflow className="w-5 h-5 text-forge-600 group-hover:text-white" />
        </div>
        {spec.journey_count > 0 && (
          <span className="text-xs font-bold text-forge-600 bg-forge-50 px-2 py-0.5 rounded-full">
            {spec.journey_count} {spec.journey_count === 1 ? 'journey' : 'journeys'}
          </span>
        )}
      </div>

      {/* Title */}
      <h3 className="font-bold text-gray-900 mb-1 truncate">{spec.agent}</h3>
      <p className="text-sm text-gray-500 mb-3 truncate">
        {spec.persona_name ? `Persona: ${spec.persona_name}` : spec.path}
      </p>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-gray-100">
        <span className="text-xs text-gray-400 truncate">{spec.path}</span>
        <span className="text-xs text-forge-600 font-medium opacity-0 group-hover:opacity-100 transition-opacity">
          View Canvas →
        </span>
      </div>
    </button>
  )
}
