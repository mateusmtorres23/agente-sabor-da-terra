import { useCallback, useEffect, useRef, useState } from 'react'

import { AppShell } from '../../../components/layout/AppShell'
import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { OrderDraftPanel } from '../../orders/components/OrderDraftPanel'
import { listOrders, type OrderRecord } from '../../orders/ordersApi'
import { listProducers } from '../../registry/registryApi'
import type { Producer } from '../../registry/types'
import { ChatHeader } from '../components/ChatHeader'
import { ChatHistory } from '../components/ChatHistory'
import { ChatInput } from '../components/ChatInput'
import { MessageList } from '../components/MessageList'
import {
  createChatSession,
  getChatSession,
  listChatSessions,
  sendChatMessage,
} from '../chatApi'
import type { ChatMessage, ChatSession, LotDraft } from '../types'

import './chat.css'

type ConversationState = {
  messages: ChatMessage[]
  loading: boolean
  sending: boolean
  loadError: string | null
  sendError: string | null
}

const emptyConversation: ConversationState = {
  messages: [],
  loading: false,
  sending: false,
  loadError: null,
  sendError: null,
}

function uniqueById<T extends { id: string }>(items: T[]): T[] {
  return [...new Map(items.map((item) => [item.id, item])).values()]
}

function sortMessages(messages: ChatMessage[]): ChatMessage[] {
  return [...messages].sort((left, right) =>
    left.position - right.position ||
    left.created_at.localeCompare(right.created_at) ||
    left.id.localeCompare(right.id)
  )
}

