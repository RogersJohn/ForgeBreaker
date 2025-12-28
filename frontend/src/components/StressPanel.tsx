import { useState } from 'react'
import type {
  StressType,
  StressResultResponse,
  AssumptionSetResponse,
} from '../api/client'
import { useStressDeck } from '../hooks/useDecks'

interface StressPanelProps {
  userId: string
  format: string
  deckName: string
  assumptions: AssumptionSetResponse | undefined
}

const STRESS_TYPES: { value: StressType; label: string; description: string }[] = [
  {
    value: 'underperform',
    label: 'Underperform',
    description: 'Key cards appear less frequently',
  },
  {
    value: 'missing',
    label: 'Missing Card',
    description: 'Remove copies of a specific card',
  },
  {
    value: 'delayed',
    label: 'Mana Problems',
    description: 'Simulate mana screw/flood',
  },
  {
    value: 'hostile_meta',
    label: 'Hostile Meta',
    description: 'Face more opponent interaction',
  },
]

const INTENSITY_LABELS: Record<number, string> = {
  0.25: 'Light',
  0.5: 'Moderate',
  0.75: 'Heavy',
  1.0: 'Maximum',
}

export function StressPanel({
  userId,
  format,
  deckName,
  assumptions,
}: StressPanelProps) {
  const [stressType, setStressType] = useState<StressType>('underperform')
  const [target, setTarget] = useState<string>('all')
  const [intensity, setIntensity] = useState<number>(0.5)
  const [result, setResult] = useState<StressResultResponse | null>(null)

  const stressMutation = useStressDeck(userId, format, deckName)

  // Get key cards from assumptions for target selection
  const keyCards: string[] = []
  if (assumptions) {
    const mustDrawAssumption = assumptions.assumptions.find(
      (a) => a.name === 'Must-Draw Cards'
    )
    if (mustDrawAssumption && Array.isArray(mustDrawAssumption.current_value)) {
      keyCards.push(...mustDrawAssumption.current_value)
    }
  }

  const handleRunStress = async () => {
    try {
      const response = await stressMutation.mutateAsync({
        stress_type: stressType,
        target,
        intensity,
      })
      setResult(response)
    } catch (error) {
      console.error('Stress test failed:', error)
    }
  }

  return (
    <div
      className="rounded-lg"
      style={{
        backgroundColor: 'var(--color-bg-surface)',
        border: '1px solid var(--color-border)',
      }}
    >
      {/* Header */}
      <div className="p-4 border-b" style={{ borderColor: 'var(--color-border)' }}>
        <h3
          className="text-lg font-semibold"
          style={{ color: 'var(--color-text-primary)' }}
        >
          Stress Testing
        </h3>
        <p
          className="text-sm mt-1"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          Test how your deck handles adversity
        </p>
      </div>

      {/* Controls */}
      <div className="p-4 space-y-4">
        {/* Stress Type Selection */}
        <div>
          <label
            className="block text-sm font-medium mb-2"
            style={{ color: 'var(--color-text-primary)' }}
          >
            Stress Type
          </label>
          <div className="grid grid-cols-2 gap-2">
            {STRESS_TYPES.map((type) => (
              <button
                key={type.value}
                onClick={() => setStressType(type.value)}
                className="p-2 rounded text-left transition-colors"
                style={{
                  backgroundColor:
                    stressType === type.value
                      ? 'var(--color-primary)'
                      : 'var(--color-bg-elevated)',
                  color:
                    stressType === type.value
                      ? 'white'
                      : 'var(--color-text-primary)',
                  border: `1px solid ${stressType === type.value ? 'var(--color-primary)' : 'var(--color-border)'}`,
                }}
              >
                <div className="font-medium text-sm">{type.label}</div>
                <div
                  className="text-xs mt-0.5"
                  style={{
                    color:
                      stressType === type.value
                        ? 'rgba(255,255,255,0.8)'
                        : 'var(--color-text-secondary)',
                  }}
                >
                  {type.description}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Target Selection (for missing card stress) */}
        {stressType === 'missing' && keyCards.length > 0 && (
          <div>
            <label
              className="block text-sm font-medium mb-2"
              style={{ color: 'var(--color-text-primary)' }}
            >
              Target Card
            </label>
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="w-full p-2 rounded text-sm"
              style={{
                backgroundColor: 'var(--color-bg-elevated)',
                color: 'var(--color-text-primary)',
                border: '1px solid var(--color-border)',
              }}
            >
              <option value="all">Any key card</option>
              {keyCards.map((card) => (
                <option key={card} value={card}>
                  {card}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Intensity Slider */}
        <div>
          <label
            className="block text-sm font-medium mb-2"
            style={{ color: 'var(--color-text-primary)' }}
          >
            Intensity: {INTENSITY_LABELS[intensity] || `${Math.round(intensity * 100)}%`}
          </label>
          <input
            type="range"
            min="0.25"
            max="1"
            step="0.25"
            value={intensity}
            onChange={(e) => setIntensity(parseFloat(e.target.value))}
            className="w-full"
          />
          <div
            className="flex justify-between text-xs mt-1"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            <span>Light</span>
            <span>Moderate</span>
            <span>Heavy</span>
            <span>Maximum</span>
          </div>
        </div>

        {/* Run Button */}
        <button
          onClick={handleRunStress}
          disabled={stressMutation.isPending}
          className="w-full py-2 px-4 rounded font-medium transition-colors"
          style={{
            backgroundColor: 'var(--color-primary)',
            color: 'white',
            opacity: stressMutation.isPending ? 0.6 : 1,
          }}
        >
          {stressMutation.isPending ? 'Running...' : 'Run Stress Test'}
        </button>
      </div>

      {/* Results */}
      {result && <StressResult result={result} />}
    </div>
  )
}

function StressResult({ result }: { result: StressResultResponse }) {
  const fragilityChange = result.stressed_fragility - result.original_fragility
  const isWorse = fragilityChange > 0

  return (
    <div
      className="p-4 border-t space-y-4"
      style={{ borderColor: 'var(--color-border)' }}
    >
      {/* Summary */}
      <div
        className="p-3 rounded"
        style={{
          backgroundColor: result.breaking_point
            ? 'rgba(239, 68, 68, 0.1)'
            : isWorse
              ? 'rgba(234, 179, 8, 0.1)'
              : 'rgba(34, 197, 94, 0.1)',
          border: `1px solid ${
            result.breaking_point
              ? 'rgba(239, 68, 68, 0.3)'
              : isWorse
                ? 'rgba(234, 179, 8, 0.3)'
                : 'rgba(34, 197, 94, 0.3)'
          }`,
        }}
      >
        <div className="flex items-center justify-between mb-2">
          <span
            className="font-medium"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {result.breaking_point ? 'Breaking Point Reached' : 'Stress Applied'}
          </span>
          <span
            className={`text-sm px-2 py-0.5 rounded ${
              result.breaking_point
                ? 'bg-red-500/20 text-red-400'
                : isWorse
                  ? 'bg-yellow-500/20 text-yellow-400'
                  : 'bg-green-500/20 text-green-400'
            }`}
          >
            {fragilityChange > 0 ? '+' : ''}
            {Math.round(fragilityChange * 100)}% fragility
          </span>
        </div>
        <p
          className="text-sm leading-relaxed"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {result.explanation}
        </p>
      </div>

      {/* Before/After Comparison */}
      <div className="grid grid-cols-2 gap-4">
        <div
          className="p-3 rounded"
          style={{
            backgroundColor: 'var(--color-bg-elevated)',
            border: '1px solid var(--color-border)',
          }}
        >
          <div
            className="text-xs font-medium mb-1"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            Before Stress
          </div>
          <div
            className="text-2xl font-bold"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {Math.round(result.original_fragility * 100)}%
          </div>
          <div
            className="text-xs"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            fragility
          </div>
        </div>
        <div
          className="p-3 rounded"
          style={{
            backgroundColor: 'var(--color-bg-elevated)',
            border: '1px solid var(--color-border)',
          }}
        >
          <div
            className="text-xs font-medium mb-1"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            After Stress
          </div>
          <div
            className="text-2xl font-bold"
            style={{
              color: result.breaking_point
                ? '#ef4444'
                : isWorse
                  ? '#eab308'
                  : '#22c55e',
            }}
          >
            {Math.round(result.stressed_fragility * 100)}%
          </div>
          <div
            className="text-xs"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            fragility
          </div>
        </div>
      </div>

      {/* Affected Assumptions */}
      {result.affected_assumptions.length > 0 && (
        <div>
          <h4
            className="text-sm font-medium mb-2"
            style={{ color: 'var(--color-text-primary)' }}
          >
            Affected Assumptions
          </h4>
          <div className="space-y-2">
            {result.affected_assumptions.map((assumption, idx) => (
              <div
                key={idx}
                className="p-2 rounded text-sm"
                style={{
                  backgroundColor: 'var(--color-bg-elevated)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span style={{ color: 'var(--color-text-primary)' }}>
                    {assumption.name}
                  </span>
                  <span
                    className={`text-xs px-1.5 py-0.5 rounded ${
                      assumption.stressed_health === 'critical'
                        ? 'bg-red-500/20 text-red-400'
                        : assumption.stressed_health === 'warning'
                          ? 'bg-yellow-500/20 text-yellow-400'
                          : 'bg-green-500/20 text-green-400'
                    }`}
                  >
                    {assumption.original_health} → {assumption.stressed_health}
                  </span>
                </div>
                <p
                  className="text-xs"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  {assumption.change_explanation}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recommendations */}
      {result.recommendations.length > 0 && (
        <div>
          <h4
            className="text-sm font-medium mb-2"
            style={{ color: 'var(--color-text-primary)' }}
          >
            Recommendations
          </h4>
          <ul className="space-y-1">
            {result.recommendations.map((rec, idx) => (
              <li
                key={idx}
                className="text-sm flex items-start gap-2"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                <span style={{ color: 'var(--color-primary)' }}>•</span>
                {rec}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
