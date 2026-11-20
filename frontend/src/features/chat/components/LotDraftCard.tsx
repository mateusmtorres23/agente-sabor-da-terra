import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '../../../lib/api-client'
import { apiErrorDetail } from '../../orders/orderHelpers'
import type { OrderRecord } from '../../orders/ordersApi'
import type { Producer } from '../../registry/types'
import {
  confirmLotDraft,
  setLotDraftAvailability,
  updateLotDraft,
} from '../chatApi'
import type { LotDraft } from '../types'

interface LotDraftCardProps {
  draft: LotDraft
  orders: OrderRecord[]
  producers: Producer[]
  onDraftUpdated: (updated: LotDraft) => void
}

function formatDeadline(deadline: LotDraft['order_deadline']): string {
  if (!deadline) return 'Não informado'
  if (
    deadline.delivery_end_date &&
    deadline.delivery_end_date !== deadline.delivery_start_date
  ) {
    return `${deadline.delivery_start_date} a ${deadline.delivery_end_date}`
  }
  return deadline.delivery_start_date
}

function normalizeQuantityForCompare(value: string | null | undefined): string {
  const trimmed = (value ?? '').trim()
  if (!trimmed) return ''
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? String(parsed) : trimmed
}

function lotDraftErrorMessage(error: unknown, fallback: string): string {
  const detail = apiErrorDetail(error)
  if (detail) return detail

  if (error instanceof ApiError && typeof error.details === 'object' && error.details !== null) {
    const rawDetail = (error.details as { detail?: unknown }).detail
    if (Array.isArray(rawDetail)) {
      const messages = rawDetail
        .map((item) =>
          typeof item === 'object' && item !== null && 'msg' in item && typeof item.msg === 'string'
            ? item.msg
            : null,
        )
        .filter((msg): msg is string => Boolean(msg))
      if (messages.length > 0) {
        return messages.join(' ')
      }
    }
  }

  return fallback
}

