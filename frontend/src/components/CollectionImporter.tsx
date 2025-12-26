import { useState, useRef } from 'react'
import { useCollection, useCollectionStats, useImportCollection } from '../hooks/useCollection'
import { CollectionStats } from './CollectionStats'

interface CollectionImporterProps {
  userId: string
}

type Tab = 'tracker' | 'decks'

export function CollectionImporter({ userId }: CollectionImporterProps) {
  const [activeTab, setActiveTab] = useState<Tab>('tracker')
  const [importText, setImportText] = useState('')
  const [fileName, setFileName] = useState<string | null>(null)
  const [deckTexts, setDeckTexts] = useState<string[]>([''])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { data: collection, isLoading } = useCollection(userId)
  const { data: stats } = useCollectionStats(userId)
  const importMutation = useImportCollection(userId)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setFileName(file.name)
      const reader = new FileReader()
      reader.onload = (event) => {
        const text = event.target?.result as string
        setImportText(text)
      }
      reader.readAsText(file)
    }
  }

  const handleTrackerSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (importText.trim()) {
      importMutation.mutate(
        { text: importText },
        {
          onSuccess: () => {
            setImportText('')
            setFileName(null)
            if (fileInputRef.current) {
              fileInputRef.current.value = ''
            }
          },
        }
      )
    }
  }

  const handleDecksSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const combinedText = deckTexts.filter((t) => t.trim()).join('\n\n')
    if (combinedText.trim()) {
      importMutation.mutate(
        { text: combinedText, merge: true },
        {
          onSuccess: () => {
            setDeckTexts([''])
          },
        }
      )
    }
  }

  const addDeckField = () => {
    setDeckTexts([...deckTexts, ''])
  }

  const updateDeck = (index: number, value: string) => {
    const updated = [...deckTexts]
    updated[index] = value
    setDeckTexts(updated)
  }

  const removeDeck = (index: number) => {
    if (deckTexts.length > 1) {
      setDeckTexts(deckTexts.filter((_, i) => i !== index))
    }
  }

  return (
    <div className="h-full flex flex-col gap-6 overflow-y-auto">
      {/* Stats Section */}
      {stats && stats.total_cards > 0 && (
        <CollectionStats stats={stats} />
      )}

      {/* Import Section */}
      <div
        className="rounded-lg shadow-lg p-6"
        style={{ backgroundColor: 'var(--color-bg-surface)', border: '1px solid var(--color-border)' }}
      >
        <h2 className="text-xl font-semibold mb-4" style={{ color: 'var(--color-text-primary)' }}>
          {collection ? 'Update Collection' : 'Import Collection'}
        </h2>

        {isLoading && (
          <p style={{ color: 'var(--color-text-secondary)' }}>Loading collection...</p>
        )}

        {!collection && !isLoading && (
          <p className="mb-4" style={{ color: 'var(--color-text-secondary)' }}>
            Import your collection to get started with deck recommendations.
          </p>
        )}

        {/* Tab Navigation */}
        <div className="mb-4" style={{ borderBottom: '1px solid var(--color-border)' }}>
          <nav className="-mb-px flex space-x-6">
            <button
              onClick={() => setActiveTab('tracker')}
              className="py-2 px-1 font-medium text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)]"
              style={{
                borderBottom: activeTab === 'tracker' ? '2px solid var(--color-accent-primary)' : '2px solid transparent',
                color: activeTab === 'tracker' ? 'var(--color-accent-primary)' : 'var(--color-text-secondary)',
              }}
            >
              From Tracker Export
            </button>
            <button
              onClick={() => setActiveTab('decks')}
              className="py-2 px-1 font-medium text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)]"
              style={{
                borderBottom: activeTab === 'decks' ? '2px solid var(--color-accent-primary)' : '2px solid transparent',
                color: activeTab === 'decks' ? 'var(--color-accent-primary)' : 'var(--color-text-secondary)',
              }}
            >
              From Deck Lists
            </button>
          </nav>
        </div>

        {/* Tracker Export Tab */}
        {activeTab === 'tracker' && (
          <form onSubmit={handleTrackerSubmit}>
            <label
              htmlFor="tracker-export"
              className="block text-sm font-medium mb-2"
              style={{ color: 'var(--color-text-primary)' }}
            >
              Import from Tracker or Collection Manager
            </label>
            <p className="text-sm mb-3" style={{ color: 'var(--color-text-secondary)' }}>
              Upload a CSV file or paste your collection export below.
            </p>

            {/* File Upload */}
            <div className="mb-4">
              <div className="flex items-center gap-3">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.txt"
                  onChange={handleFileChange}
                  className="block w-full text-sm file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:cursor-pointer disabled:opacity-50"
                  style={{ color: 'var(--color-text-secondary)' }}
                  disabled={importMutation.isPending}
                />
              </div>
              {fileName && (
                <p className="mt-1 text-sm" style={{ color: 'var(--color-accent-primary)' }}>
                  Loaded: {fileName}
                </p>
              )}
            </div>

            <div className="relative my-4">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full" style={{ borderTop: '1px solid var(--color-border)' }} />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2" style={{ backgroundColor: 'var(--color-bg-surface)', color: 'var(--color-text-secondary)' }}>
                  or paste text
                </span>
              </div>
            </div>

            <div
              className="mb-3 p-3 rounded text-xs font-mono"
              style={{ backgroundColor: 'var(--color-bg-elevated)', color: 'var(--color-text-secondary)' }}
            >
              <p className="font-semibold mb-1" style={{ color: 'var(--color-text-primary)' }}>Accepted formats:</p>
              <p>CSV with Name,Count columns</p>
              <p>4 Lightning Bolt</p>
              <p>4x Monastery Swiftspear</p>
            </div>
            <textarea
              id="tracker-export"
              value={importText}
              onChange={(e) => {
                setImportText(e.target.value)
                setFileName(null)
              }}
              placeholder="Paste your collection export here..."
              className="w-full h-48 p-3 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)] font-mono text-sm placeholder:text-gray-500"
              style={{
                backgroundColor: 'var(--color-bg-elevated)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
              }}
              disabled={importMutation.isPending}
            />

            {importMutation.isError && (
              <p className="mt-2 text-sm" style={{ color: 'var(--color-error)' }}>
                Failed to import collection. Please check the format and try again.
              </p>
            )}

            {importMutation.isSuccess && (
              <p className="mt-2 text-sm" style={{ color: 'var(--color-success)' }}>
                Collection imported successfully!
              </p>
            )}

            <button
              type="submit"
              disabled={importMutation.isPending || !importText.trim()}
              className="mt-4 w-full py-3 px-4 font-medium rounded-lg hover:opacity-90 transition-opacity focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ backgroundColor: 'var(--color-accent-primary)', color: 'white' }}
            >
              {importMutation.isPending ? 'Importing...' : 'Import Collection'}
            </button>
          </form>
        )}

        {/* Deck Lists Tab */}
        {activeTab === 'decks' && (
          <form onSubmit={handleDecksSubmit}>
            <label className="block text-sm font-medium mb-2" style={{ color: 'var(--color-text-primary)' }}>
              Import from Deck Lists
            </label>
            <p className="text-sm mb-3" style={{ color: 'var(--color-text-secondary)' }}>
              In Arena, open a deck and click the export button (or use Ctrl+C).
              Paste each deck below. We&apos;ll combine them to estimate your collection.
            </p>
            <div
              className="mb-3 p-3 rounded text-xs font-mono"
              style={{ backgroundColor: 'var(--color-bg-elevated)', color: 'var(--color-text-secondary)' }}
            >
              <p className="font-semibold mb-1" style={{ color: 'var(--color-text-primary)' }}>Arena deck format:</p>
              <p>4 Lightning Bolt (LEB) 163</p>
              <p>4 Monastery Swiftspear (BRO) 144</p>
            </div>

            {deckTexts.map((text, index) => (
              <div key={index} className="mb-4">
                <div className="flex items-center justify-between mb-1">
                  <label className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                    Deck {index + 1}
                  </label>
                  {deckTexts.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeDeck(index)}
                      className="text-sm hover:opacity-80 focus:outline-none"
                      style={{ color: 'var(--color-accent-primary)' }}
                    >
                      Remove
                    </button>
                  )}
                </div>
                <textarea
                  value={text}
                  onChange={(e) => updateDeck(index, e.target.value)}
                  placeholder="Paste deck export here..."
                  className="w-full h-32 p-3 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)] font-mono text-sm placeholder:text-gray-500"
                  style={{
                    backgroundColor: 'var(--color-bg-elevated)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-primary)',
                  }}
                  disabled={importMutation.isPending}
                />
              </div>
            ))}

            <button
              type="button"
              onClick={addDeckField}
              className="mb-4 text-sm font-medium hover:opacity-80 focus:outline-none"
              style={{ color: 'var(--color-accent-primary)' }}
            >
              + Add Another Deck
            </button>

            {importMutation.isError && (
              <p className="mt-2 text-sm" style={{ color: 'var(--color-error)' }}>
                Failed to import decks. Please check the format and try again.
              </p>
            )}

            {importMutation.isSuccess && (
              <p className="mt-2 text-sm" style={{ color: 'var(--color-success)' }}>
                Decks imported successfully!
              </p>
            )}

            <button
              type="submit"
              disabled={importMutation.isPending || !deckTexts.some((t) => t.trim())}
              className="mt-2 w-full py-3 px-4 font-medium rounded-lg hover:opacity-90 transition-opacity focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ backgroundColor: 'var(--color-accent-primary)', color: 'white' }}
            >
              {importMutation.isPending ? 'Importing...' : 'Import Decks'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
