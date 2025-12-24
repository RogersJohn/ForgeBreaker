import { useState, useRef } from 'react'
import { useCollection, useImportCollection } from '../hooks/useCollection'

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
  const { data: collection, isLoading, error } = useCollection(userId)
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
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-semibold text-gray-900 mb-4">
        Your Collection
      </h2>

      {isLoading && (
        <p className="text-gray-500">Loading collection...</p>
      )}

      {error && !collection && (
        <p className="text-gray-500 mb-4">No collection imported yet.</p>
      )}

      {collection && (
        <div className="mb-6 p-4 bg-gray-50 rounded-lg">
          <h3 className="text-lg font-medium text-gray-900 mb-2">
            Collection Stats
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-gray-500">Total Cards</p>
              <p className="text-2xl font-bold text-indigo-600">
                {collection.total_cards.toLocaleString()}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Unique Cards</p>
              <p className="text-2xl font-bold text-indigo-600">
                {collection.unique_cards.toLocaleString()}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="border-b border-gray-200 mb-4">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('tracker')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'tracker'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            From Tracker Export
          </button>
          <button
            onClick={() => setActiveTab('decks')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'decks'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
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
            className="block text-sm font-medium text-gray-700 mb-2"
          >
            Import from Tracker or Collection Manager
          </label>
          <p className="text-sm text-gray-500 mb-3">
            Upload a CSV file or paste your collection export below.
          </p>

          {/* File Upload */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Upload CSV File
            </label>
            <div className="flex items-center gap-3">
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.txt"
                onChange={handleFileChange}
                className="block w-full text-sm text-gray-500
                  file:mr-4 file:py-2 file:px-4
                  file:rounded-lg file:border-0
                  file:text-sm file:font-medium
                  file:bg-indigo-50 file:text-indigo-700
                  hover:file:bg-indigo-100
                  disabled:opacity-50"
                disabled={importMutation.isPending}
              />
            </div>
            {fileName && (
              <p className="mt-1 text-sm text-green-600">
                Loaded: {fileName}
              </p>
            )}
          </div>

          <div className="relative my-4">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-300" />
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="bg-white px-2 text-gray-500">or paste text</span>
            </div>
          </div>

          <div className="mb-3 p-3 bg-gray-50 rounded text-xs text-gray-600 font-mono">
            <p className="font-semibold mb-1">Accepted formats:</p>
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
            className="w-full h-48 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 font-mono text-sm"
            disabled={importMutation.isPending}
          />

          {importMutation.isError && (
            <p className="mt-2 text-sm text-red-600">
              Failed to import collection. Please check the format and try again.
            </p>
          )}

          {importMutation.isSuccess && (
            <p className="mt-2 text-sm text-green-600">
              Collection imported successfully!
            </p>
          )}

          <button
            type="submit"
            disabled={importMutation.isPending || !importText.trim()}
            className="mt-4 w-full py-2 px-4 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {importMutation.isPending ? 'Importing...' : 'Import Collection'}
          </button>
        </form>
      )}

      {/* Deck Lists Tab */}
      {activeTab === 'decks' && (
        <form onSubmit={handleDecksSubmit}>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Import from Deck Lists
          </label>
          <p className="text-sm text-gray-500 mb-3">
            In Arena, open a deck and click the export button (or use Ctrl+C).
            Paste each deck below. We&apos;ll combine them to estimate your
            collection.
          </p>
          <div className="mb-3 p-3 bg-gray-50 rounded text-xs text-gray-600 font-mono">
            <p className="font-semibold mb-1">Arena deck format:</p>
            <p>4 Lightning Bolt (LEB) 163</p>
            <p>4 Monastery Swiftspear (BRO) 144</p>
          </div>

          {deckTexts.map((text, index) => (
            <div key={index} className="mb-4">
              <div className="flex items-center justify-between mb-1">
                <label className="text-sm font-medium text-gray-600">
                  Deck {index + 1}
                </label>
                {deckTexts.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeDeck(index)}
                    className="text-sm text-red-600 hover:text-red-500"
                  >
                    Remove
                  </button>
                )}
              </div>
              <textarea
                value={text}
                onChange={(e) => updateDeck(index, e.target.value)}
                placeholder="Paste deck export here..."
                className="w-full h-32 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 font-mono text-sm"
                disabled={importMutation.isPending}
              />
            </div>
          ))}

          <button
            type="button"
            onClick={addDeckField}
            className="mb-4 text-sm text-indigo-600 hover:text-indigo-500 font-medium"
          >
            + Add Another Deck
          </button>

          {importMutation.isError && (
            <p className="mt-2 text-sm text-red-600">
              Failed to import decks. Please check the format and try again.
            </p>
          )}

          {importMutation.isSuccess && (
            <p className="mt-2 text-sm text-green-600">
              Decks imported successfully!
            </p>
          )}

          <button
            type="submit"
            disabled={
              importMutation.isPending ||
              !deckTexts.some((t) => t.trim())
            }
            className="mt-2 w-full py-2 px-4 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {importMutation.isPending ? 'Importing...' : 'Import Decks'}
          </button>
        </form>
      )}
    </div>
  )
}
