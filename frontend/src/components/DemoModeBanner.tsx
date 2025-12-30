/**
 * Demo mode banner component.
 *
 * Displays when user is viewing sample collection data (not their own).
 * Must be:
 * - Visible without scrolling
 * - Plain, non-marketing language
 * - Disappears immediately when user uploads their own CSV
 */

interface DemoModeBannerProps {
  /** Whether to show the banner (true when collection_source === 'DEMO') */
  isDemo: boolean
}

export function DemoModeBanner({ isDemo }: DemoModeBannerProps) {
  if (!isDemo) {
    return null
  }

  return (
    <div
      className="rounded-lg p-4 mb-4"
      style={{
        backgroundColor: 'var(--color-bg-elevated)',
        border: '1px solid var(--color-border)',
      }}
    >
      <p
        className="text-sm font-medium mb-1"
        style={{ color: 'var(--color-text-primary)' }}
      >
        Demo mode: using a sample MTG Arena collection.
      </p>
      <p
        className="text-sm"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        Upload your own collection CSV to replace it.
      </p>
    </div>
  )
}
