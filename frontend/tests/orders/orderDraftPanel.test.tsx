import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../src/features/auth/AuthContext'
import { ChatPage } from '../../src/features/chat/pages/ChatPage'
import { getChatSession, listChatSessions } from '../../src/features/chat/chatApi'
import { TriageChatPage } from '../../src/features/triage/pages/TriageChatPage'
import { openSolicitationSession } from '../../src/features/triage/triageApi'
import { OrderDraftPanel } from '../../src/features/orders/components/OrderDraftPanel'
import { confirmOrderDraft, getOrderDraft, type OrderDraftRecord, type OrderDraftScope } from '../../src/features/orders/orderDraftsApi'
import type { OrderRecord } from '../../src/features/orders/ordersApi'
import { listProducts } from '../../src/features/registry/registryApi'
import { ApiError } from '../../src/lib/api-client'
import { getAccessToken, setAccessToken } from '../../src/lib/auth-storage'

vi.mock('../../src/features/orders/orderDraftsApi', () => ({ getOrderDraft: vi.fn(), confirmOrderDraft: vi.fn() }))
vi.mock('../../src/features/registry/registryApi', () => ({ listProducts: vi.fn() }))

vi.mock('../../src/features/chat/chatApi', () => ({
  getChatSession: vi.fn(), listChatSessions: vi.fn(),
  createChatSession: vi.fn(), sendChatMessage: vi.fn(),
}))
vi.mock('../../src/features/triage/triageApi', () => ({
  openSolicitationSession: vi.fn(), sendSolicitationMessage: vi.fn(),
  finalizeSolicitation: vi.fn(),
}))

const read = vi.mocked(getOrderDraft)
const confirm = vi.mocked(confirmOrderDraft)
const products = vi.mocked(listProducts)
const draft: OrderDraftRecord = {
  id: 'draft-a', session_id: 'chat-a', version: 3,
  confirmed_order_id: null, created_at: '2026-11-19T12:00:00Z',
  data: {
    buyer: 'Mercado Bom Preço', conditions: 'Entrega pela manhã.',
    delivery_start_date: '2026-11-04', delivery_end_date: '2026-11-08', pending: [],
    items: [
      { id: 'cheese-line', product_id: 'cheese', product_name: 'Queijo coalho', quantity: '10.000', unit: 'kg', conditional: false, condition_text: null, pending: [] },
      { id: 'honey-line', product_id: 'honey', product_name: 'Mel', quantity: '5.000', unit: 'pote', conditional: true, condition_text: 'Se tiver.', pending: [] },
    ],
  },
}
const order: OrderRecord = {
  id: 'order-a', session_id: 'chat-a', version: 1, cancelled: false,
  buyer: 'Mercado Bom Preço', conditions: 'Entrega pela manhã.',
  delivery_start_date: '2026-11-06', delivery_end_date: null,
  products: '', needs_item_structuring: false,
  items: [{ id: 'saved-line', product_id: 'cheese', product: { id: 'cheese', name: 'Queijo coalho' }, quantity: '10.000', unit: 'kg' }],
}
const scope: OrderDraftScope = { kind: 'chat', id: 'chat-a' }

function view(target = scope, readOnly = false) {
  return <MemoryRouter><AuthProvider><OrderDraftPanel scope={target} readOnly={readOnly} /></AuthProvider></MemoryRouter>
}
async function ready(target = scope, readOnly = false) {
  const result = render(view(target, readOnly))
  await screen.findAllByRole('option', { name: 'Queijo coalho' })
  return result
}
function acknowledge() { fireEvent.click(screen.getByLabelText('Revisei os dados e confirmo o cadastro deste pedido.')) }
function submit() { fireEvent.submit(screen.getByRole('form', { name: 'Revisão do pedido' })) }
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

beforeEach(() => {
  setAccessToken('test-token')
  read.mockReset().mockResolvedValue({ draft: structuredClone(draft), order: null })
  confirm.mockReset().mockResolvedValue(order)
  products.mockReset().mockResolvedValue([{ id: 'cheese', name: 'Queijo coalho' }, { id: 'honey', name: 'Mel' }])
})
afterEach(() => { cleanup(); localStorage.clear() })

