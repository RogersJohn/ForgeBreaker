import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type { CollectionResponse, ImportResponse } from '../api/client'

export function useCollection(userId: string) {
  return useQuery({
    queryKey: ['collection', userId],
    queryFn: () => apiClient.getCollection(userId),
    enabled: !!userId,
    retry: false,
  })
}

export function useCollectionStats(userId: string) {
  return useQuery({
    queryKey: ['collectionStats', userId],
    queryFn: () => apiClient.getCollectionStats(userId),
    enabled: !!userId,
    retry: false,
  })
}

interface ImportOptions {
  text: string
  format?: 'auto' | 'simple' | 'csv' | 'arena'
  merge?: boolean
}

export function useImportCollection(userId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ text, format = 'auto', merge = false }: ImportOptions) =>
      apiClient.importCollection(userId, text, format, merge),
    onSuccess: (data: ImportResponse) => {
      // Update cached collection with new data
      const collection: CollectionResponse = {
        user_id: data.user_id,
        total_cards: data.total_cards,
        unique_cards: data.cards_imported,
        cards: data.cards,
      }
      queryClient.setQueryData(['collection', userId], collection)
      // Invalidate stats so they refresh with new data
      queryClient.invalidateQueries({ queryKey: ['collectionStats', userId] })
    },
  })
}
