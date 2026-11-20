
export interface ChatSession {
  id: string
  title: string
  created_at: string
}

export interface Citation {
  message_id: string
  chunk_id: string
  document_id: string
  document_name: string
  chunk_content: string
  record_id: string | null
  record_fields: Record<string, string> | null
  source_type: 'record' | 'excerpt'
  label: string
  view_url: string
  download_url: string
}

export interface ChatMessage {
  id: string
  role: string
  content: string
  position: number
  created_at: string
  citations: Citation[]
  lot_draft?: LotDraft | null
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[]
}

export interface CreateMessagePayload {
  content: string
}
export interface LotDraftOrderDeadline {
  delivery_start_date: string
  delivery_end_date: string | null
  cancelled: boolean
}

export interface LotDraftSavedLot {
  id: string
  order_id: string | null
  item_id: string | null
  producer_id: string
  producer_name: string
  quantity: string
  unit: string | null
  delivery_date: string
  availability_confirmed: boolean | null
}

export interface LotDraft {
  id: string
  session_id: string
  message_id: string
  order_id: string | null
  item_id: string | null
  producer_id: string | null
  quantity: string | null
  unit: string | null
  delivery_date: string | null
  availability_confirmed: boolean
  needs_date_review: boolean
  lot_id: string | null
  status: 'em_revisao' | 'confirmado'
  order_deadline: LotDraftOrderDeadline | null
  saved_lot: LotDraftSavedLot | null
}