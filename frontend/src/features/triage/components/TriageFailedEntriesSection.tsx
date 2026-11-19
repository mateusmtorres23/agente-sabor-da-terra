import type { FailedTriageEntry } from '../types'

interface TriageFailedEntriesSectionProps {
  entries: FailedTriageEntry[]
  retryingIds: ReadonlySet<string>
  rowErrors: Readonly<Record<string, string>>
  onRetry: (entryId: string) => void
}

function formatReceivedAt(isoDate: string): string {
  const parsed = new Date(isoDate)
  if (Number.isNaN(parsed.getTime())) return isoDate
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
    timeZone: 'America/Recife',
  }).format(parsed)
}

export function TriageFailedEntriesSection({
  entries,
  retryingIds,
  rowErrors,
  onRetry,
}: TriageFailedEntriesSectionProps) {
  if (entries.length === 0) return null

  return (
    <section
      className="triage-failed-section"
      aria-labelledby="triage-failed-heading"
    >
      <div className="triage-failed-header">
        <h2 id="triage-failed-heading">Falhas de triagem</h2>
        <span className="triage-badge" data-urgency="urgente">
          {entries.length === 1 ? '1 falha' : `${entries.length} falhas`}
        </span>
      </div>

      <div className="triage-failed-table-wrapper">
        <table className="triage-failed-table">
          <thead>
            <tr>
              <th scope="col">Remetente</th>
              <th scope="col">Canal</th>
              <th scope="col">Data de recebimento</th>
              <th scope="col">Ação</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => {
              const isProcessing =
                retryingIds.has(entry.id) ||
                entry.triage_status === 'em_processamento'
              const errorMessage = rowErrors[entry.id]

              return (
                <tr key={entry.id}>
                  <td>{entry.sender}</td>
                  <td>{entry.source_channel}</td>
                  <td>{formatReceivedAt(entry.received_at)}</td>
                  <td>
                    {isProcessing ? (
                      <span className="triage-row-processing" role="status">
                        Processando triagem…
                      </span>
                    ) : (
                      <div className="triage-row-action">
                        <button
                          className="triage-button"
                          type="button"
                          onClick={() => onRetry(entry.id)}
                        >
                          Tentar triagem novamente
                        </button>
                        {errorMessage && (
                          <span className="triage-row-error" role="alert">
                            {errorMessage}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}