import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'

export function useDecks(format: string, limit = 50) {
  return useQuery({
    queryKey: ['decks', format, limit],
    queryFn: () => apiClient.getDecks(format, limit),
    enabled: !!format,
  })
}

export function useDeckDistance(
  userId: string,
  format: string,
  deckName: string
) {
  return useQuery({
    queryKey: ['distance', userId, format, deckName],
    queryFn: () => apiClient.getDeckDistance(userId, format, deckName),
    enabled: !!userId && !!format && !!deckName,
  })
}

export function useDeckAssumptions(
  userId: string,
  format: string,
  deckName: string
) {
  return useQuery({
    queryKey: ['assumptions', userId, format, deckName],
    queryFn: () => apiClient.getDeckAssumptions(userId, format, deckName),
    enabled: !!userId && !!format && !!deckName,
  })
}
