import { useState } from 'react'
import { useCollection, useImportCollection } from '../hooks/useCollection'

interface CollectionImporterProps {
  userId: string
}

export function CollectionImporter({ userId }: CollectionImporterProps) {
  const [arenaExport, setArenaExport] = useState('')
  const { data: collection, isLoading, error } = useCollection(userId)
  const importMutation = useImportCollection(userId)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (arenaExport.trim()) {
      importMutation.mutate(arenaExport, {
        onSuccess: () => {
          setArenaExport('')
        },
      })
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

      <form onSubmit={handleSubmit}>
        <label
          htmlFor="arena-export"
          className="block text-sm font-medium text-gray-700 mb-2"
        >
          Import from MTG Arena
        </label>
        <p className="text-sm text-gray-500 mb-3">
          In MTG Arena, go to Collection, click Export, and paste the text below.
        </p>
        <textarea
          id="arena-export"
          value={arenaExport}
          onChange={(e) => setArenaExport(e.target.value)}
          placeholder="Paste your Arena collection export here..."
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
          disabled={importMutation.isPending || !arenaExport.trim()}
          className="mt-4 w-full py-2 px-4 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {importMutation.isPending ? 'Importing...' : 'Import Collection'}
        </button>
      </form>
    </div>
  )
}
