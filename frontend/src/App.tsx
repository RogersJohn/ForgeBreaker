import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from './api/client'
import { CollectionImporter } from './components/CollectionImporter'

function App() {
  const [userId, setUserId] = useState(() => {
    return localStorage.getItem('forgebreaker_user_id') || ''
  })
  const [userIdInput, setUserIdInput] = useState(userId)

  const { data: health, isLoading, error } = useQuery({
    queryKey: ['health'],
    queryFn: () => apiClient.checkHealth(),
    retry: false,
  })

  const handleSetUserId = (e: React.FormEvent) => {
    e.preventDefault()
    if (userIdInput.trim()) {
      setUserId(userIdInput.trim())
      localStorage.setItem('forgebreaker_user_id', userIdInput.trim())
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-indigo-600 text-white shadow">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <h1 className="text-3xl font-bold">ForgeBreaker</h1>
          <p className="text-indigo-200 mt-1">MTG Arena Deck Advisor</p>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Backend Status */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
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

        {/* User ID Setup */}
        {!userId ? (
          <div className="bg-white rounded-lg shadow p-6 mb-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              Get Started
            </h2>
            <p className="text-gray-500 mb-4">
              Enter a username to start tracking your collection.
            </p>
            <form onSubmit={handleSetUserId} className="flex gap-4">
              <input
                type="text"
                value={userIdInput}
                onChange={(e) => setUserIdInput(e.target.value)}
                placeholder="Enter your username"
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              />
              <button
                type="submit"
                disabled={!userIdInput.trim()}
                className="px-6 py-2 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50"
              >
                Continue
              </button>
            </form>
          </div>
        ) : (
          <>
            {/* User Info Bar */}
            <div className="bg-white rounded-lg shadow p-4 mb-6 flex items-center justify-between">
              <p className="text-gray-700">
                Logged in as: <span className="font-medium">{userId}</span>
              </p>
              <button
                onClick={() => {
                  setUserId('')
                  setUserIdInput('')
                  localStorage.removeItem('forgebreaker_user_id')
                }}
                className="inline-flex items-center rounded-md border border-gray-300 bg-white px-3 py-1 text-sm font-medium text-gray-600 shadow-sm hover:bg-gray-50 hover:text-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
              >
                Switch User
              </button>
            </div>

            {/* Main Content */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <CollectionImporter userId={userId} />

              <div className="space-y-6">
                <div className="bg-white rounded-lg shadow p-6">
                  <h3 className="text-lg font-medium text-gray-900">
                    Browse Decks
                  </h3>
                  <p className="text-gray-500 mt-2">
                    Explore meta decks and see which ones you can build.
                  </p>
                  <p className="text-sm text-gray-400 mt-4">Coming soon...</p>
                </div>

                <div className="bg-white rounded-lg shadow p-6">
                  <h3 className="text-lg font-medium text-gray-900">
                    Chat Advisor
                  </h3>
                  <p className="text-gray-500 mt-2">
                    Get AI-powered advice on deck building and card choices.
                  </p>
                  <p className="text-sm text-gray-400 mt-4">Coming soon...</p>
                </div>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  )
}

export default App
