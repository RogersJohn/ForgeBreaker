import { useState } from 'react'
import type { DeckAssumption, AssumptionSetResponse } from '../api/client'

interface AssumptionPanelProps {
  data: AssumptionSetResponse
  isLoading?: boolean
}

const CATEGORY_LABELS: Record<string, string> = {
  mana_curve: 'Mana Curve',
  draw_consistency: 'Draw Consistency',
  key_cards: 'Key Cards',
  interaction_timing: 'Interaction',
}

const HEALTH_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  healthy: {
    bg: 'rgba(34, 197, 94, 0.1)',
    text: '#22c55e',
    border: 'rgba(34, 197, 94, 0.3)',
  },
  warning: {
    bg: 'rgba(234, 179, 8, 0.1)',
    text: '#eab308',
    border: 'rgba(234, 179, 8, 0.3)',
  },
  critical: {
    bg: 'rgba(239, 68, 68, 0.1)',
    text: '#ef4444',
    border: 'rgba(239, 68, 68, 0.3)',
  },
}

export function AssumptionPanel({ data, isLoading }: AssumptionPanelProps) {
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
    new Set(['mana_curve', 'key_cards'])
  )

  if (isLoading) {
    return (
      <div
        className="rounded-lg p-6"
        style={{
          backgroundColor: 'var(--color-bg-surface)',
          border: '1px solid var(--color-border)',
        }}
      >
        <p style={{ color: 'var(--color-text-secondary)' }}>
          Analyzing deck assumptions...
        </p>
      </div>
    )
  }

  const toggleCategory = (category: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(category)) {
        next.delete(category)
      } else {
        next.add(category)
      }
      return next
    })
  }

  // Group assumptions by category
  const byCategory = data.assumptions.reduce(
    (acc, assumption) => {
      const cat = assumption.category
      if (!acc[cat]) {
        acc[cat] = []
      }
      acc[cat].push(assumption)
      return acc
    },
    {} as Record<string, DeckAssumption[]>
  )

  const categories = Object.keys(byCategory)

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
        <div className="flex items-center justify-between mb-2">
          <h3
            className="text-lg font-semibold"
            style={{ color: 'var(--color-text-primary)' }}
          >
            Deck Assumptions
          </h3>
          <FragilityBadge fragility={data.overall_fragility} />
        </div>
        <p
          className="text-sm leading-relaxed"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {data.fragility_explanation}
        </p>
      </div>

      {/* Assumption Categories */}
      <div className="divide-y" style={{ borderColor: 'var(--color-border)' }}>
        {categories.map((category) => (
          <div key={category}>
            <button
              onClick={() => toggleCategory(category)}
              className="w-full px-4 py-3 flex items-center justify-between hover:opacity-80 transition-opacity"
              style={{ backgroundColor: 'transparent' }}
            >
              <span
                className="font-medium"
                style={{ color: 'var(--color-text-primary)' }}
              >
                {CATEGORY_LABELS[category] || category}
              </span>
              <div className="flex items-center gap-2">
                <CategoryHealthSummary assumptions={byCategory[category]} />
                <span style={{ color: 'var(--color-text-secondary)' }}>
                  {expandedCategories.has(category) ? '−' : '+'}
                </span>
              </div>
            </button>

            {expandedCategories.has(category) && (
              <div className="px-4 pb-4 space-y-3">
                {byCategory[category].map((assumption, idx) => (
                  <AssumptionCard key={idx} assumption={assumption} />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function FragilityBadge({ fragility }: { fragility: number }) {
  let label: string
  let color: string

  if (fragility < 0.2) {
    label = 'Stable'
    color = '#22c55e'
  } else if (fragility < 0.5) {
    label = 'Moderate'
    color = '#eab308'
  } else {
    label = 'Fragile'
    color = '#ef4444'
  }

  return (
    <span
      className="px-2 py-1 rounded text-xs font-medium"
      style={{
        backgroundColor: `${color}20`,
        color: color,
        border: `1px solid ${color}40`,
      }}
    >
      {label} ({Math.round(fragility * 100)}%)
    </span>
  )
}

function CategoryHealthSummary({ assumptions }: { assumptions: DeckAssumption[] }) {
  const warnings = assumptions.filter((a) => a.health === 'warning').length
  const criticals = assumptions.filter((a) => a.health === 'critical').length

  if (criticals > 0) {
    return (
      <span
        className="text-xs px-2 py-0.5 rounded"
        style={{
          backgroundColor: HEALTH_COLORS.critical.bg,
          color: HEALTH_COLORS.critical.text,
        }}
      >
        {criticals} critical
      </span>
    )
  }
  if (warnings > 0) {
    return (
      <span
        className="text-xs px-2 py-0.5 rounded"
        style={{
          backgroundColor: HEALTH_COLORS.warning.bg,
          color: HEALTH_COLORS.warning.text,
        }}
      >
        {warnings} warning
      </span>
    )
  }
  return (
    <span
      className="text-xs px-2 py-0.5 rounded"
      style={{
        backgroundColor: HEALTH_COLORS.healthy.bg,
        color: HEALTH_COLORS.healthy.text,
      }}
    >
      healthy
    </span>
  )
}

function AssumptionCard({ assumption }: { assumption: DeckAssumption }) {
  const [expanded, setExpanded] = useState(false)
  const colors = HEALTH_COLORS[assumption.health]

  const formatValue = (value: unknown): string => {
    if (Array.isArray(value)) {
      return value.slice(0, 3).join(', ') + (value.length > 3 ? '...' : '')
    }
    if (typeof value === 'number') {
      return value.toFixed(2)
    }
    return String(value)
  }

  return (
    <div
      className="rounded-lg p-3"
      style={{
        backgroundColor: colors.bg,
        border: `1px solid ${colors.border}`,
      }}
    >
      <div
        className="flex items-start justify-between cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span
              className="font-medium text-sm"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {assumption.name}
            </span>
            <span
              className="text-xs px-1.5 py-0.5 rounded"
              style={{ backgroundColor: colors.border, color: colors.text }}
            >
              {assumption.health}
            </span>
          </div>
          <p
            className="text-sm"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            {assumption.description}
          </p>
        </div>
        <span
          className="text-xs ml-2"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {expanded ? '−' : '+'}
        </span>
      </div>

      {expanded && (
        <div className="mt-3 pt-3 border-t" style={{ borderColor: colors.border }}>
          <p
            className="text-sm leading-relaxed mb-2"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            {assumption.explanation}
          </p>
          {typeof assumption.current_value !== 'undefined' &&
            assumption.expected_range[0] !== 0 &&
            assumption.expected_range[1] !== 0 && (
              <div className="flex items-center gap-4 text-xs">
                <span style={{ color: 'var(--color-text-secondary)' }}>
                  Current: <strong>{formatValue(assumption.current_value)}</strong>
                </span>
                <span style={{ color: 'var(--color-text-secondary)' }}>
                  Expected: {assumption.expected_range[0]} - {assumption.expected_range[1]}
                </span>
              </div>
            )}
        </div>
      )}
    </div>
  )
}
