import { useState } from 'react'
import type { DeckResponse } from '../api/client'
import { useDecks } from '../hooks/useDecks'
import { DeckCard } from './DeckCard'

const FORMATS = [
  { value: 'standard', label: 'Standard' },
  { value: 'historic', label: 'Historic' },
  { value: 'explorer', label: 'Explorer' },
  { value: 'alchemy', label: 'Alchemy' },
  { value: 'brawl', label: 'Brawl' },
]

interface DeckBrowserProps {
  userId: string
  onSelectDeck?: (deck: DeckResponse) => void
}

export function DeckBrowser({ userId, onSelectDeck }: DeckBrowserProps) {
  const [format, setFormat] = useState('standard')
  const { data, isLoading, error } = useDecks(format)

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-gray-900">Meta Decks</h2>
        <select
          value={format}
          onChange={(e) => setFormat(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
        >
          {FORMATS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
      </div>

      {isLoading && (
        <div className="text-center py-8">
          <p className="text-gray-500">Loading decks...</p>
        </div>
      )}

      {error && (
        <div className="text-center py-8">
          <p className="text-red-600">Failed to load decks. Is the backend running?</p>
        </div>
      )}

      {data && data.decks.length === 0 && (
        <div className="text-center py-8">
          <p className="text-gray-500">No decks found for {format}.</p>
        </div>
      )}

      {data && data.decks.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data.decks.map((deck) => (
            <DeckCard
              key={deck.name}
              deck={deck}
              userId={userId}
              onSelect={onSelectDeck}
            />
          ))}
        </div>
      )}

      {data && (
        <p className="text-sm text-gray-400 mt-4 text-center">
          Showing {data.decks.length} decks for {format}
        </p>
      )}
    </div>
  )
}
