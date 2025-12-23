import { useMutation } from '@tanstack/react-query'
import type { ChatMessage } from '../api/client'
import { apiClient } from '../api/client'

export function useChat(userId: string) {
  return useMutation({
    mutationFn: (messages: ChatMessage[]) => apiClient.chat(userId, messages),
  })
}
