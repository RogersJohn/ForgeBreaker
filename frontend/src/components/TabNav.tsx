export type TabId = 'chat' | 'collection' | 'meta'

interface Tab {
  id: TabId
  label: string
}

const TABS: Tab[] = [
  { id: 'chat', label: 'Chat' },
  { id: 'collection', label: 'Collection' },
  { id: 'meta', label: 'Meta Decks' },
]

interface TabNavProps {
  activeTab: TabId
  onTabChange: (tab: TabId) => void
}

export function TabNav({ activeTab, onTabChange }: TabNavProps) {
  return (
    <nav
      role="tablist"
      aria-label="Main navigation"
      className="flex gap-1 p-1 rounded-lg"
      style={{ backgroundColor: 'var(--color-bg-surface)' }}
    >
      {TABS.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={activeTab === tab.id}
          aria-controls={`${tab.id}-panel`}
          onClick={() => onTabChange(tab.id)}
          className={`
            px-6 py-2 rounded-md font-medium transition-colors
            ${activeTab === tab.id
              ? 'text-white'
              : 'text-gray-400 hover:text-gray-200'
            }
          `}
          style={{
            backgroundColor: activeTab === tab.id ? 'var(--color-accent-primary)' : 'transparent',
          }}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  )
}
