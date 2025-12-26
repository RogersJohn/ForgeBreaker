import { useState, useRef, useEffect } from 'react'
import type { ChatMessage } from '../api/client'
import { useChat } from '../hooks/useChat'

interface ChatAdvisorProps {
  userId: string
}

const HELP_TOPICS = [
  {
    title: 'Search Your Collection',
    description: 'Find cards you own by name, color, or type.',
    examples: ['Do I have any goblins?', 'Show me my red creatures', 'What shrines do I own?'],
  },
  {
    title: 'Build a Deck',
    description: 'Create a 60-card deck using only cards you own. No wildcards needed.',
    examples: ['Build me a shrine deck', 'Make a goblin tribal deck', 'Create something fun with dragons'],
  },
  {
    title: 'Find Synergies',
    description: 'Discover cards that work well together.',
    examples: ['What pairs well with Sheoldred?', 'Find synergies for my sacrifice deck'],
  },
  {
    title: 'Export to Arena',
    description: 'Get a deck list you can import directly into MTG Arena.',
    examples: ['Export this deck for Arena', 'Give me the import text'],
  },
  {
    title: 'Improve a Deck',
    description: 'Paste a deck list and get upgrade suggestions from your collection.',
    examples: ['Improve this deck: [paste list]', 'What upgrades can I make to this?'],
  },
  {
    title: 'Meta Deck Recommendations',
    description: 'Find competitive decks you can complete with your collection.',
    examples: ['What meta decks can I build?', 'Show me Standard decks I\'m close to'],
  },
  {
    title: 'Deck Completion Details',
    description: 'See exactly what cards you need to finish a specific deck.',
    examples: ['How close am I to Mono Red Aggro?', 'What do I need for Esper Control?'],
  },
  {
    title: 'Browse Meta Decks',
    description: 'See the top competitive decks for any format.',
    examples: ['What are the top decks in Standard?', 'Show me Historic meta decks'],
  },
  {
    title: 'Collection Stats',
    description: 'View your collection overview and statistics.',
    examples: ['How many cards do I have?', 'Show me my collection statistics'],
  },
]

