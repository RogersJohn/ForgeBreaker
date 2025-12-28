import type { BreakingPointResponse } from '../api/client'
import { useBreakingPoint } from '../hooks/useDecks'

interface BreakingPointFinderProps {
  userId: string
  format: string
  deckName: string
}

export function BreakingPointFinder({
  userId,
  format,
  deckName,
}: BreakingPointFinderProps) {
  const { data, isLoading, error } = useBreakingPoint(userId, format, deckName)

  if (isLoading) {
    return (
      <div
        className="p-4 rounded-lg"
        style={{
          backgroundColor: 'var(--color-bg-surface)',
          border: '1px solid var(--color-border)',
        }}
      >
        <p style={{ color: 'var(--color-text-secondary)' }}>
          Analyzing breaking points...
        </p>
      </div>
    )
  }

  if (error || !data) {
    return null
  }

  return <BreakingPointDisplay data={data} />
}

function BreakingPointDisplay({ data }: { data: BreakingPointResponse }) {
  const resilienceColor =
    data.resilience_score > 0.7
      ? '#22c55e'
      : data.resilience_score > 0.4
        ? '#eab308'
        : '#ef4444'

  const resilienceLabel =
    data.resilience_score > 0.7
      ? 'Resilient'
      : data.resilience_score > 0.4
        ? 'Moderate'
        : 'Fragile'

  return (
    <div
      className="rounded-lg"
      style={{
        backgroundColor: 'var(--color-bg-surface)',
        border: '1px solid var(--color-border)',
      }}
    >
      {/* Header */}
      <div
        className="p-4 border-b"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <div className="flex items-center justify-between">
          <h3
            className="text-lg font-semibold"
            style={{ color: 'var(--color-text-primary)' }}
          >
            Breaking Point Analysis
          </h3>
          <span
            className="px-2 py-1 rounded text-xs font-medium"
            style={{
              backgroundColor: `${resilienceColor}20`,
              color: resilienceColor,
              border: `1px solid ${resilienceColor}40`,
            }}
          >
            {resilienceLabel} ({Math.round(data.resilience_score * 100)}%)
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Weakest Point */}
        <div
          className="p-3 rounded"
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.05)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
          }}
        >
          <div
            className="text-xs font-medium mb-1"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            Weakest Point
          </div>
          <div
            className="text-lg font-semibold"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {data.weakest_assumption}
          </div>
          {data.breaking_scenario && (
            <div
              className="text-sm mt-1"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              Breaks at {Math.round(data.breaking_intensity * 100)}% stress
              intensity
            </div>
          )}
        </div>

        {/* Breaking Scenario Details */}
        {data.breaking_scenario && (
          <div
            className="p-3 rounded"
            style={{
              backgroundColor: 'var(--color-bg-elevated)',
              border: '1px solid var(--color-border)',
            }}
          >
            <div
              className="text-xs font-medium mb-2"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              Stress Scenario That Causes Break
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span style={{ color: 'var(--color-text-secondary)' }}>
                  Type:{' '}
                </span>
                <span style={{ color: 'var(--color-text-primary)' }}>
                  {formatStressType(data.breaking_scenario.stress_type)}
                </span>
              </div>
              <div>
                <span style={{ color: 'var(--color-text-secondary)' }}>
                  Target:{' '}
                </span>
                <span style={{ color: 'var(--color-text-primary)' }}>
                  {data.breaking_scenario.target}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Resilience Meter */}
        <div>
          <div className="flex justify-between text-xs mb-1">
            <span style={{ color: 'var(--color-text-secondary)' }}>
              Resilience Score
            </span>
            <span style={{ color: resilienceColor }}>
              {Math.round(data.resilience_score * 100)}%
            </span>
          </div>
          <div
            className="w-full h-2 rounded-full overflow-hidden"
            style={{ backgroundColor: 'var(--color-bg-elevated)' }}
          >
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${data.resilience_score * 100}%`,
                backgroundColor: resilienceColor,
              }}
            />
          </div>
          <div
            className="flex justify-between text-xs mt-1"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            <span>Fragile</span>
            <span>Resilient</span>
          </div>
        </div>

        {/* Explanation */}
        <p
          className="text-sm leading-relaxed"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {data.explanation}
        </p>
      </div>
    </div>
  )
}

function formatStressType(type: string): string {
  const labels: Record<string, string> = {
    underperform: 'Underperformance',
    missing: 'Missing Card',
    delayed: 'Mana Problems',
    hostile_meta: 'Hostile Meta',
  }
  return labels[type] || type
}
