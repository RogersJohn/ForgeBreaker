import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { DeckResponse } from './api/client'
import { apiClient } from './api/client'
import { ChatAdvisor } from './components/ChatAdvisor'
import { CollectionImporter } from './components/CollectionImporter'
import { DeckBrowser } from './components/DeckBrowser'
import { DeckDetail } from './components/DeckDetail'
import { LandingPage } from './components/LandingPage'
import { TabNav, type TabId } from './components/TabNav'

// Generate a stable UUID for this browser session
function getOrCreateUserId(): string {
  const stored = localStorage.getItem('forgebreaker_user_id')
  if (stored) return stored
  const newId = crypto.randomUUID()
  localStorage.setItem('forgebreaker_user_id', newId)
  return newId
}

function App() {
  // User ID is auto-generated, not user-supplied
  const [userId] = useState(() => getOrCreateUserId())
  const [hasStarted, setHasStarted] = useState(() => {
    return localStorage.getItem('forgebreaker_started') === 'true'
  })
  const [selectedDeck, setSelectedDeck] = useState<DeckResponse | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>('chat')

  const handleTabChange = (tab: TabId) => {
    setActiveTab(tab)
    // Clear deck selection when leaving meta tab
    if (tab !== 'meta') {
      setSelectedDeck(null)
    }
  }

  const { data: health, isLoading, error } = useQuery({
    queryKey: ['health'],
    queryFn: () => apiClient.checkHealth(),
    retry: false,
  })

  const handleStart = () => {
    setHasStarted(true)
    localStorage.setItem('forgebreaker_started', 'true')
  }

  const handleReset = () => {
    setHasStarted(false)
    localStorage.removeItem('forgebreaker_started')
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
              <p style={{ color: 'var(--color-text-secondary)' }}>Understand your deck, not just build it</p>
            </div>

            {hasStarted && (
              <div className="flex items-center gap-4">
                <TabNav activeTab={activeTab} onTabChange={handleTabChange} />
                <button
                  onClick={handleReset}
                  className="text-sm px-3 py-1.5 rounded hover:opacity-80 transition-opacity"
                  style={{
                    backgroundColor: 'var(--color-bg-elevated)',
                    color: 'var(--color-text-secondary)',
                    border: '1px solid var(--color-border)',
                  }}
                >
                  Reset
                </button>
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

        {/* Landing Page or Main App */}
        {!hasStarted ? (
          <LandingPage
            onStart={handleStart}
            isBackendConnected={!!health}
          />
        ) : (
          <div className="h-[calc(100vh-120px)]">
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