export function ChatPage() {
  const { logout } = useAuth()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [conversations, setConversations] = useState<
    Record<string, ConversationState | undefined>
  >({})
  const [orders, setOrders] = useState<OrderRecord[]>([])
  const [producers, setProducers] = useState<Producer[]>([])
  const [listing, setListing] = useState(true)
  const [creating, setCreating] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [createError, setCreateError] = useState<string | null>(null)
  const pageLifetime = useRef<AbortController | null>(null)
  const messageRead = useRef<AbortController | null>(null)
  const selectionRevision = useRef(0)
  const createInProgress = useRef(false)
  const pendingSends = useRef(new Set<string>())
  const confirmedMessages = useRef(new Map<string, ChatMessage[]>())

  const updateConversation = useCallback((
    sessionId: string, patch: Partial<ConversationState>,
  ) => {
    setConversations((current) => ({
      ...current,
      [sessionId]: { ...(current[sessionId] ?? emptyConversation), ...patch },
    }))
  }, [])

  const expireSession = useCallback((error: unknown, lifetime: AbortController) => {
    if (error instanceof ApiError && error.status === 401) {
      lifetime.abort()
      messageRead.current?.abort()
      logout()
      return true
    }
    return false
  }, [logout])

  const selectSession = useCallback(async (sessionId: string) => {
    const lifetime = pageLifetime.current
    if (!lifetime || lifetime.signal.aborted) return

    selectionRevision.current += 1
    messageRead.current?.abort()
    const controller = new AbortController()
    messageRead.current = controller
    setActiveSessionId(sessionId)
    setListError(null)
    setCreateError(null)
    updateConversation(sessionId, { loading: true, loadError: null })

    const isCurrentRead = () =>
      !lifetime.signal.aborted && !controller.signal.aborted &&
      messageRead.current === controller

    try {
      const session = await getChatSession(sessionId, controller.signal)
      if (!isCurrentRead()) return

      // A read may have started before an in-flight send was committed.
      updateConversation(sessionId, {
        messages: sortMessages(uniqueById([
          ...session.messages,
          ...(confirmedMessages.current.get(sessionId) ?? []),
        ])),
      })
    } catch (error) {
      if (!isCurrentRead() || expireSession(error, lifetime)) return
      updateConversation(sessionId, {
        loadError: 'Não foi possível carregar as mensagens.',
      })
    } finally {
      if (isCurrentRead()) {
        messageRead.current = null
        updateConversation(sessionId, { loading: false })
      }
    }
  }, [expireSession, updateConversation])

  useEffect(() => {
    const lifetime = new AbortController()
    pageLifetime.current = lifetime
    const initialRevision = selectionRevision.current

    async function loadSessions() {
      try {
        const data = await listChatSessions(lifetime.signal)
        if (lifetime.signal.aborted) return
        setSessions((current) => uniqueById([...current, ...data]))

        if (selectionRevision.current === initialRevision && data.length > 0) {
          void selectSession(data[0].id)
        }
      } catch (error) {
        if (lifetime.signal.aborted || expireSession(error, lifetime)) return
        if (selectionRevision.current === initialRevision) {
          setListError('Não foi possível carregar as conversas.')
        }
      } finally {
        if (!lifetime.signal.aborted) setListing(false)
      }
    }

    async function loadCatalogContext() {
      try {
        const [orderList, producerList] = await Promise.all([
          listOrders(lifetime.signal),
          listProducers(undefined, lifetime.signal),
        ])
        if (lifetime.signal.aborted) return
        setOrders(orderList)
        setProducers(producerList)
      } catch (error) {
        if (lifetime.signal.aborted || expireSession(error, lifetime)) return
      }
    }

    void loadCatalogContext()
    void loadSessions()
    return () => {
      lifetime.abort()
      messageRead.current?.abort()
    }
  }, [expireSession, selectSession])

  async function handleCreateSession() {
    const lifetime = pageLifetime.current
    if (!lifetime || lifetime.signal.aborted || createInProgress.current) return

    createInProgress.current = true
    const revision = ++selectionRevision.current
    setCreating(true)
    setListError(null)
    setCreateError(null)

    try {
      const session = await createChatSession()
      if (lifetime.signal.aborted) return
      setSessions((current) => uniqueById([session, ...current]))

      if (selectionRevision.current === revision) {
        messageRead.current?.abort()
        messageRead.current = null
        updateConversation(session.id, emptyConversation)
        setActiveSessionId(session.id)
      }
    } catch (error) {
      if (lifetime.signal.aborted || expireSession(error, lifetime)) return
      if (selectionRevision.current === revision) {
        setCreateError('Não foi possível criar uma nova conversa.')
      }
    } finally {
      createInProgress.current = false
      if (!lifetime.signal.aborted) setCreating(false)
    }
  }

  async function handleSendMessage(content: string) {
    const lifetime = pageLifetime.current
    const sessionId = activeSessionId
    if (!lifetime || lifetime.signal.aborted || !sessionId ||
      pendingSends.current.has(sessionId)) return

    pendingSends.current.add(sessionId)
    updateConversation(sessionId, { sending: true, sendError: null })

    try {
      const message = await sendChatMessage(sessionId, { content })
      if (lifetime.signal.aborted) return

      confirmedMessages.current.set(sessionId, uniqueById([
        ...(confirmedMessages.current.get(sessionId) ?? []), message,
      ]))
      setConversations((current) => {
        const conversation = current[sessionId] ?? emptyConversation
        return {
          ...current,
          [sessionId]: {
            ...conversation,
            messages: sortMessages(uniqueById([...conversation.messages, message])),
          },
        }
      })
    } catch (error) {
      if (!lifetime.signal.aborted && !expireSession(error, lifetime)) {
        updateConversation(sessionId, {
          sendError: 'Não foi possível enviar a mensagem.',
        })
      }
      throw error
    } finally {
      pendingSends.current.delete(sessionId)
      if (!lifetime.signal.aborted) updateConversation(sessionId, { sending: false })
    }
  }

  const handleDraftUpdated = useCallback(
    (messageId: string, updatedDraft: LotDraft) => {
      const sessionId = activeSessionId
      if (!sessionId) return

      const applyDraft = (list: ChatMessage[]) =>
        list.map((msg) =>
          msg.id === messageId ? { ...msg, lot_draft: updatedDraft } : msg,
        )

      const existingConfirmed = confirmedMessages.current.get(sessionId)
      if (existingConfirmed) {
        confirmedMessages.current.set(sessionId, applyDraft(existingConfirmed))
      }

      setConversations((current) => {
        const conv = current[sessionId]
        if (!conv) return current
        return {
          ...current,
          [sessionId]: {
            ...conv,
            messages: applyDraft(conv.messages),
          },
        }
      })

      if (updatedDraft.status === 'confirmado') {
        void listOrders().then(setOrders).catch(() => {})
      }
    },
    [activeSessionId],
  )

  const conversation = (activeSessionId && conversations[activeSessionId]) || emptyConversation
  const loading = conversation.loading || (!activeSessionId && (listing || creating))
  const errors = [listError, createError, conversation.loadError, conversation.sendError]

  return (
    <AppShell>
      <div className="chat-page">
        <ChatHistory
          conversations={sessions}
          activeSessionId={activeSessionId}
          creating={creating}
          onSelect={selectSession}
          onCreate={handleCreateSession}
        />

        <section className="chat-workspace" aria-label="Chat da cooperativa">
          <ChatHeader
            title={
              sessions.find((session) => session.id === activeSessionId)
                ?.title ?? 'Novo chat'
            }
            subtitle="Consulte informações da operação da cooperativa."
          />

          {errors.map((error) => error && <p key={error} role="alert">{error}</p>)}

          {loading ? (
            <p>Carregando conversa...</p>
          ) : (
            <MessageList
              messages={conversation.messages}
              orders={orders}
              producers={producers}
              onDraftUpdated={handleDraftUpdated}
            />
          )}

          {activeSessionId && (
            <OrderDraftPanel scope={{ kind: 'chat', id: activeSessionId }} />
          )}

          <ChatInput
            key={activeSessionId ?? 'no-session'}
            onSend={handleSendMessage}
            disabled={!activeSessionId || loading || conversation.sending}
          />
        </section>
      </div>
    </AppShell>
  )
}