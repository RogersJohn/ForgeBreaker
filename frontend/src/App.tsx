import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { DeckResponse } from './api/client'
import { apiClient } from './api/client'
import { ChatAdvisor } from './components/ChatAdvisor'
import { CollectionImporter } from './components/CollectionImporter'
import { DeckBrowser } from './components/DeckBrowser'
import { DeckDetail } from './components/DeckDetail'
import { TabNav, type TabId } from './components/TabNav'

function App() {
  const [userId, setUserId] = useState(() => {
    return localStorage.getItem('forgebreaker_user_id') || ''
  })
  const [userIdInput, setUserIdInput] = useState(userId)
  const [selectedDeck, setSelectedDeck] = useState<DeckResponse | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>('chat')

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
    <div className="min-h-screen" style={{ backgroundColor: 'var(--color-bg-primary)' }}>
      <header
        className="shadow-lg"
        style={{ backgroundColor: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border)' }}
      >
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1
                className="text-2xl font-bold"
                style={{ color: 'var(--color-accent-primary)' }}
              >
                ForgeBreaker
              </h1>
              <p style={{ color: 'var(--color-text-secondary)' }}>MTG Arena Deck Advisor</p>
            </div>

            {userId && (
              <div className="flex items-center gap-4">
                <TabNav activeTab={activeTab} onTabChange={setActiveTab} />
                <div
                  className="flex items-center gap-3 px-4 py-2 rounded-lg"
                  style={{ backgroundColor: 'var(--color-bg-elevated)' }}
                >
                  <span style={{ color: 'var(--color-text-secondary)' }}>{userId}</span>
                  <button
                    onClick={() => {
                      setUserId('')
                      setUserIdInput('')
                      localStorage.removeItem('forgebreaker_user_id')
                    }}
                    className="text-sm px-2 py-1 rounded hover:opacity-80 transition-opacity"
                    style={{ color: 'var(--color-accent-primary)' }}
                  >
                    Logout
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6">
        {/* Backend Status - only show if there's an error */}
        {(isLoading || error) && (
          <div
            className="rounded-lg shadow p-4 mb-6"
            style={{ backgroundColor: 'var(--color-bg-surface)', border: '1px solid var(--color-border)' }}
          >
            {isLoading && (
              <p style={{ color: 'var(--color-text-secondary)' }}>Checking backend connection...</p>
            )}
            {error && (
              <p style={{ color: 'var(--color-accent-primary)' }}>
                Backend unavailable. Make sure the server is running.
              </p>
            )}
          </div>
        )}

        {/* User ID Setup */}
        {!userId ? (
          <div
            className="rounded-lg shadow p-8 max-w-md mx-auto mt-20"
            style={{ backgroundColor: 'var(--color-bg-surface)', border: '1px solid var(--color-border)' }}
          >
            <h2
              className="text-xl font-semibold mb-4"
              style={{ color: 'var(--color-text-primary)' }}
            >
              Get Started
            </h2>
            <p className="mb-6" style={{ color: 'var(--color-text-secondary)' }}>
              Enter a username to start tracking your collection.
            </p>
            <form onSubmit={handleSetUserId} className="flex gap-3">
              <input
                type="text"
                value={userIdInput}
                onChange={(e) => setUserIdInput(e.target.value)}
                placeholder="Enter your username"
                className="flex-1 px-4 py-2 rounded-lg focus:outline-none focus:ring-2"
                style={{
                  backgroundColor: 'var(--color-bg-elevated)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-primary)',
                }}
              />
              <button
                type="submit"
                disabled={!userIdInput.trim()}
                className="px-6 py-2 font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
                style={{ backgroundColor: 'var(--color-accent-primary)', color: 'white' }}
              >
                Continue
              </button>
            </form>
            {health && (
              <p className="mt-4 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                Backend connected
              </p>
            )}
          </div>
        ) : (
          <div className="h-[calc(100vh-140px)]">
            {/* Chat Tab */}
            {activeTab === 'chat' && (
              <ChatAdvisor userId={userId} />
            )}

            {/* Collection Tab */}
            {activeTab === 'collection' && (
              <CollectionImporter userId={userId} />
            )}

            {/* Meta Decks Tab */}
            {activeTab === 'meta' && (
              <>
                {selectedDeck ? (
                  <DeckDetail
                    deck={selectedDeck}
                    userId={userId}
                    onClose={() => setSelectedDeck(null)}
                  />
                ) : (
                  <DeckBrowser
                    userId={userId}
                    onSelectDeck={setSelectedDeck}
                  />
                )}
              </>
            )}
          </div>
        )}
      </main>
    </div>
  )
}

export default App