function HelpPanel({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="absolute inset-0 z-10 overflow-y-auto rounded-lg"
      style={{ backgroundColor: 'var(--color-bg-surface)' }}
    >
      <div className="p-6">
        <div className="flex justify-between items-center mb-6">
          <h4 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            What can I ask?
          </h4>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:opacity-80 transition-opacity focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)]"
            style={{ color: 'var(--color-text-secondary)' }}
            aria-label="Close help"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {HELP_TOPICS.map((topic) => (
            <div
              key={topic.title}
              className="p-4 rounded-lg"
              style={{ backgroundColor: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
            >
              <h5 className="font-medium mb-2" style={{ color: 'var(--color-accent-primary)' }}>
                {topic.title}
              </h5>
              <p className="text-sm mb-3" style={{ color: 'var(--color-text-secondary)' }}>
                {topic.description}
              </p>
              <div className="flex flex-wrap gap-1">
                {topic.examples.slice(0, 2).map((example) => (
                  <span
                    key={example}
                    className="inline-block text-xs px-2 py-1 rounded"
                    style={{ backgroundColor: 'var(--color-bg-surface)', color: 'var(--color-text-secondary)' }}
                  >
                    "{example}"
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className="max-w-[80%] rounded-lg px-4 py-3"
        style={{
          backgroundColor: isUser ? 'var(--color-accent-primary)' : 'var(--color-bg-elevated)',
          color: isUser ? 'white' : 'var(--color-text-primary)',
        }}
      >
        <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
      </div>
    </div>
  )
}

export function ChatAdvisor({ userId }: ChatAdvisorProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [showHelp, setShowHelp] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { mutate: sendMessage, isPending } = useChat(userId)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isPending) return

    const userMessage: ChatMessage = { role: 'user', content: input.trim() }
    const updatedMessages = [...messages, userMessage]
    setMessages(updatedMessages)
    setInput('')

    sendMessage(updatedMessages, {
      onSuccess: (response) => {
        setMessages([...updatedMessages, response.message])
      },
      onError: (error) => {
        setMessages([
          ...updatedMessages,
          {
            role: 'assistant',
            content: `Sorry, I encountered an error: ${error.message}`,
          },
        ])
      },
    })
  }

  return (
    <div
      className="rounded-lg shadow-lg flex flex-col h-full relative"
      style={{ backgroundColor: 'var(--color-bg-surface)', border: '1px solid var(--color-border)' }}
    >
      {/* Help Panel Overlay */}
      {showHelp && <HelpPanel onClose={() => setShowHelp(false)} />}

      {/* Header */}
      <div
        className="px-6 py-4 flex justify-between items-start"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <div>
          <h3 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            Deck Advisor
          </h3>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            AI-powered deck building advice based on your collection
          </p>
        </div>
        <button
          onClick={() => setShowHelp(true)}
          className="p-2 rounded-lg hover:opacity-80 transition-opacity focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)]"
          style={{ color: 'var(--color-text-secondary)' }}
          aria-label="Show help"
          title="What can I ask?"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-12">
            <div
              className="w-16 h-16 mx-auto mb-4 rounded-full flex items-center justify-center"
              style={{ backgroundColor: 'var(--color-bg-elevated)' }}
            >
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-accent-primary)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <p className="text-lg mb-2" style={{ color: 'var(--color-text-primary)' }}>
              Start a conversation
            </p>
            <p className="mb-4" style={{ color: 'var(--color-text-secondary)' }}>
              Ask me to help build decks, find synergies, or explore meta options.
            </p>
            <div className="flex flex-wrap justify-center gap-2 mb-6">
              {['Build me a goblin deck', 'What meta decks can I build?', 'Find synergies for Sheoldred'].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setInput(suggestion)}
                  className="px-3 py-2 text-sm rounded-lg hover:opacity-80 transition-opacity"
                  style={{ backgroundColor: 'var(--color-bg-elevated)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }}
                >
                  {suggestion}
                </button>
              ))}
            </div>
            <button
              onClick={() => setShowHelp(true)}
              className="hover:opacity-80 transition-opacity underline focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)] focus:ring-offset-2 rounded"
              style={{ color: 'var(--color-accent-primary)' }}
            >
              See all things I can help with
            </button>
          </div>
        )}
        {messages.map((message, index) => (
          <MessageBubble key={index} message={message} />
        ))}
        {isPending && (
          <div className="flex justify-start">
            <div
              className="rounded-lg px-4 py-3"
              style={{ backgroundColor: 'var(--color-bg-elevated)' }}
            >
              <div className="flex space-x-1">
                <div className="w-2 h-2 rounded-full animate-bounce" style={{ backgroundColor: 'var(--color-accent-primary)' }} />
                <div
                  className="w-2 h-2 rounded-full animate-bounce"
                  style={{ backgroundColor: 'var(--color-accent-primary)', animationDelay: '0.1s' }}
                />
                <div
                  className="w-2 h-2 rounded-full animate-bounce"
                  style={{ backgroundColor: 'var(--color-accent-primary)', animationDelay: '0.2s' }}
                />
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        className="p-4"
        style={{ borderTop: '1px solid var(--color-border)' }}
      >
        <div className="flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about deck building..."
            disabled={isPending}
            className="flex-1 px-4 py-3 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-primary)] disabled:opacity-50 placeholder:text-gray-500"
            style={{
              backgroundColor: 'var(--color-bg-elevated)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-primary)',
            }}
          />
          <button
            type="submit"
            disabled={!input.trim() || isPending}
            className="px-6 py-3 font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2"
            style={{ backgroundColor: 'var(--color-accent-primary)', color: 'white' }}
          >
            Send
          </button>
        </div>
      </form>
    </div>
  )
}
