import { useState } from 'react'

interface LandingPageProps {
  onSetUserId: (userId: string) => void
  isBackendConnected: boolean
}

export function LandingPage({ onSetUserId, isBackendConnected }: LandingPageProps) {
  const [userIdInput, setUserIdInput] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (userIdInput.trim()) {
      onSetUserId(userIdInput.trim())
    }
  }

  return (
    <div className="min-h-[calc(100vh-var(--header-height,120px))] flex flex-col items-center justify-center px-4">
      {/* Hero Section */}
      <div className="max-w-2xl text-center mb-12">
        <h2
          className="text-3xl font-bold mb-4"
          style={{ color: 'var(--color-text-primary)' }}
        >
          Understand Your Deck, Not Just Build It
        </h2>
        <p
          className="text-lg mb-8"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          A thinking tool for MTG Arena players who want to know why their decks
          work—or why they don't.
        </p>
      </div>

      {/* Value Propositions */}
      <div className="grid md:grid-cols-3 gap-6 max-w-4xl mb-12">
        <ValueCard
          title="Surface Assumptions"
          description="See what your deck relies on: mana curve expectations, key card dependencies, interaction timing."
        />
        <ValueCard
          title="Stress Test Ideas"
          description="Intentionally break things. Simulate underperformance to find fragility before your opponent does."
        />
        <ValueCard
          title="Explain Outcomes"
          description="Every result comes with an explanation—and an honest acknowledgment of uncertainty."
        />
      </div>

      {/* Login Form */}
      <div
        className="rounded-lg shadow p-8 w-full max-w-md"
        style={{
          backgroundColor: 'var(--color-bg-surface)',
          border: '1px solid var(--color-border)',
        }}
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <label
            htmlFor="username"
            className="text-sm font-medium"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            Enter a username to get started
          </label>
          <div className="flex gap-3">
            <input
              id="username"
              type="text"
              value={userIdInput}
              onChange={(e) => setUserIdInput(e.target.value)}
              placeholder="Your username"
              className="flex-1 px-4 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#e94560]"
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
              Start
            </button>
          </div>
          {isBackendConnected && (
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              Backend connected
            </p>
          )}
        </form>
      </div>

      {/* Non-claims Section */}
      <div className="mt-12 max-w-2xl text-center">
        <p
          className="text-sm leading-relaxed"
          style={{ color: 'var(--color-text-secondary)', opacity: 0.7 }}
        >
          ForgeBreaker is not a meta aggregation platform, ladder optimizer, or winrate predictor.
          It helps you think about your deck—it doesn't think for you.
          ML-assisted recommendations have known limitations.
        </p>
      </div>
    </div>
  )
}

function ValueCard({ title, description }: { title: string; description: string }) {
  return (
    <div
      className="rounded-lg p-6"
      style={{
        backgroundColor: 'var(--color-bg-surface)',
        border: '1px solid var(--color-border)',
      }}
    >
      <h3
        className="text-lg font-semibold mb-2"
        style={{ color: 'var(--color-text-primary)' }}
      >
        {title}
      </h3>
      <p
        className="text-sm leading-relaxed"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        {description}
      </p>
    </div>
  )
}
