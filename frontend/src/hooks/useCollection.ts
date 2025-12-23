import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type { CollectionResponse } from '../api/client'

export function useCollection(userId: string) {
  return useQuery({
    queryKey: ['collection', userId],
    queryFn: () => apiClient.getCollection(userId),
    enabled: !!userId,
    retry: false,
  })
}

export function useImportCollection(userId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (arenaExport: string) =>
      apiClient.importCollection(userId, arenaExport),
    onSuccess: (data: CollectionResponse) => {
      queryClient.setQueryData(['collection', userId], data)
    },
  })
}
