import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import {
  confirmOrderDraft, getOrderDraft,
  type OrderDraftConfirmation, type OrderDraftContext, type OrderDraftScope,
} from '../orderDraftsApi'
import { OrderDraftReviewForm } from './OrderDraftReviewForm'

import './order-draft.css'

interface Props {
  scope: OrderDraftScope
  readOnly?: boolean
}

export function OrderDraftPanel(props: Props) {
  return <OrderDraftPanelContent key={`${props.scope.kind}:${props.scope.id}`} {...props} />
}

function conflictDetail(error: ApiError): { code?: string; orderId?: string } {
  const details = error.details
  if (typeof details !== 'object' || details === null || !('detail' in details)) return {}
  const detail = details.detail
  if (typeof detail !== 'object' || detail === null) return {}
  return {
    code: 'code' in detail && typeof detail.code === 'string' ? detail.code : undefined,
    orderId: 'order_id' in detail && typeof detail.order_id === 'string' ? detail.order_id : undefined,
  }
}

function OrderDraftPanelContent({ scope, readOnly = false }: Props) {
  const { logout } = useAuth()
  const [context, setContext] = useState<OrderDraftContext | null>(null)
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [blocked, setBlocked] = useState(false)
  const [existingId, setExistingId] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const mounted = useRef(false)
  const submitting = useRef(false)
  const { kind, id } = scope

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void getOrderDraft({ kind, id }, controller.signal).then(data => {
      if (controller.signal.aborted) return
      setContext(data)
      setBlocked(false)
      setExistingId(null)
      setError(null)
    }).catch((cause: unknown) => {
      if (controller.signal.aborted) return
      if (cause instanceof ApiError && cause.status === 401) logout()
      else setError('Não foi possível carregar o rascunho do pedido.')
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [kind, id, attempt, logout])

  function reload() {
    if (submitting.current) return
    setLoading(true)
    setError(null)
    setNotice(null)
    setAttempt(value => value + 1)
  }

  async function confirm(payload: OrderDraftConfirmation) {
    if (!context?.draft || submitting.current || readOnly || blocked) return
    submitting.current = true
    setPending(true)
    setError(null)
    try {
      const order = await confirmOrderDraft(scope, context.draft.id, payload)
      if (!mounted.current) return
      setContext(current => current ? { ...current, order } : current)
      setNotice('Pedido confirmado. O vínculo com esta conversa foi salvo.')
    } catch (cause) {
      if (!mounted.current) return
      if (cause instanceof ApiError) {
        if (cause.status === 401) { logout(); return }
        const detail = conflictDetail(cause)
        if (detail.code === 'order_already_confirmed') {
          setExistingId(detail.orderId ?? null)
          setBlocked(true)
          setError('Esta conversa já possui um pedido. Abra o pedido existente ou atualize o rascunho.')
          return
        }
        if (detail.code === 'order_draft_version_conflict') {
          setBlocked(true)
          setError('O rascunho foi alterado. Recarregue e revise os dados antes de confirmar.')
          return
        }
        if (detail.code === 'solicitation_finished') {
          setBlocked(true)
          setError('A solicitação foi finalizada. O pedido não pode ser confirmado por esta conversa.')
          return
        }
        if (cause.status === 404) {
          setBlocked(true)
          setError('Conversa ou rascunho indisponível. Atualize antes de continuar.')
          return
        }
        if (cause.status === 422) {
          setError('Confira os campos, os itens selecionados e os produtos do catálogo antes de confirmar.')
          return
        }
      }
      setError('Não foi possível confirmar o pedido. Tente novamente com os mesmos dados ou atualize o rascunho para conferir se o pedido foi salvo.')
    } finally {
      submitting.current = false
      if (mounted.current) setPending(false)
    }
  }

  const linkedId = context?.order?.id ?? existingId
  return (
    <section className="draft-review" aria-label="Pedido desta conversa">
      <header><h2>Pedido desta conversa</h2>
        <button type="button" disabled={pending || loading} onClick={reload}>Atualizar rascunho</button>
      </header>
      {loading ? <p>Carregando rascunho…</p> : <>
        {notice && <p role="status">{notice}</p>}
        {error && <p role="alert">{error}</p>}
        {linkedId ? <div className="draft-review-notice">
          <p>{context?.order?.cancelled ? 'O pedido vinculado foi cancelado. O vínculo com esta conversa permanece disponível.' : 'Esta conversa já possui um pedido cadastrado.'}</p>
          <Link to={`/orders/${encodeURIComponent(linkedId)}`}>Abrir pedido</Link>
        </div> : context?.draft ? <>
          {readOnly && <p>Solicitação finalizada: o rascunho está disponível somente para consulta.</p>}
          <OrderDraftReviewForm key={`${context.draft.id}:${context.draft.version}:${attempt}`} draft={context.draft} pending={pending} blocked={blocked || readOnly} onConfirm={confirm} />
        </> : context && <p>Nenhum rascunho de pedido nesta conversa.</p>}
      </>}
    </section>
  )
}
