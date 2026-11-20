import { useEffect, useId, useRef, useState, type FormEvent } from 'react'

import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { listProducts } from '../../registry/registryApi'
import type { Product } from '../../registry/types'
import type { OrderDraftConfirmation, OrderDraftRecord } from '../orderDraftsApi'
import { validQuantity } from '../orderHelpers'

interface Props {
  draft: OrderDraftRecord
  pending: boolean
  blocked: boolean
  onConfirm: (payload: OrderDraftConfirmation) => Promise<void>
}

export function OrderDraftReviewForm({ draft, pending, blocked, onConfirm }: Props) {
  const { logout } = useAuth()
  const prefix = useId()
  const [buyer, setBuyer] = useState(draft.data.buyer ?? '')
  const [conditions, setConditions] = useState(draft.data.conditions)
  const [start, setStart] = useState(draft.data.delivery_start_date ?? '')
  const [end, setEnd] = useState(draft.data.delivery_end_date ?? '')
  const [interval, setInterval] = useState(Boolean(draft.data.delivery_end_date))
  const [confirmed, setConfirmed] = useState(false)
  const [items, setItems] = useState(() => draft.data.items.map(item => ({
    ...item, selected: true, product_id: item.product_id ?? '',
    quantity: item.quantity ?? '', unit: item.unit ?? '',
  })))
  const [catalog, setCatalog] = useState<Product[] | null>(null)
  const [catalogError, setCatalogError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [validation, setValidation] = useState<string | null>(null)
  const submitting = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    void listProducts(controller.signal).then(products => {
      if (!controller.signal.aborted) setCatalog(products)
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return
      if (error instanceof ApiError && error.status === 401) logout()
      else setCatalogError(true)
    })
    return () => controller.abort()
  }, [attempt, logout])

  function editItem(index: number, field: 'product_id' | 'quantity' | 'unit', value: string) {
    setItems(current => current.map((item, i) => i === index ? { ...item, [field]: value } : item))
    setConfirmed(false)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending || blocked || submitting.current) return
    const selected = items.filter(item => item.selected)
    if (!confirmed) {
      setValidation('Marque a confirmação após revisar os dados.')
      return
    }
    if (!buyer.trim() || !start || (interval && !end)) {
      setValidation('Preencha o comprador e o prazo de entrega.')
      return
    }
    if (interval && end < start) {
      setValidation('A data final deve ser igual ou posterior à data inicial.')
      return
    }
    if (!catalog?.length || selected.length === 0 || selected.some(item =>
      !catalog.some(product => product.id === item.product_id) ||
      !validQuantity(item.quantity.trim().replace(',', '.')) || !item.unit.trim()
    )) {
      setValidation('Selecione pelo menos um produto do catálogo, com quantidade positiva de até 3 casas decimais e unidade.')
      return
    }
    setValidation(null)
    submitting.current = true
    try {
      await onConfirm({
        buyer: buyer.trim(), conditions: conditions.trim(),
        delivery_start_date: start, delivery_end_date: interval ? end : null,
        confirmed: true, draft_version: draft.version,
        items: selected.map(item => ({
          draft_item_id: item.id, product_id: item.product_id,
          quantity: item.quantity.trim().replace(',', '.'), unit: item.unit.trim(),
        })),
      })
    } finally {
      submitting.current = false
    }
  }

  const disabled = pending || blocked
  return (
    <form onSubmit={submit} aria-label="Revisão do pedido" aria-busy={pending}>
      <p>Revise os dados antes de cadastrar. Apenas os itens condicionais podem ser retirados.</p>
      {draft.data.pending.length > 0 && <div className="draft-review-notice">
        <strong>Pendências apontadas no rascunho</strong>
        <ul>{draft.data.pending.map((text, i) => <li key={i}>{text}</li>)}</ul>
        <p>Confira e complete os campos correspondentes antes de confirmar.</p>
      </div>}
      <fieldset disabled={disabled}>
        <legend>Dados do pedido</legend>
        <label htmlFor={`${prefix}-buyer`}>Comprador</label>
        <input id={`${prefix}-buyer`} value={buyer} required onChange={e => { setBuyer(e.target.value); setConfirmed(false) }} />
        <label htmlFor={`${prefix}-conditions`}>Condições de atendimento</label>
        <textarea id={`${prefix}-conditions`} value={conditions} rows={2} onChange={e => { setConditions(e.target.value); setConfirmed(false) }} />
      </fieldset>
      {catalogError ? <div role="alert">
        <p>Não foi possível carregar o catálogo.</p>
        <button type="button" disabled={disabled} onClick={() => {
          setCatalogError(false); setCatalog(null); setAttempt(value => value + 1)
        }}>Recarregar catálogo</button>
      </div> : catalog === null ? <p>Carregando catálogo…</p> : catalog.length === 0 ? <p role="alert">Nenhum produto cadastrado. Cadastre produtos no catálogo antes de confirmar.</p> : null}
      {items.map((item, index) => <fieldset key={item.id} disabled={disabled} className="draft-review-item">
        <legend>Item {index + 1}{item.product_name ? `: ${item.product_name}` : ''}</legend>
        {item.conditional ? <>
          <label className="draft-review-check">
            <input type="checkbox" checked={item.selected} onChange={e => {
              const selected = e.target.checked
              setItems(current => current.map((row, i) => i === index ? { ...row, selected } : row))
              setConfirmed(false)
            }} />Incluir item condicional {index + 1}
          </label>
          <p>{item.condition_text || 'Inclusão sujeita à revisão.'}</p>
        </> : <p>Item obrigatório</p>}
        {item.pending.length > 0 && <ul className="draft-review-notice">{item.pending.map((text, i) => <li key={i}>{text}</li>)}</ul>}
        <div className="draft-review-grid">
          <div>
            <label htmlFor={`${prefix}-product-${index}`}>Produto {index + 1}</label>
            <select id={`${prefix}-product-${index}`} value={item.product_id} required={item.selected} disabled={!item.selected || !catalog?.length} onChange={e => editItem(index, 'product_id', e.target.value)}>
              <option value="">Selecione um produto</option>
              {item.product_id && !catalog?.some(product => product.id === item.product_id) && <option value={item.product_id} disabled>Produto indisponível — selecione outro</option>}
              {catalog?.map(product => <option key={product.id} value={product.id}>{product.name}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor={`${prefix}-quantity-${index}`}>Quantidade {index + 1}</label>
            <input id={`${prefix}-quantity-${index}`} inputMode="decimal" value={item.quantity} disabled={!item.selected} required={item.selected} onChange={e => editItem(index, 'quantity', e.target.value)} />
          </div>
          <div>
            <label htmlFor={`${prefix}-unit-${index}`}>Unidade {index + 1}</label>
            <input id={`${prefix}-unit-${index}`} value={item.unit} disabled={!item.selected} required={item.selected} onChange={e => editItem(index, 'unit', e.target.value)} />
          </div>
        </div>
      </fieldset>)}
      {items.length === 0 && <p role="alert">O rascunho ainda não tem itens. Aguarde um rascunho com produtos antes de confirmar.</p>}
      <fieldset disabled={disabled}>
        <legend>Prazo de entrega</legend>
        <label className="draft-review-check"><input type="checkbox" checked={interval} onChange={e => { setInterval(e.target.checked); setConfirmed(false) }} />Entrega em um intervalo de datas</label>
        <div className="draft-review-grid">
          <div><label htmlFor={`${prefix}-start`}>{interval ? 'Data inicial' : 'Data de entrega'}</label>
            <input id={`${prefix}-start`} type="date" required value={start} onChange={e => { setStart(e.target.value); setConfirmed(false) }} /></div>
          {interval && <div><label htmlFor={`${prefix}-end`}>Data final</label>
            <input id={`${prefix}-end`} type="date" required min={start || undefined} value={end} onChange={e => { setEnd(e.target.value); setConfirmed(false) }} /></div>}
        </div>
        <label className="draft-review-check"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />Revisei os dados e confirmo o cadastro deste pedido.</label>
      </fieldset>
      {validation && <p role="alert">{validation}</p>}
      <button className="draft-review-primary" type="submit" disabled={disabled || !catalog?.length || items.length === 0 || !confirmed}>{pending ? 'Confirmando…' : 'Confirmar pedido'}</button>
    </form>
  )
}
