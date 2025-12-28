import { useState } from 'react'

interface ExplanationBlockProps {
  summary: string
  uncertainty?: string
  assumptions?: string[]
  confidence?: 'low' | 'medium' | 'high'
  compact?: boolean
}

const CONFIDENCE_COLORS: Record<string, { bg: string; text: string }> = {
  high: { bg: 'rgba(34, 197, 94, 0.1)', text: '#22c55e' },
  medium: { bg: 'rgba(234, 179, 8, 0.1)', text: '#eab308' },
  low: { bg: 'rgba(239, 68, 68, 0.1)', text: '#ef4444' },
}

export function ExplanationBlock({
  summary,
  uncertainty,
  assumptions,
  confidence = 'medium',
  compact = false,
}: ExplanationBlockProps) {
  const [expanded, setExpanded] = useState(false)
  const colors = CONFIDENCE_COLORS[confidence]
  const hasDetails = uncertainty || (assumptions && assumptions.length > 0)

  if (compact) {
    return (
      <div
        className="flex items-start gap-2 text-sm"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        <span className="text-xs" style={{ color: colors.text }}>
          ?
        </span>
        <span>{summary}</span>
      </div>
    )
  }

  return (
    <div
      className="rounded p-3"
      style={{
        backgroundColor: colors.bg,
        border: `1px solid ${colors.text}30`,
      }}
    >
      <div
        className={`flex items-start gap-2 ${hasDetails ? 'cursor-pointer' : ''}`}
        onClick={() => hasDetails && setExpanded(!expanded)}
      >
        <span
          className="text-xs font-medium mt-0.5"
          style={{ color: colors.text }}
        >
          {confidence === 'high' ? 'Confident' : confidence === 'low' ? 'Uncertain' : 'Note'}
        </span>
        <div className="flex-1">
          <p
            className="text-sm leading-relaxed"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {summary}
          </p>
        </div>
        {hasDetails && (
          <span
            className="text-xs"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            {expanded ? '−' : '+'}
          </span>
        )}
      </div>

      {expanded && hasDetails && (
        <div
          className="mt-3 pt-3 border-t space-y-2"
          style={{ borderColor: `${colors.text}30` }}
        >
          {uncertainty && (
            <div className="flex items-start gap-2">
              <span
                className="text-xs font-medium"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                If:
              </span>
              <p
                className="text-sm"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                {uncertainty}
              </p>
            </div>
          )}
          {assumptions && assumptions.length > 0 && (
            <div className="flex items-start gap-2">
              <span
                className="text-xs font-medium"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                Based on:
              </span>
              <div className="flex flex-wrap gap-1">
                {assumptions.map((assumption, idx) => (
                  <span
                    key={idx}
                    className="text-xs px-1.5 py-0.5 rounded"
                    style={{
                      backgroundColor: 'var(--color-bg-elevated)',
                      color: 'var(--color-text-secondary)',
                    }}
                  >
                    {assumption}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Inline explanation for use next to metrics
 */
export function InlineExplanation({
  text,
  confidence = 'medium',
}: {
  text: string
  confidence?: 'low' | 'medium' | 'high'
}) {
  const colors = CONFIDENCE_COLORS[confidence]

  return (
    <span
      className="text-xs ml-1"
      style={{ color: colors.text }}
      title={text}
    >
      *
    </span>
  )
}

/**
 * Tooltip-style explanation that appears on hover
 */
export function ExplanationTooltip({
  children,
  summary,
  uncertainty,
}: {
  children: React.ReactNode
  summary: string
  uncertainty?: string
}) {
  const [showTooltip, setShowTooltip] = useState(false)

  return (
    <div className="relative inline-block">
      <div
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        {children}
      </div>
      {showTooltip && (
        <div
          className="absolute z-50 w-64 p-3 rounded-lg shadow-lg text-sm"
          style={{
            backgroundColor: 'var(--color-bg-elevated)',
            border: '1px solid var(--color-border)',
            bottom: '100%',
            left: '50%',
            transform: 'translateX(-50%)',
            marginBottom: '8px',
          }}
        >
          <p style={{ color: 'var(--color-text-primary)' }}>{summary}</p>
          {uncertainty && (
            <p
              className="mt-2 text-xs"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              {uncertainty}
            </p>
          )}
          <div
            className="absolute w-2 h-2 rotate-45"
            style={{
              backgroundColor: 'var(--color-bg-elevated)',
              borderRight: '1px solid var(--color-border)',
              borderBottom: '1px solid var(--color-border)',
              bottom: '-5px',
              left: '50%',
              transform: 'translateX(-50%)',
            }}
          />
        </div>
      )}
    </div>
  )
}
