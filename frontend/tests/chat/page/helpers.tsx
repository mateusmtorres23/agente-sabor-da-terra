import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, vi } from 'vitest'

import { AuthProvider } from '../../../src/features/auth/AuthContext'
import {
  createChatSession,
  getChatSession,
  listChatSessions,
  sendChatMessage,
} from '../../../src/features/chat/chatApi'
import { ChatPage } from '../../../src/features/chat/pages/ChatPage'
import { clearAccessToken, setAccessToken } from '../../../src/lib/auth-storage'

vi.mock('../../../src/features/chat/chatApi', () => ({
  createChatSession: vi.fn(),
  getChatSession: vi.fn(),
  listChatSessions: vi.fn(),
  sendChatMessage: vi.fn(),
}))

// These page tests isolate chat behavior; draft review has its own tests.
vi.mock('../../../src/features/orders/orderDraftsApi', () => ({
  getOrderDraft: vi.fn(async () => ({ draft: null, order: null })),
  confirmOrderDraft: vi.fn(),
}))

export const list = vi.mocked(listChatSessions)
export const read = vi.mocked(getChatSession)
export const create = vi.mocked(createChatSession)
export const send = vi.mocked(sendChatMessage)

const timestamp = '2026-11-17T12:00:00Z'
export const sessionA = { id: 'session-a', title: 'Conversa A', created_at: timestamp }
export const sessionB = { id: 'session-b', title: 'Conversa B', created_at: timestamp }
export const sessionC = { id: 'session-c', title: 'Conversa C', created_at: timestamp }
export const messageA = { id: 'message-a', role: 'user', content: 'Mensagem de A', position: 1, created_at: timestamp, citations: [] }
export const messageB = { id: 'message-b', role: 'user', content: 'Mensagem de B', position: 1, created_at: timestamp, citations: [] }
export const detailA = { ...sessionA, messages: [messageA] }
export const detailB = { ...sessionB, messages: [messageB] }
export const sentA = { ...messageA, id: 'sent-a', content: 'Novo envio de A', position: 2, citations: [] }
export const sentB = { ...messageB, id: 'sent-b', content: 'Novo envio de B', position: 2, citations: [] }

export function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

export function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider><ChatPage /></AuthProvider>
    </MemoryRouter>,
  )
}

export async function renderReadyPage() {
  const result = renderPage()
  await screen.findByText(messageA.content)
  return result
}

export function select(title: string) {
  fireEvent.click(screen.getByRole('button', { name: title }))
}

export function editor() {
  return screen.getByRole('textbox', { name: 'Mensagem para o assistente' }) as HTMLTextAreaElement
}

export function submit(content: string) {
  fireEvent.change(editor(), { target: { value: content } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar mensagem' }))
}

export function setupChatPageTests() {
  beforeEach(() => {
    setAccessToken('test-token')
    list.mockReset().mockResolvedValue([sessionA, sessionB])
    read.mockReset().mockImplementation(async (id) => id === sessionA.id ? detailA : detailB)
    create.mockReset().mockResolvedValue(sessionC)
    send.mockReset().mockResolvedValue(sentA)
  })

  afterEach(clearAccessToken)
}
