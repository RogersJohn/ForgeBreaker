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
    <div className="absolute inset-0 bg-white z-10 overflow-y-auto">
      <div className="p-4">
        <div className="flex justify-between items-center mb-4">
          <h4 className="text-lg font-medium text-gray-900">What can I ask?</h4>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="Close help"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="space-y-4">
          {HELP_TOPICS.map((topic) => (
            <div key={topic.title} className="border-b border-gray-100 pb-3 last:border-0">
              <h5 className="font-medium text-gray-800 text-sm">{topic.title}</h5>
              <p className="text-xs text-gray-500 mt-1">{topic.description}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {topic.examples.map((example) => (
                  <span
                    key={example}
                    className="inline-block text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded"
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
        className={`max-w-[80%] rounded-lg px-4 py-2 ${
          isUser
            ? 'bg-indigo-600 text-white'
            : 'bg-gray-100 text-gray-900'
        }`}
      >
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
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
    <div className="bg-white rounded-lg shadow flex flex-col h-96 relative">
      {/* Help Panel Overlay */}
      {showHelp && <HelpPanel onClose={() => setShowHelp(false)} />}

      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 flex justify-between items-start">
        <div>
          <h3 className="text-lg font-medium text-gray-900">Deck Advisor</h3>
          <p className="text-sm text-gray-500">
            Ask for deck building advice based on your collection
          </p>
        </div>
        <button
          onClick={() => setShowHelp(true)}
          className="text-gray-400 hover:text-indigo-600 p-1"
          aria-label="Show help"
          title="What can I ask?"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 text-sm py-8">
            <p>Start a conversation to get deck advice.</p>
            <p className="mt-2">Try asking:</p>
            <ul className="mt-1 space-y-1">
              <li>"Build me a goblin deck"</li>
              <li>"What meta decks can I build?"</li>
              <li>"Find synergies for Sheoldred"</li>
            </ul>
            <button
              onClick={() => setShowHelp(true)}
              className="mt-4 text-indigo-600 hover:text-indigo-800 underline"
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
            <div className="bg-gray-100 rounded-lg px-4 py-2">
              <div className="flex space-x-1">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                <div
                  className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                  style={{ animationDelay: '0.1s' }}
                />
                <div
                  className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                  style={{ animationDelay: '0.2s' }}
                />
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t border-gray-200">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about deck building..."
            disabled={isPending}
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-50 disabled:text-gray-500"
          />
          <button
            type="submit"
            disabled={!input.trim() || isPending}
            className="px-4 py-2 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  )
}
