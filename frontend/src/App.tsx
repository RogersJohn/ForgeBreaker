import { useQuery } from '@tanstack/react-query'
import { apiClient } from './api/client'

function App() {
  const { data: health, isLoading, error } = useQuery({
    queryKey: ['health'],
    queryFn: () => apiClient.checkHealth(),
    retry: false,
  })

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-indigo-600 text-white shadow">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <h1 className="text-3xl font-bold">ForgeBreaker</h1>
          <p className="text-indigo-200 mt-1">MTG Arena Deck Advisor</p>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Backend Status
          </h2>
          {isLoading && (
            <p className="text-gray-500">Checking backend connection...</p>
          )}
          {error && (
            <p className="text-red-600">
              Backend unavailable. Make sure the server is running.
            </p>
          )}
          {health && (
            <p className="text-green-600">
              Backend connected: {health.status}
            </p>
          )}
        </div>

        <div className="mt-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900">
              Import Collection
            </h3>
            <p className="text-gray-500 mt-2">
              Import your MTG Arena collection to get personalized deck recommendations.
            </p>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900">
              Browse Decks
            </h3>
            <p className="text-gray-500 mt-2">
              Explore meta decks and see which ones you can build.
            </p>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900">
              Chat Advisor
            </h3>
            <p className="text-gray-500 mt-2">
              Get AI-powered advice on deck building and card choices.
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
