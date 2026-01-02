import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { StressScenarioRequest } from '../api/client'
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

export function useBreakingPoint(
  userId: string,
  format: string,
  deckName: string
) {
  return useQuery({
    queryKey: ['breaking-point', userId, format, deckName],
    queryFn: () => apiClient.getBreakingPoint(userId, format, deckName),
    enabled: !!userId && !!format && !!deckName,
  })
}

export function useStressDeck(
  userId: string,
  format: string,
  deckName: string
) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (scenario: StressScenarioRequest) =>
      apiClient.stressDeck(userId, format, deckName, scenario),
    onSuccess: () => {
      // Invalidate related queries if needed
      queryClient.invalidateQueries({
        queryKey: ['stress', userId, format, deckName],
      })
    },
  })
}
