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
          Exploring which belief fails first...
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
  const hasVulnerability = data.most_vulnerable_belief !== 'None identified'

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
        <h3
          className="text-lg font-semibold"
          style={{ color: 'var(--color-text-primary)' }}
        >
          Most Vulnerable Belief
        </h3>
        <p
          className="text-sm mt-1"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          Which assumption fails first under stress?
        </p>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Vulnerable Belief */}
        {hasVulnerability ? (
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
              Given sufficient stress, this belief fails first:
            </div>
            <div
              className="text-lg font-semibold"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {data.most_vulnerable_belief}
            </div>
            {data.failing_scenario && (
              <div
                className="text-sm mt-2"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                Fails under: {formatScenario(data.failing_scenario)}
              </div>
            )}
          </div>
        ) : (
          <div
            className="p-3 rounded"
            style={{
              backgroundColor: 'rgba(34, 197, 94, 0.05)',
              border: '1px solid rgba(34, 197, 94, 0.2)',
            }}
          >
            <div
              className="text-xs font-medium mb-1"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              No clear vulnerability found
            </div>
            <div
              className="text-sm"
              style={{ color: 'var(--color-text-primary)' }}
            >
              The tested scenarios did not invalidate any beliefs.
            </div>
          </div>
        )}

        {/* Scenario Details */}
        {data.failing_scenario && (
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
              Scenario That Invalidates This Belief
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span style={{ color: 'var(--color-text-secondary)' }}>
                  Type:{' '}
                </span>
                <span style={{ color: 'var(--color-text-primary)' }}>
                  {formatStressType(data.failing_scenario.stress_type)}
                </span>
              </div>
              <div>
                <span style={{ color: 'var(--color-text-secondary)' }}>
                  Target:{' '}
                </span>
                <span style={{ color: 'var(--color-text-primary)' }}>
                  {data.failing_scenario.target}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Insight */}
        <div>
          <p
            className="text-sm leading-relaxed"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            {data.exploration_insight}
          </p>
        </div>

        {/* Disclaimer */}
        <p
          className="text-xs leading-relaxed"
          style={{ color: 'var(--color-text-secondary)', opacity: 0.7 }}
        >
          This analysis explores which belief is most sensitive to change.
          It does not predict how the deck will perform in actual games.
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

function formatScenario(scenario: { stress_type: string; target: string }): string {
  const type = formatStressType(scenario.stress_type)
  return `${type} (${scenario.target})`
}
