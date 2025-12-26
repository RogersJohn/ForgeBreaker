import type { CollectionStatsResponse } from '../api/client'

interface CollectionStatsProps {
  stats: CollectionStatsResponse
}

const RARITY_COLORS: Record<string, string> = {
  common: 'var(--color-rarity-common)',
  uncommon: 'var(--color-rarity-uncommon)',
  rare: 'var(--color-rarity-rare)',
  mythic: 'var(--color-rarity-mythic)',
  other: 'var(--color-rarity-other)',
}

const MANA_COLORS: Record<string, string> = {
  W: 'var(--color-mana-w)',
  U: 'var(--color-mana-u)',
  B: 'var(--color-mana-b)',
  R: 'var(--color-mana-r)',
  G: 'var(--color-mana-g)',
  colorless: 'var(--color-mana-colorless)',
  multicolor: 'var(--color-mana-multicolor)',
  other: 'var(--color-mana-other)',
}

function StatBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const percentage = max > 0 ? (value / max) * 100 : 0

  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="w-20 text-xs truncate" style={{ color: 'var(--color-text-secondary)' }}>
        {label}
      </span>
      <div
        className="flex-1 h-4 rounded-full overflow-hidden"
        style={{ backgroundColor: 'var(--color-bg-primary)' }}
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={`${label}: ${value.toLocaleString()} cards`}
      >
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${percentage}%`, backgroundColor: color }}
        />
      </div>
      <span className="w-12 text-xs text-right" style={{ color: 'var(--color-text-primary)' }}>
        {value.toLocaleString()}
      </span>
    </div>
  )
}

export function CollectionStats({ stats }: CollectionStatsProps) {
  const rarityMax = Math.max(...Object.values(stats.by_rarity || {}), 1)
  const colorMax = Math.max(...Object.values(stats.by_color || {}), 1)
  const typeMax = Math.max(...Object.values(stats.by_type || {}), 1)

  const rarityOrder = ['common', 'uncommon', 'rare', 'mythic', 'other']
  const colorOrder = ['W', 'U', 'B', 'R', 'G', 'colorless', 'multicolor', 'other']

  const sortedTypes = Object.entries(stats.by_type || {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 8)

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Summary */}
      <div
        className="p-4 rounded-lg"
        style={{ backgroundColor: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
      >
        <h4 className="text-sm font-medium mb-4" style={{ color: 'var(--color-text-secondary)' }}>
          Overview
        </h4>
        <div className="space-y-4">
          <div>
            <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>Total Cards</p>
            <p className="text-3xl font-bold" style={{ color: 'var(--color-accent-primary)' }}>
              {stats.total_cards.toLocaleString()}
            </p>
          </div>
          <div>
            <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>Unique Cards</p>
            <p className="text-3xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
              {stats.unique_cards.toLocaleString()}
            </p>
          </div>
        </div>
      </div>

      {/* Rarity Breakdown */}
      <div
        className="p-4 rounded-lg"
        style={{ backgroundColor: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
      >
        <h4 className="text-sm font-medium mb-4" style={{ color: 'var(--color-text-secondary)' }}>
          By Rarity
        </h4>
        {rarityOrder.map((rarity) => {
          const value = stats.by_rarity?.[rarity] || 0
          if (value === 0 && rarity === 'other') return null
          return (
            <StatBar
              key={rarity}
              label={rarity.charAt(0).toUpperCase() + rarity.slice(1)}
              value={value}
              max={rarityMax}
              color={RARITY_COLORS[rarity] || '#666'}
            />
          )
        })}
      </div>

      {/* Color Breakdown */}
      <div
        className="p-4 rounded-lg"
        style={{ backgroundColor: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
      >
        <h4 className="text-sm font-medium mb-4" style={{ color: 'var(--color-text-secondary)' }}>
          By Color
        </h4>
        {colorOrder.map((color) => {
          const value = stats.by_color?.[color] || 0
          if (value === 0 && (color === 'other' || color === 'multicolor')) return null
          const label = color === 'colorless' ? 'Colorless' : color === 'multicolor' ? 'Multi' : color
          return (
            <StatBar
              key={color}
              label={label}
              value={value}
              max={colorMax}
              color={MANA_COLORS[color] || '#666'}
            />
          )
        })}
      </div>

      {/* Type Breakdown */}
      <div
        className="p-4 rounded-lg lg:col-span-3"
        style={{ backgroundColor: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
      >
        <h4 className="text-sm font-medium mb-4" style={{ color: 'var(--color-text-secondary)' }}>
          By Card Type
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {sortedTypes.map(([type, value]) => (
            <StatBar
              key={type}
              label={type}
              value={value}
              max={typeMax}
              color="var(--color-accent-primary)"
            />
          ))}
        </div>
      </div>
    </div>
  )
}