describe('revisão de pedidos no chat', () => {
  it.each(['chat', 'triage'] as const)('confirma a seleção revisada no contexto %s', async kind => {
    const target = { kind, id: 'source-a' }
    await ready(target)
    expect(confirm).not.toHaveBeenCalled()
    expect(screen.getByText('Item obrigatório')).toBeTruthy()
    expect(screen.queryByLabelText('Incluir item condicional 1')).toBeNull()
    fireEvent.click(screen.getByLabelText('Incluir item condicional 2'))
    fireEvent.click(screen.getByLabelText('Entrega em um intervalo de datas'))
    fireEvent.change(screen.getByLabelText('Data de entrega'), { target: { value: '2026-11-06' } })
    acknowledge()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar pedido' }))
    await screen.findByRole('link', { name: 'Abrir pedido' })
    expect(confirm).toHaveBeenCalledExactlyOnceWith(target, 'draft-a', {
      buyer: 'Mercado Bom Preço', conditions: 'Entrega pela manhã.',
      delivery_start_date: '2026-11-06', delivery_end_date: null,
      confirmed: true, draft_version: 3,
      items: [{ draft_item_id: 'cheese-line', product_id: 'cheese', quantity: '10.000', unit: 'kg' }],
    })
    expect(screen.getByRole('link', { name: 'Abrir pedido' }).getAttribute('href')).toBe('/orders/order-a')
  })

  it('exige confirmação explícita e a desmarca após edição', async () => {
    await ready()
    submit()
    expect(confirm).not.toHaveBeenCalled()
    expect(await screen.findByRole('alert')).toBeTruthy()
    acknowledge()
    fireEvent.change(screen.getByLabelText('Comprador'), { target: { value: 'Outro comprador' } })
    expect(screen.getByRole<HTMLInputElement>('checkbox', { name: /Revisei os dados/ }).checked).toBe(false)
    submit()
    expect(confirm).not.toHaveBeenCalled()
  })

  it.each(['0', '1.1234'])('rejeita quantidade inválida %s antes de enviar', async quantity => {
    await ready()
    fireEvent.change(screen.getByLabelText('Quantidade 1'), { target: { value: quantity } })
    acknowledge(); submit()
    expect(confirm).not.toHaveBeenCalled()
    expect((await screen.findByRole('alert')).textContent).toContain('quantidade positiva')
  })

  it('bloqueia envio com período invertido', async () => {
    await ready()
    fireEvent.change(screen.getByLabelText('Data final'), { target: { value: '2026-11-01' } })
    acknowledge(); submit()
    expect(confirm).not.toHaveBeenCalled()
    expect((await screen.findByRole('alert')).textContent).toContain('data final')
  })

  it('não duplica o POST com dois envios enquanto aguarda a resposta', async () => {
    const pending = deferred<OrderRecord>()
    confirm.mockReturnValueOnce(pending.promise)
    await ready(); acknowledge(); submit(); submit()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Confirmando…' }).disabled).toBe(true)
    await act(async () => pending.resolve(order))
    await screen.findByRole('link', { name: 'Abrir pedido' })
  })

  it('bloqueia versão desatualizada até recarregar e exigir nova revisão', async () => {
    confirm.mockRejectedValueOnce(new ApiError(409, { detail: { code: 'order_draft_version_conflict' } }))
    await ready(); acknowledge(); submit()
    expect((await screen.findByRole('alert')).textContent).toContain('rascunho foi alterado')
    submit(); expect(confirm).toHaveBeenCalledTimes(1)
    read.mockResolvedValueOnce({ draft: { ...draft, version: 4, data: { ...draft.data, buyer: 'Comprador atualizado' } }, order: null })
    fireEvent.click(screen.getByRole('button', { name: 'Atualizar rascunho' }))
    await screen.findByDisplayValue('Comprador atualizado')
    expect(screen.getByRole<HTMLInputElement>('checkbox', { name: /Revisei os dados/ }).checked).toBe(false)
    acknowledge(); submit()
    await screen.findByRole('link', { name: 'Abrir pedido' })
    expect(confirm.mock.calls[1][2].draft_version).toBe(4)
  })

  it('mostra o pedido existente quando outra confirmação venceu', async () => {
    confirm.mockRejectedValueOnce(new ApiError(409, { detail: { code: 'order_already_confirmed', order_id: 'other-order' } }))
    await ready(); acknowledge(); submit()
    const link = await screen.findByRole('link', { name: 'Abrir pedido' })
    expect(link.getAttribute('href')).toBe('/orders/other-order')
    expect(screen.queryByRole('button', { name: 'Confirmar pedido' })).toBeNull()
  })

  it('mantém vínculo com pedido cancelado ao reabrir a conversa', async () => {
    read.mockResolvedValueOnce({ draft, order: { ...order, cancelled: true } })
    render(view())
    await screen.findByRole('link', { name: 'Abrir pedido' })
    expect(screen.getByText(/pedido vinculado foi cancelado/)).toBeTruthy()
    expect(confirm).not.toHaveBeenCalled()
    expect(products).not.toHaveBeenCalled()
  })

  it('permite consultar rascunho de triagem finalizada sem confirmar', async () => {
    await ready({ kind: 'triage', id: 'sol-a' }, true)
    submit()
    expect(confirm).not.toHaveBeenCalled()
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Confirmar pedido' }).disabled).toBe(true)
  })

  it('bloqueia o formulário se a triagem for finalizada durante a revisão', async () => {
    confirm.mockRejectedValueOnce(new ApiError(409, { detail: { code: 'solicitation_finished' } }))
    await ready(); acknowledge(); submit()
    expect((await screen.findByRole('alert')).textContent).toContain('solicitação foi finalizada')
    submit(); expect(confirm).toHaveBeenCalledTimes(1)
  })

  it('preserva os dados após falha de rede e permite repetir a mesma confirmação', async () => {
    confirm.mockRejectedValueOnce(new TypeError('network failure'))
    await ready(); acknowledge(); submit()
    await screen.findByRole('alert')
    expect(screen.getByDisplayValue('Mercado Bom Preço')).toBeTruthy()
    submit()
    await screen.findByRole('link', { name: 'Abrir pedido' })
    expect(confirm.mock.calls[1]).toEqual(confirm.mock.calls[0])
  })

  it('não envia confirmação quando o catálogo está vazio', async () => {
    products.mockResolvedValueOnce([])
    render(view())
    await screen.findByText(/Nenhum produto cadastrado/)
    acknowledge(); submit()
    expect(confirm).not.toHaveBeenCalled()
  })

  it('permite repetir a consulta após falha sem cadastrar pedido', async () => {
    read.mockRejectedValueOnce(new TypeError('network failure'))
    render(view())
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Atualizar rascunho' }))
    await screen.findByDisplayValue('Mercado Bom Preço')
    expect(confirm).not.toHaveBeenCalled()
  })

  it('ignora resposta de consulta atrasada ao trocar de conversa', async () => {
    const old = deferred<Awaited<ReturnType<typeof getOrderDraft>>>()
    read.mockReturnValueOnce(old.promise)
    const result = render(view())
    read.mockResolvedValueOnce({ draft: null, order: null })
    result.rerender(view({ kind: 'chat', id: 'chat-b' }))
    await screen.findByText('Nenhum rascunho de pedido nesta conversa.')
    await act(async () => old.resolve({ draft, order: null }))
    expect(screen.queryByDisplayValue('Mercado Bom Preço')).toBeNull()
    expect(confirm).not.toHaveBeenCalled()
  })

  it('ignora confirmação atrasada ao trocar de conversa', async () => {
    const pending = deferred<OrderRecord>()
    confirm.mockReturnValueOnce(pending.promise)
    const result = await ready(); acknowledge(); submit()
    read.mockResolvedValueOnce({ draft: null, order: null })
    result.rerender(view({ kind: 'chat', id: 'chat-b' }))
    await screen.findByText('Nenhum rascunho de pedido nesta conversa.')
    await act(async () => pending.resolve(order))
    expect(screen.queryByRole('link', { name: 'Abrir pedido' })).toBeNull()
  })

  it('encerra a autenticação quando a API retorna 401', async () => {
    confirm.mockRejectedValueOnce(new ApiError(401, {}))
    await ready(); acknowledge(); submit()
    await waitFor(() => expect(getAccessToken()).toBeNull())
  })
})


