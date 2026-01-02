import { useState } from 'react'
import type { DeckResponse } from '../api/client'
import { apiClient } from '../api/client'

interface LandingPageProps {
  onStart: () => void
  onTrySampleDeck: (deck: DeckResponse) => void
  isBackendConnected: boolean
}

export function LandingPage({ onStart, onTrySampleDeck, isBackendConnected }: LandingPageProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleTrySampleDeck = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const deck = await apiClient.createSampleDeck()
      onTrySampleDeck(deck)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sample deck')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-var(--header-height,120px))] flex flex-col items-center justify-center px-4">
      {/* Hero - Lead with the question */}
      <div className="max-w-2xl text-center mb-10">
        <h2
          className="text-3xl font-bold mb-6"
          style={{ color: 'var(--color-text-primary)' }}
        >
          Why does my deck feel inconsistent?
        </h2>
        <p
          className="text-lg mb-4"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          That's the question ForgeBreaker helps you answer.
        </p>
      </div>

      {/* The Questions ForgeBreaker Answers */}
      <div className="max-w-2xl mb-10">
        <div
          className="rounded-lg p-6"
          style={{
            backgroundColor: 'var(--color-bg-surface)',
            border: '1px solid var(--color-border)',
          }}
        >
          <p
            className="text-sm font-medium mb-4"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            ForgeBreaker helps you answer:
          </p>
          <ul className="space-y-3">
            <QuestionItem>Which card is my deck secretly relying on?</QuestionItem>
            <QuestionItem>What happens when this assumption fails?</QuestionItem>
            <QuestionItem>What part of my deck breaks first?</QuestionItem>
          </ul>
        </div>
      </div>

      {/* Core Concepts */}
      <div className="grid md:grid-cols-3 gap-4 max-w-4xl mb-10">
        <ConceptCard
          concept="Assumptions"
          explanation="Every deck relies on things being true: land drops, key cards connecting, removal arriving on time. ForgeBreaker makes these visible."
        />
        <ConceptCard
          concept="Fragility"
          explanation="How much does your deck suffer when one thing goes wrong? Find out which assumptions your deck can't afford to lose."
        />
        <ConceptCard
          concept="Breaking Point"
          explanation="Stress your deck's assumptions intentionally. Discover what fails first—before your opponent finds it for you."
        />
      </div>

      {/* Start Buttons */}
      <div
        className="rounded-lg shadow p-8 w-full max-w-md mb-10"
        style={{
          backgroundColor: 'var(--color-bg-surface)',
          border: '1px solid var(--color-border)',
        }}
      >
        <div className="flex flex-col gap-4">
          <button
            onClick={onStart}
            disabled={!isBackendConnected}
            className="w-full px-6 py-3 font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
            style={{ backgroundColor: 'var(--color-accent-primary)', color: 'white' }}
          >
            Get Started
          </button>
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px" style={{ backgroundColor: 'var(--color-border)' }} />
            <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>or</span>
            <div className="flex-1 h-px" style={{ backgroundColor: 'var(--color-border)' }} />
          </div>
          <button
            onClick={handleTrySampleDeck}
            disabled={!isBackendConnected || isLoading}
            className="w-full px-6 py-3 font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
            style={{
              backgroundColor: 'var(--color-bg-elevated)',
              color: 'var(--color-text-primary)',
              border: '1px solid var(--color-border)',
            }}
          >
            {isLoading ? 'Loading...' : 'Try with Sample Deck'}
          </button>
          {error && (
            <p className="text-xs text-center" style={{ color: 'var(--color-accent-primary)' }}>
              {error}
            </p>
          )}
          <p className="text-xs text-center" style={{ color: 'var(--color-text-secondary)' }}>
            No MTG Arena account needed—explore a Mono-Red Aggro deck first.
          </p>
          {isBackendConnected && (
            <p className="text-xs text-center" style={{ color: 'var(--color-text-secondary)' }}>
              Backend connected
            </p>
          )}
        </div>
      </div>

      {/* What ForgeBreaker Does NOT Do */}
      <div className="max-w-2xl">
        <div
          className="rounded-lg p-5"
          style={{
            backgroundColor: 'var(--color-bg-elevated)',
            border: '1px solid var(--color-border)',
          }}
        >
          <p
            className="text-xs font-medium mb-3"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            What ForgeBreaker does NOT do:
          </p>
          <ul
            className="text-xs space-y-1"
            style={{ color: 'var(--color-text-secondary)', opacity: 0.8 }}
          >
            <li>Does not track your ladder performance or match history</li>
            <li>Does not predict your personal winrate</li>
            <li>Does not tell you which deck is "statistically best"</li>
            <li>Does not replace playtesting—it helps you know what to watch for</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

function QuestionItem({ children }: { children: React.ReactNode }) {
  return (
    <li
      className="text-base font-medium"
      style={{ color: 'var(--color-text-primary)' }}
    >
      "{children}"
    </li>
  )
}

function ConceptCard({ concept, explanation }: { concept: string; explanation: string }) {
  return (
    <div
      className="rounded-lg p-5"
      style={{
        backgroundColor: 'var(--color-bg-elevated)',
        border: '1px solid var(--color-border)',
      }}
    >
      <h3
        className="text-sm font-bold mb-2"
        style={{ color: 'var(--color-accent-primary)' }}
      >
        {concept}
      </h3>
      <p
        className="text-sm leading-relaxed"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        {explanation}
      </p>
    </div>
  )
}
