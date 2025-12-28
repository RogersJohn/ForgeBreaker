/**
 * API client for ForgeBreaker backend.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

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
}

export interface ImportResponse {
  user_id: string
  cards_imported: number
  total_cards: number
  cards: Record<string, number>
}

export interface CollectionStatsResponse {
  user_id: string
  total_cards: number
  unique_cards: number
  by_rarity: Record<string, number>
  by_color: Record<string, number>
  by_type: Record<string, number>
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

export interface DeckAssumption {
  name: string
  category: string
  description: string
  current_value: unknown
  expected_range: [number, number]
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
}

export const apiClient = new ApiClient()
