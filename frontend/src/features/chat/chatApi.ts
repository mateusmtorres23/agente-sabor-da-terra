
import { apiRequest } from '../../lib/api-client'

import type {
  ChatMessage,
  ChatSession,
  ChatSessionDetail,
  CreateMessagePayload,
} from './types'

export function listChatSessions(signal?: AbortSignal): Promise<ChatSession[]> {
  return apiRequest<ChatSession[]>('/chat/sessions', { signal })
}

export function createChatSession(): Promise<ChatSession> {
  return apiRequest<ChatSession>('/chat/sessions', {
    method: 'POST',
  })
}

export function getChatSession(
  sessionId: string,
  signal?: AbortSignal,
): Promise<ChatSessionDetail> {
  return apiRequest<ChatSessionDetail>(
    `/chat/sessions/${sessionId}`,
    { signal },
  )
}

export function sendChatMessage(
  sessionId: string,
  payload: CreateMessagePayload,
): Promise<ChatMessage> {
  return apiRequest<ChatMessage>(
    `/chat/sessions/${sessionId}/messages`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
}
import type { LotDraft } from './types'

export interface LotDraftUpdatePayload {
  order_id?: string | null
  item_id?: string | null
  producer_id?: string | null
  quantity?: string | null
  unit?: string | null
  delivery_date?: string | null
}

export function updateLotDraft(
  draftId: string,
  payload: LotDraftUpdatePayload,
): Promise<LotDraft> {
  return apiRequest<LotDraft>(`/chat/lot-drafts/${encodeURIComponent(draftId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function setLotDraftAvailability(
  draftId: string,
  confirmed = true,
  expectedRevision?: number,
): Promise<LotDraft> {
  return apiRequest<LotDraft>(
    `/chat/lot-drafts/${encodeURIComponent(draftId)}/availability`,
    {
      method: 'POST',
      body: JSON.stringify({
        confirmed,
        ...(expectedRevision !== undefined
          ? { expected_revision: expectedRevision }
          : {}),
      }),
    },
  )
}

export function confirmLotDraft(
  draftId: string,
  expectedRevision?: number,
): Promise<LotDraft> {
  return apiRequest<LotDraft>(
    `/chat/lot-drafts/${encodeURIComponent(draftId)}/confirm`,
    {
      method: 'POST',
      ...(expectedRevision !== undefined
        ? { body: JSON.stringify({ expected_revision: expectedRevision }) }
        : {}),
    },
  )
}