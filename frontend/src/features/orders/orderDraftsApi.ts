import { apiRequest } from '../../lib/api-client'
import type { OrderInput, OrderItemInput, OrderRecord } from './ordersApi'

export type OrderDraftScope = {
  kind: 'chat' | 'triage'
  id: string
}

export interface OrderDraftItem {
  id: string
  product_id: string | null
  product_name: string | null
  quantity: string | null
  unit: string | null
  conditional: boolean
  condition_text: string | null
  pending: string[]
}

export interface OrderDraftData {
  buyer: string | null
  conditions: string
  delivery_start_date: string | null
  delivery_end_date: string | null
  items: OrderDraftItem[]
  pending: string[]
}

export interface OrderDraftRecord {
  id: string
  session_id: string
  version: number
  data: OrderDraftData
  confirmed_order_id: string | null
  created_at: string
}

export interface OrderDraftContext {
  draft: OrderDraftRecord | null
  order: OrderRecord | null
}

export interface OrderDraftItemConfirmation extends OrderItemInput {
  draft_item_id: string
}

export interface OrderDraftConfirmation extends Omit<OrderInput, 'items'> {
  draft_version: number
  confirmed: true
  items: OrderDraftItemConfirmation[]
}

function scopePath(scope: OrderDraftScope): string {
  const id = encodeURIComponent(scope.id)
  return scope.kind === 'chat'
    ? `/chat/sessions/${id}`
    : `/solicitations/${id}`
}

export function getOrderDraft(
  scope: OrderDraftScope,
  signal?: AbortSignal,
): Promise<OrderDraftContext> {
  return apiRequest(`${scopePath(scope)}/order-draft`, { signal })
}

export function confirmOrderDraft(
  scope: OrderDraftScope,
  draftId: string,
  payload: OrderDraftConfirmation,
): Promise<OrderRecord> {
  return apiRequest(
    `${scopePath(scope)}/order-drafts/${encodeURIComponent(draftId)}/confirm`,
    { method: 'POST', body: JSON.stringify(payload) },
  )
}
