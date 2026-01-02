/**
 * API client for ForgeBreaker backend.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Collection source type for demo/user distinction
export type CollectionSource = 'DEMO' | 'USER'

export interface DeckResponse {
  name: string
  archetype: string
  format: string
  cards: Record<string, number>
  sideboard: Record<string, number>
  win_rate: number | null
  meta_share: number | null
  source_url: string | null
}

export interface DeckListResponse {
  format: string
  decks: DeckResponse[]
  count: number
}

export interface CollectionResponse {
  user_id: string
  total_cards: number
  unique_cards: number
  cards?: Record<string, number>
  collection_source: CollectionSource
}

export interface ImportResponse {
  user_id: string
  cards_imported: number
  total_cards: number
  cards: Record<string, number>
  collection_source: CollectionSource
}

export interface CollectionStatsResponse {
  user_id: string
  total_cards: number
  unique_cards: number
  by_rarity: Record<string, number>
  by_color: Record<string, number>
  by_type: Record<string, number>
  collection_source: CollectionSource
}

export interface DistanceResponse {
  deck_name: string
  archetype: string
  completion_percentage: number
  owned_cards: number
  missing_cards: number
  is_complete: boolean
  wildcard_cost: {
    common: number
    uncommon: number
    rare: number
    mythic: number
    total: number
  }
  missing_card_list: Array<{
    name: string
    quantity: number
    rarity: string
  }>
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatResponse {
  message: ChatMessage
  tool_calls: Array<{ name: string; input: Record<string, unknown> }>
}

/**
 * A player belief about what a deck needs to function.
 *
 * These are hypotheses for players to examine, not system predictions.
 * The observed_value is a fact about the decklist; typical_range is
 * what convention suggests for the archetype (not truth).
 */
export interface DeckAssumption {
  name: string
  category: string
  description: string
  observed_value: unknown  // What the decklist shows (fact)
  typical_range: [number, number]  // Convention for archetype (not prescription)
  health: 'healthy' | 'warning' | 'critical'
  explanation: string
  adjustable: boolean
}

export interface AssumptionSetResponse {
  deck_name: string
  archetype: string
  assumptions: DeckAssumption[]
  overall_fragility: number
  fragility_explanation: string
}

export type StressType = 'underperform' | 'missing' | 'delayed' | 'hostile_meta'

export interface StressScenarioRequest {
  stress_type: StressType
  target: string
  intensity?: number
}

/**
 * How a belief changes under a hypothetical stress scenario.
 */
export interface StressedAssumption {
  name: string
  original_value: unknown
  stressed_value: unknown
  original_health: string
  stressed_health: string
  change_explanation: string
  belief_violated: boolean
  violation_reason: string
}

/**
 * Result of exploring a stress scenario with a deck.
 *
 * A breaking point occurs when a specific belief can no longer be held,
 * NOT when a numeric threshold is crossed.
 */
export interface StressResultResponse {
  deck_name: string
  stress_type: string
  target: string
  intensity: number
  original_fragility: number
  stressed_fragility: number
  fragility_change: number
  affected_assumptions: StressedAssumption[]
  // Semantic fields
  assumption_violated: boolean
  violated_belief: string
  violation_explanation: string
  exploration_summary: string
  considerations: string[]
  // Backwards compatibility
  breaking_point: boolean  // Deprecated: use assumption_violated
  explanation: string  // Deprecated: use exploration_summary
  recommendations: string[]  // Deprecated: use considerations
}

/**
 * Analysis of which belief fails first under stress.
 *
 * This identifies the most vulnerable assumption, not a prediction of failure.
 */
export interface BreakingPointResponse {
  deck_name: string
  // Semantic fields
  most_vulnerable_belief: string
  stress_threshold: number
  failing_scenario: StressScenarioRequest | null
  exploration_insight: string
  // Backwards compatibility
  weakest_assumption: string  // Deprecated: use most_vulnerable_belief
  breaking_intensity: number  // Deprecated: use stress_threshold
  resilience_score: number  // Deprecated: removed concept
  breaking_scenario: StressScenarioRequest | null  // Deprecated: use failing_scenario
  explanation: string  // Deprecated: use exploration_insight
}

class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl
  }

  private async request<T>(
    path: string,
    options: RequestInit = {}
  ): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || `API error: ${response.status}`)
    }

    return response.json()
  }

  // Health
  async checkHealth(): Promise<{ status: string }> {
    return this.request('/health')
  }

  // Decks
  async getDecks(format: string, limit = 50): Promise<DeckListResponse> {
    return this.request(`/decks/${format}?limit=${limit}`)
  }

  async getDeck(format: string, deckName: string): Promise<DeckResponse> {
    return this.request(`/decks/${format}/${encodeURIComponent(deckName)}`)
  }

  // Collection
  async getCollection(userId: string): Promise<CollectionResponse> {
    return this.request(`/collection/${userId}`)
  }

  async importCollection(
    userId: string,
    text: string,
    format: 'auto' | 'simple' | 'csv' | 'arena' = 'auto',
    merge = false
  ): Promise<ImportResponse> {
    return this.request(`/collection/${userId}/import`, {
      method: 'POST',
      body: JSON.stringify({ text, format, merge }),
    })
  }

  async getCollectionStats(userId: string): Promise<CollectionStatsResponse> {
    return this.request(`/collection/${userId}/stats`)
  }

  // Distance
  async getDeckDistance(
    userId: string,
    format: string,
    deckName: string
  ): Promise<DistanceResponse> {
    return this.request(
      `/distance/${userId}/${format}/${encodeURIComponent(deckName)}`
    )
  }

  // Chat
  async chat(
    userId: string,
    messages: ChatMessage[]
  ): Promise<ChatResponse> {
    return this.request('/chat/', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, messages }),
    })
  }

  // Assumptions
  async getDeckAssumptions(
    userId: string,
    format: string,
    deckName: string
  ): Promise<AssumptionSetResponse> {
    return this.request(
      `/assumptions/${userId}/${format}/${encodeURIComponent(deckName)}`
    )
  }

  // Stress Testing
  async stressDeck(
    userId: string,
    format: string,
    deckName: string,
    scenario: StressScenarioRequest
  ): Promise<StressResultResponse> {
    return this.request(
      `/stress/${userId}/${format}/${encodeURIComponent(deckName)}`,
      {
        method: 'POST',
        body: JSON.stringify(scenario),
      }
    )
  }

  async getBreakingPoint(
    userId: string,
    format: string,
    deckName: string
  ): Promise<BreakingPointResponse> {
    return this.request(
      `/stress/breaking-point/${userId}/${format}/${encodeURIComponent(deckName)}`
    )
  }

  // Sample deck
  async createSampleDeck(): Promise<DeckResponse> {
    return this.request('/decks/sample', {
      method: 'POST',
    })
  }
}

export const apiClient = new ApiClient()
