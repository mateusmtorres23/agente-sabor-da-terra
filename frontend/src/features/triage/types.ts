import type { ChatMessage } from '../chat/types'

export type SolicitationStatus = 'recebida' | 'em_analise' | 'finalizada'

export type SolicitationType =
  | 'pedido'
  | 'consulta'
  | 'oferta'
  | 'comunicado'
  | 'nao_identificado'

export type SolicitationUrgency = 'urgente' | 'normal' | 'indeterminada'

export interface Solicitation {
  id: string
  session_id: string
  summary: string
  request_type: SolicitationType
  urgency: SolicitationUrgency
  status: SolicitationStatus
}

export interface SolicitationSession extends Solicitation {
  title: string
  created_at: string
  read_only: boolean
  messages: ChatMessage[]
}

export interface SolicitationMessagePayload {
  content: string
}

export const solicitationStatusLabels: Record<SolicitationStatus, string> = {
  recebida: 'Recebida',
  em_analise: 'Em análise',
  finalizada: 'Finalizada',
}

export const solicitationTypeLabels: Record<SolicitationType, string> = {
  pedido: 'Pedido',
  consulta: 'Consulta',
  oferta: 'Oferta',
  comunicado: 'Comunicado',
  nao_identificado: 'Não identificado',
}

export const solicitationUrgencyLabels: Record<SolicitationUrgency, string> = {
  urgente: 'Urgente',
  normal: 'Normal',
  indeterminada: 'Indeterminada',
}
export type ReceivedEntryStatus =
  | 'pendente'
  | 'em_processamento'
  | 'concluida'
  | 'falhou'

export interface FailedTriageEntry {
  id: string
  original_text: string
  sender: string
  source_channel: string
  received_at: string
  triage_status: ReceivedEntryStatus
  failure_reason?: string | null
}

export interface RetryTriageEntryResponse {
  entry: FailedTriageEntry
  solicitation: Solicitation | null
  enqueued: boolean
}