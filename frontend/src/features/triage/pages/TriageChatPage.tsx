import { useParams } from 'react-router-dom'

import { AppShell } from '../../../components/layout/AppShell'
import { OrderDraftPanel } from '../../orders/components/OrderDraftPanel'
import { TriageBackLink } from '../components/TriageBackLink'
import { TriageChatHeader } from '../components/TriageChatHeader'
import { TriageChatState } from '../components/TriageChatState'
import { TriageConversation } from '../components/TriageConversation'
import { TriageFinalizeConfirmation } from '../components/TriageFinalizeConfirmation'
import { useTriageChat } from '../hooks/useTriageChat'

import './triage.css'

export function TriageChatPage() {
  const { solicitationId } = useParams<{ solicitationId: string }>()

  return (
    <TriageChatPageContent
      key={solicitationId}
      solicitationId={solicitationId}
    />
  )
}

interface TriageChatPageContentProps {
  solicitationId: string | undefined
}

function TriageChatPageContent({
  solicitationId,
}: TriageChatPageContentProps) {
  const {
    detail,
    sending,
    finalizing,
    confirmingFinalize,
    sendError,
    finalizeError,
    notice,
    handleSendMessage,
    handleFinalize,
    startFinalize,
    cancelFinalize,
    retry,
  } = useTriageChat(solicitationId)

  if (detail.status === 'loading') {
    return <TriageChatState variant="loading" />
  }

  if (detail.status === 'not_found') {
    return <TriageChatState variant="not_found" />
  }

  if (detail.status === 'error') {
    return <TriageChatState variant="error" onRetry={retry} />
  }

  const session = detail.data

  return (
    <AppShell>
      <section
        className="triage-page triage-detail"
        aria-labelledby="triage-chat-heading"
      >
        <TriageBackLink />

        <TriageChatHeader
          summary={session.summary}
          status={session.status}
          urgency={session.urgency}
          requestType={session.request_type}
          readOnly={session.read_only}
          confirmingFinalize={confirmingFinalize}
          onStartFinalize={startFinalize}
        />

        {confirmingFinalize && !session.read_only && (
          <TriageFinalizeConfirmation
            finalizing={finalizing}
            onCancel={cancelFinalize}
            onConfirm={() => void handleFinalize()}
          />
        )}

        {finalizeError && (
          <p className="triage-action-error" role="alert">{finalizeError}</p>
        )}
        {notice && (
          <p className="triage-notice success" role="status">{notice}</p>
        )}
        {session.read_only && (
          <p className="triage-notice">
            Esta solicitação está finalizada. A conversa permanece disponível
            somente para consulta.
          </p>
        )}

        <OrderDraftPanel
          scope={{ kind: 'triage', id: session.id }}
          readOnly={session.read_only}
        />

        <TriageConversation
          session={session}
          sending={sending}
          sendError={sendError}
          onSend={handleSendMessage}
        />
      </section>
    </AppShell>
  )
}
