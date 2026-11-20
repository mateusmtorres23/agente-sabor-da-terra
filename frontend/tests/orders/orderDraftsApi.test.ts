import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  confirmOrderDraft,
  getOrderDraft,
  type OrderDraftConfirmation,
  type OrderDraftScope,
} from '../../src/features/orders/orderDraftsApi'
import { ApiError } from '../../src/lib/api-client'
import { clearAccessToken, setAccessToken } from '../../src/lib/auth-storage'

const base = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const fetchMock = vi.fn<typeof fetch>()
const confirmation: OrderDraftConfirmation = {
  buyer: 'Mercado Bom Preço',
  conditions: 'Entrega pela manhã.',
  delivery_start_date: '2026-11-06',
  delivery_end_date: null,
  draft_version: 3,
  confirmed: true,
  items: [{
    draft_item_id: 'cheese-line', product_id: 'cheese-product',
    quantity: '10.000', unit: 'kg',
  }],
}

const contexts: { scope: OrderDraftScope; path: string }[] = [
  { scope: { kind: 'chat', id: 'session/id' }, path: '/chat/sessions/session%2Fid' },
  { scope: { kind: 'triage', id: 'solicitation/id' }, path: '/solicitations/solicitation%2Fid' },
]

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  setAccessToken('draft-test-token')
})

afterEach(() => {
  clearAccessToken()
  vi.unstubAllGlobals()
})

describe.each(contexts)('rascunho em $scope.kind', ({ scope, path }) => {
  it('consulta o contexto com JWT e permite cancelar a consulta', async () => {
    fetchMock.mockResolvedValue(Response.json({ draft: null, order: null }))
    const { signal } = new AbortController()
    expect(await getOrderDraft(scope, signal)).toEqual({ draft: null, order: null })
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe(`${base}${path}/order-draft`)
    expect(options?.signal).toBe(signal)
    expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer draft-test-token')
  })

  it.each([201, 200])('aceita confirmação nova ou repetida com status %i', async (status) => {
    // This API layer must preserve the selected items and the opened draft version.
    const saved = { id: 'saved-order', session_id: 'original-session', items: [] }
    fetchMock.mockResolvedValue(Response.json(saved, { status }))
    expect(await confirmOrderDraft(scope, 'draft/id', confirmation)).toEqual(saved)
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe(`${base}${path}/order-drafts/draft%2Fid/confirm`)
    expect(options?.method).toBe('POST')
    expect(JSON.parse(options?.body as string)).toEqual(confirmation)
    const headers = new Headers(options?.headers)
    expect(headers.get('Authorization')).toBe('Bearer draft-test-token')
    expect(headers.get('Content-Type')).toBe('application/json')
  })

  it('preserva o ID do pedido existente no conflito e não repete o POST', async () => {
    const details = {
      detail: {
        code: 'order_already_confirmed',
        message: 'Esta conversa já possui um pedido.',
        order_id: 'existing-order',
      },
    }
    fetchMock.mockResolvedValue(Response.json(details, { status: 409 }))
    const result = confirmOrderDraft(scope, 'draft-id', confirmation)
    await expect(result).rejects.toBeInstanceOf(ApiError)
    await expect(result).rejects.toMatchObject({ status: 409, details })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('propaga falha de autenticação sem tentar confirmar novamente', async () => {
    fetchMock.mockResolvedValue(Response.json({ detail: 'Unauthorized' }, { status: 401 }))
    await expect(confirmOrderDraft(scope, 'draft-id', confirmation)).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