export function LotDraftCard({
  draft,
  orders,
  producers,
  onDraftUpdated,
}: LotDraftCardProps) {
  const navigate = useNavigate()
  const [orderId, setOrderId] = useState(draft.order_id ?? '')
  const [itemId, setItemId] = useState(draft.item_id ?? '')
  const [producerId, setProducerId] = useState(draft.producer_id ?? '')
  const [quantity, setQuantity] = useState(draft.quantity ?? '')
  const [unit, setUnit] = useState(draft.unit ?? '')
  const [deliveryDate, setDeliveryDate] = useState(draft.delivery_date ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setOrderId(draft.order_id ?? '')
    setItemId(draft.item_id ?? '')
    setProducerId(draft.producer_id ?? '')
    setQuantity(draft.quantity ?? '')
    setUnit(draft.unit ?? '')
    setDeliveryDate(draft.delivery_date ?? '')
  }, [draft])

  const selectedOrder = orders.find((order) => order.id === orderId)
  const availableItems = selectedOrder?.items ?? []
  const selectedItem = availableItems.find((item) => item.id === itemId)
  const selectedProducer = producers.find((producer) => producer.id === producerId)

  const effectiveDeadline: LotDraft['order_deadline'] = selectedOrder
    ? {
        delivery_start_date: selectedOrder.delivery_start_date,
        delivery_end_date: selectedOrder.delivery_end_date,
        cancelled: selectedOrder.cancelled,
      }
    : orderId
      ? draft.order_deadline
      : null

  const hasUnsavedChanges =
    orderId !== (draft.order_id ?? '') ||
    itemId !== (draft.item_id ?? '') ||
    producerId !== (draft.producer_id ?? '') ||
    normalizeQuantityForCompare(quantity) !== normalizeQuantityForCompare(draft.quantity) ||
    unit.trim() !== (draft.unit ?? '').trim() ||
    deliveryDate !== (draft.delivery_date ?? '')

  if (draft.status === 'confirmado') {
    const lot = draft.saved_lot
    const targetOrderId = lot?.order_id ?? draft.order_id
    return (
      <section className="lot-draft-card lot-draft-confirmed" aria-label="Lote confirmado">
        <h4>Lote confirmado</h4>
        <p>
          <strong>Pedido:</strong> {selectedOrder?.buyer ?? targetOrderId ?? '—'}
        </p>
        <p>
          <strong>Item:</strong> {selectedItem?.product.name ?? lot?.item_id ?? draft.item_id ?? '—'}
        </p>
        <p>
          <strong>Produtor:</strong>{' '}
          {lot?.producer_name || selectedProducer?.name || '—'}
        </p>
        <p>
          <strong>Quantidade:</strong> {lot?.quantity ?? draft.quantity ?? '—'}{' '}
          {lot?.unit ?? draft.unit ?? ''}
        </p>
        <p>
          <strong>Data prevista do lote:</strong>{' '}
          {lot?.delivery_date ?? draft.delivery_date ?? '—'}
        </p>
        {!lot && (
          <p className="lot-draft-meta">
            Autorização já processada (o lote cadastrado não está mais ativo).
          </p>
        )}
        {targetOrderId && (
          <button
            type="button"
            className="chat-button"
            onClick={() => navigate(`/orders/${encodeURIComponent(targetOrderId)}`)}
          >
            Abrir pedido
          </button>
        )}
      </section>
    )
  }

  async function handleSaveReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const updated = await updateLotDraft(draft.id, {
        order_id: orderId || null,
        item_id: itemId || null,
        producer_id: producerId || null,
        quantity: quantity.trim() || null,
        unit: unit.trim() || null,
        delivery_date: deliveryDate || null,
      })
      onDraftUpdated(updated)
    } catch (err) {
      setError(
        lotDraftErrorMessage(
          err,
          'Não foi possível atualizar o rascunho de lote.',
        ),
      )
    } finally {
      setBusy(false)
    }
  }

  async function handleConfirmAvailability() {
    if (busy || hasUnsavedChanges) return
    setBusy(true)
    setError(null)
    try {
      const updated = await setLotDraftAvailability(
        draft.id,
        true,
        draft.revision,
      )
      onDraftUpdated(updated)
    } catch (err) {
      setError(
        lotDraftErrorMessage(
          err,
          'Não foi possível confirmar a disponibilidade.',
        ),
      )
    } finally {
      setBusy(false)
    }
  }

  async function handleAuthorizeRegistration() {
    if (busy || hasUnsavedChanges || draft.needs_date_review) return
    setBusy(true)
    setError(null)
    try {
      const updated = await confirmLotDraft(draft.id, draft.revision)
      onDraftUpdated(updated)
    } catch (err) {
      setError(
        lotDraftErrorMessage(
          err,
          'Não foi possível cadastrar o lote. O rascunho foi preservado.',
        ),
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      className="lot-draft-card"
      aria-label="Revisão de rascunho de lote"
      onSubmit={handleSaveReview}
    >
      <h4>Rascunho de lote</h4>

      <p className="lot-draft-meta">
        <strong>Prazo aceito pelo comprador:</strong>{' '}
        {formatDeadline(effectiveDeadline)}
        {effectiveDeadline?.cancelled ? ' (Pedido cancelado)' : ''}
      </p>

      <p className="lot-draft-meta">
        <strong>Situação da disponibilidade:</strong>{' '}
        {draft.availability_confirmed ? 'Confirmada' : 'Pendente'}
      </p>

      {hasUnsavedChanges && (
        <p className="lot-draft-warning" role="status">
          Há alterações não salvas. Clique em “Salvar revisão” antes de
          confirmar a disponibilidade ou autorizar o cadastro.
        </p>
      )}

      {draft.needs_date_review && (
        <p className="lot-draft-warning" role="status">
          Pedido ou item alterado: revise e salve a data prevista do lote conforme o
          prazo aceito pelo comprador antes de autorizar o cadastro.
        </p>
      )}

      <label>
        Pedido
        <select
          value={orderId}
          disabled={busy}
          onChange={(e) => {
            const nextOrderId = e.target.value
            setOrderId(nextOrderId)
            setItemId('')
          }}
        >
          <option value="">Selecione o pedido</option>
          {orders.map((order) => (
            <option key={order.id} value={order.id}>
              {order.buyer} ({order.id.slice(0, 8)})
            </option>
          ))}
        </select>
      </label>

      <label>
        Item do pedido
        <select
          value={itemId}
          disabled={busy || !orderId}
          onChange={(e) => {
            const nextItemId = e.target.value
            setItemId(nextItemId)
            const chosen = availableItems.find((i) => i.id === nextItemId)
            if (chosen && !unit) {
              setUnit(chosen.unit)
            }
          }}
        >
          <option value="">Selecione o item</option>
          {availableItems.map((item) => (
            <option key={item.id} value={item.id}>
              {item.product.name} ({item.quantity} {item.unit})
            </option>
          ))}
        </select>
      </label>

      <label>
        Produtor
        <select
          value={producerId}
          disabled={busy}
          onChange={(e) => setProducerId(e.target.value)}
        >
          <option value="">Selecione o produtor</option>
          {producers.map((producer) => (
            <option key={producer.id} value={producer.id}>
              {producer.name} {!producer.active ? '(Inativo)' : ''}
            </option>
          ))}
        </select>
      </label>

      <label>
        Quantidade
        <input
          type="text"
          inputMode="decimal"
          value={quantity}
          disabled={busy}
          onChange={(e) => setQuantity(e.target.value)}
        />
      </label>

      <label>
        Unidade
        <input
          type="text"
          value={unit}
          disabled={busy}
          onChange={(e) => setUnit(e.target.value)}
        />
      </label>

      <label>
        Data prevista do lote (data_entrega)
        <input
          type="date"
          value={deliveryDate}
          disabled={busy}
          onChange={(e) => setDeliveryDate(e.target.value)}
        />
      </label>

      {error && (
        <p className="lot-draft-error" role="alert">
          {error}
        </p>
      )}

      <div className="lot-draft-actions">
        <button type="submit" className="chat-button" disabled={busy}>
          Salvar revisão
        </button>

        <button
          type="button"
          className="chat-button"
          disabled={busy || hasUnsavedChanges}
          onClick={() => void handleConfirmAvailability()}
        >
          Confirmar disponibilidade
        </button>

        <button
          type="button"
          className="chat-button chat-button-primary"
          disabled={
            busy ||
            hasUnsavedChanges ||
            draft.needs_date_review ||
            !draft.availability_confirmed
          }
          onClick={() => void handleAuthorizeRegistration()}
        >
          Autorizar cadastro
        </button>
      </div>
    </form>
  )
}