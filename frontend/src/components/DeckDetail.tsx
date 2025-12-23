import type { DeckResponse, DistanceResponse } from '../api/client'
import { useDeckDistance } from '../hooks/useDecks'

interface DeckDetailProps {
  deck: DeckResponse
  userId: string
  onClose: () => void
}

function WildcardBadge({
  rarity,
  count,
}: {
  rarity: 'common' | 'uncommon' | 'rare' | 'mythic'
  count: number
}) {
  if (count === 0) return null

  const colors = {
    common: 'bg-gray-200 text-gray-800',
    uncommon: 'bg-gray-400 text-white',
    rare: 'bg-yellow-500 text-white',
    mythic: 'bg-orange-500 text-white',
  }

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[rarity]}`}
    >
      {count} {rarity}
    </span>
  )
}

function CardList({
  title,
  cards,
  distance,
}: {
  title: string
  cards: Record<string, number>
  distance?: DistanceResponse
}) {
  const entries = Object.entries(cards).sort(([a], [b]) => a.localeCompare(b))

  if (entries.length === 0) return null

  const missingMap = new Map(
    distance?.missing_card_list.map((c) => [c.name, c]) ?? []
  )

  return (
    <div>
      <h4 className="text-sm font-medium text-gray-700 mb-2">{title}</h4>
      <div className="space-y-1">
        {entries.map(([name, qty]) => {
          const missing = missingMap.get(name)
          const isMissing = missing && missing.quantity > 0

          return (
            <div
              key={name}
              className={`flex items-center justify-between py-1 px-2 rounded ${
                isMissing ? 'bg-red-50' : 'bg-gray-50'
              }`}
            >
              <span
                className={`text-sm ${
                  isMissing ? 'text-red-700' : 'text-gray-900'
                }`}
              >
                {qty}x {name}
              </span>
              {missing && missing.quantity > 0 && (
                <span className="text-xs text-red-600 font-medium">
                  Need {missing.quantity}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function DeckDetail({ deck, userId, onClose }: DeckDetailProps) {
  const { data: distance, isLoading } = useDeckDistance(
    userId,
    deck.format,
    deck.name
  )

  const completionPercent = distance?.completion_percentage ?? 0
  const isComplete = distance?.is_complete ?? false

  return (
    <div className="bg-white rounded-lg shadow">
      {/* Header */}
      <div className="border-b border-gray-200 px-6 py-4">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">{deck.name}</h2>
            <div className="flex items-center gap-3 mt-1">
              <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 text-gray-600">
                {deck.archetype}
              </span>
              <span className="text-sm text-gray-500">{deck.format}</span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-500"
            aria-label="Close"
          >
            <svg
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Stats */}
        <div className="flex gap-4 mt-3 text-sm text-gray-500">
          {deck.win_rate != null && (
            <span>Win rate: {(deck.win_rate * 100).toFixed(1)}%</span>
          )}
          {deck.meta_share != null && (
            <span>Meta: {(deck.meta_share * 100).toFixed(1)}%</span>
          )}
        </div>
      </div>

      {/* Completion Section */}
      <div className="px-6 py-4 border-b border-gray-200">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-700">
            Collection Progress
          </span>
          {isLoading ? (
            <span className="text-sm text-gray-400">Loading...</span>
          ) : (
            <span
              className={`text-sm font-semibold ${
                isComplete ? 'text-green-600' : 'text-gray-900'
              }`}
            >
              {completionPercent.toFixed(0)}%
            </span>
          )}
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2.5">
          <div
            className={`h-2.5 rounded-full transition-all ${
              isComplete
                ? 'bg-green-500'
                : completionPercent >= 75
                  ? 'bg-yellow-500'
                  : 'bg-indigo-500'
            }`}
            style={{ width: `${completionPercent}%` }}
          />
        </div>

        {distance && !isComplete && (
          <div className="mt-3">
            <div className="text-sm text-gray-600 mb-2">
              Missing {distance.missing_cards} cards (
              {distance.wildcard_cost.total} wildcards needed)
            </div>
            <div className="flex flex-wrap gap-2">
              <WildcardBadge
                rarity="common"
                count={distance.wildcard_cost.common}
              />
              <WildcardBadge
                rarity="uncommon"
                count={distance.wildcard_cost.uncommon}
              />
              <WildcardBadge rarity="rare" count={distance.wildcard_cost.rare} />
              <WildcardBadge
                rarity="mythic"
                count={distance.wildcard_cost.mythic}
              />
            </div>
          </div>
        )}

        {isComplete && (
          <div className="mt-3 text-sm text-green-600 font-medium">
            You have all the cards to build this deck!
          </div>
        )}
      </div>

      {/* Card Lists */}
      <div className="px-6 py-4 space-y-6 max-h-96 overflow-y-auto">
        <CardList title="Maindeck" cards={deck.cards} distance={distance} />
        {Object.keys(deck.sideboard).length > 0 && (
          <CardList
            title="Sideboard"
            cards={deck.sideboard}
            distance={distance}
          />
        )}
      </div>

      {/* Source Link */}
      {deck.source_url && (
        <div className="px-6 py-3 border-t border-gray-200 bg-gray-50">
          <a
            href={deck.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-indigo-600 hover:text-indigo-800"
          >
            View on source site
          </a>
        </div>
      )}
    </div>
  )
}
