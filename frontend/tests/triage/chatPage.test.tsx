import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../src/features/auth/AuthContext'
import { TriageChatPage } from '../../src/features/triage/pages/TriageChatPage'
import {
  finalizeSolicitation,
  openSolicitationSession,
  sendSolicitationMessage,
} from '../../src/features/triage/triageApi'
import type { SolicitationSession } from '../../src/features/triage/types'
import { ApiError } from '../../src/lib/api-client'
import { getAccessToken, setAccessToken } from '../../src/lib/auth-storage'

vi.mock('../../src/features/triage/triageApi', () => ({
  finalizeSolicitation: vi.fn(),
  openSolicitationSession: vi.fn(),
  sendSolicitationMessage: vi.fn(),
}))

// Draft review is tested separately; avoid real HTTP in triage page tests.
vi.mock('../../src/features/orders/orderDraftsApi', () => ({
  getOrderDraft: vi.fn(async () => ({ draft: null, order: null })),
  confirmOrderDraft: vi.fn(),
}))

const read = vi.mocked(openSolicitationSession)
const send = vi.mocked(sendSolicitationMessage)
const finalize = vi.mocked(finalizeSolicitation)
const timestamp = '2026-10-30T16:00:00Z'
const session: SolicitationSession = {
  id: 'solicitation-a',
  session_id: 'session-a',
  summary: 'Oferta de queijo coalho com pedido de retorno.',
  request_type: 'oferta',
  urgency: 'urgente',
  status: 'em_analise',
  title: 'PED-2026-015',
  created_at: timestamp,
  read_only: false,
  messages: [
    {
      id: 'message-original',
      role: 'user',
      content: 'Tenho 200 kg de queijo coalho. Me avisa até amanhã.',
      position: 1,
      created_at: timestamp,
      citations: [],
    },
    {
      id: 'message-analysis',
      role: 'assistant',
      content: 'Análise inicial da triagem\nPrazo: 31/10/2026\nPendências:\n- Verificar pedidos da semana.',
      position: 2,
      created_at: timestamp,
      citations: [],
    },
  ],
}
const solved: SolicitationSession = {
  ...session,
  status: 'finalizada',
  read_only: true,
}
const clarification = {
  id: 'message-clarification',
  role: 'user',
  content: 'Há pedidos para o produtor nesta semana.',
  position: 3,
  created_at: timestamp,
  citations: [],
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function renderPage(solicitationId = session.id) {
  return render(
    <MemoryRouter initialEntries={[`/triagem/${solicitationId}`]}>
      <AuthProvider>
        <Routes>
          <Route path="/triagem" element={<h1>Fila de triagem</h1>} />
          <Route path="/triagem/:solicitationId" element={<TriageChatPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

function editor() {
  return screen.getByRole<HTMLTextAreaElement>('textbox', {
    name: 'Mensagem para o assistente',
  })
}

function submit(content: string) {
  fireEvent.change(editor(), { target: { value: content } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar mensagem' }))
}

describe('TriageChatPage', () => {
  beforeEach(() => {
    localStorage.clear()
    setAccessToken('test-token')
    read.mockReset().mockResolvedValue(session)
    send.mockReset().mockResolvedValue(clarification)
    finalize.mockReset().mockResolvedValue({
      id: session.id,
      session_id: session.session_id,
      summary: session.summary,
      request_type: session.request_type,
      urgency: session.urgency,
      status: 'finalizada',
    })
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('loads the shared history with original message and initial analysis', async () => {
    const pending = deferred<SolicitationSession>()
    read.mockReturnValueOnce(pending.promise)
    renderPage()

    expect(screen.getByRole('status').textContent).toBe('Carregando solicitação…')
    expect(read).toHaveBeenCalledExactlyOnceWith(
      session.id,
      expect.any(AbortSignal),
    )
    await act(async () => pending.resolve(session))

    expect(
      await screen.findByRole('heading', { name: session.summary }),
    ).toBeTruthy()
    for (const value of ['Em análise', 'Urgente', 'Oferta']) {
      expect(screen.getByText(value)).toBeTruthy()
    }

    const log = screen.getByRole('log')
    expect(within(log).getByText('Mensagem original')).toBeTruthy()
    expect(within(log).getByText(session.messages[0].content)).toBeTruthy()
    expect(within(log).getByText('Assistente')).toBeTruthy()
    expect(within(log).getByText(/Análise inicial da triagem/)).toBeTruthy()
    expect(within(log).getByText(/Prazo: 31\/10\/2026/)).toBeTruthy()
    expect(editor().disabled).toBe(false)
  })

  it('sends a clarification into the shared conversation', async () => {
    const pending = deferred<typeof clarification>()
    send.mockReturnValueOnce(pending.promise)
    renderPage()
    await screen.findByRole('heading', { name: session.summary })

    submit(clarification.content)

    expect(send).toHaveBeenCalledExactlyOnceWith(session.id, {
      content: clarification.content,
    })
    expect(editor().disabled).toBe(true)
    await act(async () => pending.resolve(clarification))

    const log = screen.getByRole('log')
    expect(within(log).getByText('Funcionário')).toBeTruthy()
    expect(within(log).getByText(clarification.content)).toBeTruthy()
    expect(editor().value).toBe('')
    expect(editor().disabled).toBe(false)
  })

  it('preserves the draft and shows an error when sending fails', async () => {
    send.mockRejectedValueOnce(new Error('Offline'))
    renderPage()
    await screen.findByRole('heading', { name: session.summary })

    submit('Mensagem que não foi enviada')

    expect((await screen.findByRole('alert')).textContent)
      .toBe('Não foi possível enviar a mensagem.')
    expect(editor().value).toBe('Mensagem que não foi enviada')
    expect(screen.queryByText('Funcionário')).toBeNull()
  })

  it('switches to read-only when another employee finalized the conversation', async () => {
    send.mockRejectedValueOnce(new ApiError(409, null))
    renderPage()
    await screen.findByRole('heading', { name: session.summary })

    submit('Mensagem atrasada')

    expect((await screen.findByRole('alert')).textContent)
      .toBe('A conversa foi finalizada e não aceita novas mensagens.')
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.getByText('Finalizada')).toBeTruthy()
    expect(screen.getByText(/permanece disponível/)).toBeTruthy()
  })

  it('finalizes without service after confirming and remains consultable', async () => {
    const pending = deferred<Awaited<ReturnType<typeof finalizeSolicitation>>>()
    finalize.mockReturnValueOnce(pending.promise)
    renderPage()
    await screen.findByRole('heading', { name: session.summary })

    fireEvent.click(screen.getByRole('button', { name: 'Encerrar solicitação' }))
    const confirmation = screen.getByRole('group', {
      name: 'Confirmar encerramento da solicitação',
    })
    expect(finalize).not.toHaveBeenCalled()
    fireEvent.click(within(confirmation).getByRole('button', {
      name: 'Confirmar encerramento',
    }))
    expect(finalize).toHaveBeenCalledExactlyOnceWith(session.id)
    expect(within(confirmation).getByRole<HTMLButtonElement>('button', {
      name: 'Finalizando…',
    }).disabled).toBe(true)

    await act(async () => pending.resolve({
      id: session.id,
      session_id: session.session_id,
      summary: session.summary,
      request_type: session.request_type,
      urgency: session.urgency,
      status: 'finalizada',
    }))

    expect(screen.getByText(
      'Solicitação finalizada. A conversa permanece disponível para consulta.',
    )).toBeTruthy()
    expect(screen.getByText('Finalizada')).toBeTruthy()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Encerrar solicitação' })).toBeNull()
    expect(
      within(screen.getByRole('log')).getByText(/Análise inicial da triagem/),
    ).toBeTruthy()
  })

  it('cancels finalization without calling the API', async () => {
    renderPage()
    await screen.findByRole('heading', { name: session.summary })

    fireEvent.click(screen.getByRole('button', { name: 'Encerrar solicitação' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(finalize).not.toHaveBeenCalled()
    expect(screen.queryByRole('group')).toBeNull()
    expect(editor().disabled).toBe(false)
  })

  it('opens a finalized solicitation in read-only mode', async () => {
    read.mockResolvedValueOnce(solved)
    renderPage()

    await screen.findByRole('heading', { name: session.summary })

    expect(screen.getByText('Finalizada')).toBeTruthy()
    expect(screen.getByText(/somente para consulta/)).toBeTruthy()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Encerrar solicitação' })).toBeNull()
    expect(within(screen.getByRole('log')).getByText(session.messages[0].content)).toBeTruthy()
  })

  it('shows a not-found state and returns to the queue', async () => {
    read.mockRejectedValueOnce(new ApiError(404, null))
    renderPage('unknown')

    expect(
      await screen.findByRole('heading', { name: 'Solicitação não encontrada' }),
    ).toBeTruthy()
    fireEvent.click(screen.getByRole('link', { name: '← Voltar para a fila' }))

    expect(screen.getByRole('heading', { name: 'Fila de triagem' })).toBeTruthy()
  })

  it('retries a failed load', async () => {
    read.mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce(session)
    renderPage()

    expect((await screen.findByRole('alert')).textContent)
      .toBe('Não foi possível carregar a solicitação.')
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    expect(
      await screen.findByRole('heading', { name: session.summary }),
    ).toBeTruthy()
    expect(read).toHaveBeenCalledTimes(2)
  })

  it('aborts the active read on unmount', async () => {
    const pending = deferred<SolicitationSession>()
    read.mockReturnValueOnce(pending.promise)
    const { unmount } = renderPage()
    const signal = read.mock.calls[0][1]

    expect(signal?.aborted).toBe(false)
    unmount()
    expect(signal?.aborted).toBe(true)
  })

  it('logs out when the session read returns 401', async () => {
    read.mockRejectedValueOnce(new ApiError(401, null))
    renderPage()

    await waitFor(() => expect(getAccessToken()).toBeNull())
  })
})
