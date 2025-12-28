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
    description: 'What if key cards appear less frequently?',
  },
  {
    value: 'missing',
    label: 'Missing Card',
    description: 'What if a specific card is unavailable?',
  },
  {
    value: 'delayed',
    label: 'Mana Problems',
    description: 'What if mana development is delayed?',
  },
  {
    value: 'hostile_meta',
    label: 'Hostile Meta',
    description: 'What if opponents have more answers?',
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
    if (mustDrawAssumption && Array.isArray(mustDrawAssumption.observed_value)) {
      keyCards.push(...mustDrawAssumption.observed_value)
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
      console.error('Stress exploration failed:', error)
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
          Explore Hypothetical Scenarios
        </h3>
        <p
          className="text-sm mt-1"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          Examine which beliefs might not hold under certain conditions
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
            Scenario Type
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
          {stressMutation.isPending ? 'Exploring...' : 'Explore Scenario'}
        </button>
      </div>

      {/* Results */}
      {result && <StressResult result={result} />}
    </div>
  )
}

function StressResult({ result }: { result: StressResultResponse }) {
  const hasViolation = result.assumption_violated

  return (
    <div
      className="p-4 border-t space-y-4"
      style={{ borderColor: 'var(--color-border)' }}
    >
      {/* Summary */}
      <div
        className="p-3 rounded"
        style={{
          backgroundColor: hasViolation
            ? 'rgba(239, 68, 68, 0.1)'
            : 'rgba(34, 197, 94, 0.1)',
          border: `1px solid ${
            hasViolation
              ? 'rgba(239, 68, 68, 0.3)'
              : 'rgba(34, 197, 94, 0.3)'
          }`,
        }}
      >
        <div className="flex items-center justify-between mb-2">
          <span
            className="font-medium"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {hasViolation ? 'Belief Invalidated' : 'Beliefs Hold'}
          </span>
          {hasViolation && result.violated_belief && (
            <span className="text-sm px-2 py-0.5 rounded bg-red-500/20 text-red-400">
              {result.violated_belief}
            </span>
          )}
        </div>
        <p
          className="text-sm leading-relaxed"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {result.exploration_summary}
        </p>
        {hasViolation && result.violation_explanation && (
          <p
            className="text-sm leading-relaxed mt-2 pt-2 border-t"
            style={{
              color: 'var(--color-text-secondary)',
              borderColor: hasViolation
                ? 'rgba(239, 68, 68, 0.2)'
                : 'var(--color-border)',
            }}
          >
            {result.violation_explanation}
          </p>
        )}
      </div>

      {/* Affected Beliefs */}
      {result.affected_assumptions.length > 0 && (
        <div>
          <h4
            className="text-sm font-medium mb-2"
            style={{ color: 'var(--color-text-primary)' }}
          >
            Affected Beliefs
          </h4>
          <div className="space-y-2">
            {result.affected_assumptions.map((assumption, idx) => (
              <div
                key={idx}
                className="p-2 rounded text-sm"
                style={{
                  backgroundColor: assumption.belief_violated
                    ? 'rgba(239, 68, 68, 0.05)'
                    : 'var(--color-bg-elevated)',
                  border: `1px solid ${
                    assumption.belief_violated
                      ? 'rgba(239, 68, 68, 0.2)'
                      : 'var(--color-border)'
                  }`,
                }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span style={{ color: 'var(--color-text-primary)' }}>
                    {assumption.name}
                  </span>
                  <span
                    className={`text-xs px-1.5 py-0.5 rounded ${
                      assumption.belief_violated
                        ? 'bg-red-500/20 text-red-400'
                        : assumption.stressed_health === 'critical'
                          ? 'bg-red-500/20 text-red-400'
                          : assumption.stressed_health === 'warning'
                            ? 'bg-yellow-500/20 text-yellow-400'
                            : 'bg-green-500/20 text-green-400'
                    }`}
                  >
                    {assumption.belief_violated
                      ? 'violated'
                      : `${assumption.original_health} → ${assumption.stressed_health}`}
                  </span>
                </div>
                <p
                  className="text-xs"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  {assumption.belief_violated && assumption.violation_reason
                    ? assumption.violation_reason
                    : assumption.change_explanation}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Considerations */}
      {result.considerations.length > 0 && (
        <div>
          <h4
            className="text-sm font-medium mb-2"
            style={{ color: 'var(--color-text-primary)' }}
          >
            Things to Consider
          </h4>
          <ul className="space-y-1">
            {result.considerations.map((consideration, idx) => (
              <li
                key={idx}
                className="text-sm flex items-start gap-2"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                <span style={{ color: 'var(--color-primary)' }}>•</span>
                {consideration}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
