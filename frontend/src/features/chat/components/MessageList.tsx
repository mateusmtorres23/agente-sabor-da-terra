import type { OrderRecord } from '../../orders/ordersApi'
import type { Producer } from '../../registry/types'
import type { ChatMessage, LotDraft } from '../types'

import { CitationList } from './CitationList'
import { LotDraftCard } from './LotDraftCard'

interface MessageListProps {
  messages: ChatMessage[]
  orders?: OrderRecord[]
  producers?: Producer[]
  onDraftUpdated?: (messageId: string, updatedDraft: LotDraft) => void
  className?: string
  ariaLabel?: string
  getPresentation?: (
    message: ChatMessage,
    index: number,
  ) => { className: string; author: string; authorClassName?: string }
}

export function MessageList({
  messages,
  orders = [],
  producers = [],
  onDraftUpdated,
  className = 'message-list',
  ariaLabel = 'Histórico da conversa',
  getPresentation,
}: MessageListProps) {
  return (
    <div
      className={className}
      role="log"
      aria-label={ariaLabel}
      aria-live="polite"
    >
      {messages.map((message, index) => {
        const isAssistant = message.role === 'assistant'
        const presentation = getPresentation?.(message, index) ?? {
          className: `chat-message ${isAssistant ? 'assistant' : 'user'}`,
          author: isAssistant ? 'Assistente' : 'Você',
        }

        return (
          <article
            className={presentation.className}
            key={message.id}
          >
            <span className={presentation.authorClassName ?? 'message-author'}>
              {presentation.author}
            </span>

            <p>{message.content}</p>

            {isAssistant && message.lot_draft && (
              <LotDraftCard
                draft={message.lot_draft}
                orders={orders}
                producers={producers}
                onDraftUpdated={(updated) => onDraftUpdated?.(message.id, updated)}
              />
            )}

            {isAssistant && <CitationList citations={message.citations} />}
          </article>
        )
      })}
    </div>
  )
}