describe('integração do painel nas páginas de chat', () => {
  it('consulta o pedido da conversa privada selecionada', async () => {
    const chat = { id: 'chat-a', title: 'Minha conversa', created_at: '2026-11-19T12:00:00Z' }
    vi.mocked(listChatSessions).mockResolvedValue([chat])
    vi.mocked(getChatSession).mockResolvedValue({ ...chat, messages: [] })
    read.mockResolvedValueOnce({ draft, order })
    render(<MemoryRouter><AuthProvider><ChatPage /></AuthProvider></MemoryRouter>)
    await screen.findByRole('link', { name: 'Abrir pedido' })
    expect(read).toHaveBeenCalledWith({ kind: 'chat', id: 'chat-a' }, expect.any(AbortSignal))
    expect(confirm).not.toHaveBeenCalled()
  })

  it('usa o ID da solicitação e bloqueia revisão após a finalização', async () => {
    vi.mocked(openSolicitationSession).mockResolvedValue({
      id: 'solicitation-a', session_id: 'triage-chat-a', summary: 'Pedido recebido',
      request_type: 'pedido', urgency: 'normal', status: 'finalizada',
      title: 'Triagem', created_at: '2026-11-19T12:00:00Z',
      read_only: true, messages: [],
    })
    render(<MemoryRouter initialEntries={['/triagem/solicitation-a']}><AuthProvider><Routes>
      <Route path="/triagem/:solicitationId" element={<TriageChatPage />} />
    </Routes></AuthProvider></MemoryRouter>)
    await screen.findAllByRole('option', { name: 'Queijo coalho' })
    expect(read).toHaveBeenCalledWith({ kind: 'triage', id: 'solicitation-a' }, expect.any(AbortSignal))
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Confirmar pedido' }).disabled).toBe(true)
    expect(confirm).not.toHaveBeenCalled()
  })
})
