import type { DeckResponse } from '../api/client'
import { useDeckDistance } from '../hooks/useDecks'

interface DeckCardProps {
  deck: DeckResponse
  userId: string
  onSelect?: (deck: DeckResponse) => void
}

export function DeckCard({ deck, userId, onSelect }: DeckCardProps) {
  const { data: distance, isLoading } = useDeckDistance(
    userId,
    deck.format,
    deck.name
  )

  const completionPercent = distance?.completion_percentage ?? 0
  const isComplete = distance?.is_complete ?? false

  return (
    <div
      className="bg-white rounded-lg shadow p-4 hover:shadow-md transition-shadow cursor-pointer"
      onClick={() => onSelect?.(deck)}
    >
      <div className="flex justify-between items-start mb-2">
        <h3 className="text-lg font-medium text-gray-900">{deck.name}</h3>
        <span className="px-2 py-1 text-xs font-medium rounded-full bg-gray-100 text-gray-600">
          {deck.archetype}
        </span>
      </div>

      {/* Win rate and meta share */}
      <div className="flex gap-4 text-sm text-gray-500 mb-3">
        {deck.win_rate != null && (
          <span>Win rate: {(deck.win_rate * 100).toFixed(1)}%</span>
        )}
        {deck.meta_share != null && (
          <span>Meta: {(deck.meta_share * 100).toFixed(1)}%</span>
        )}
      </div>

      {/* Completion bar */}
      <div className="mt-2">
        <div className="flex justify-between text-sm mb-1">
          <span className="text-gray-600">Collection Progress</span>
          {isLoading ? (
            <span className="text-gray-400">Loading...</span>
          ) : (
            <span
              className={
                isComplete
                  ? 'text-green-600 font-medium'
                  : 'text-gray-900 font-medium'
              }
            >
              {completionPercent.toFixed(0)}%
            </span>
          )}
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all ${
              isComplete
                ? 'bg-green-500'
                : completionPercent >= 75
                  ? 'bg-yellow-500'
                  : 'bg-indigo-500'
            }`}
            style={{ width: `${completionPercent}%` }}
          />
        </div>
      </div>

      {/* Missing cards summary */}
      {distance && !isComplete && (
        <div className="mt-3 text-sm text-gray-500">
          Missing {distance.missing_cards} cards ({distance.wildcard_cost.total}{' '}
          wildcards)
        </div>
      )}

      {isComplete && (
        <div className="mt-3 text-sm text-green-600 font-medium">
          You can build this deck!
        </div>
      )}
    </div>
  )
}
