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

      {/* Login Form */}
      <div
        className="rounded-lg shadow p-8 w-full max-w-md mb-10"
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
            Enter a username to start exploring
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
