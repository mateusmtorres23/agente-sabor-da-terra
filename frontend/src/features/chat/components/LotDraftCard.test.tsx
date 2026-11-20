import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../../lib/api-client'
import type { OrderRecord } from '../../orders/ordersApi'
import type { Producer } from '../../registry/types'
import * as chatApi from '../chatApi'
import type { LotDraft } from '../types'
import { LotDraftCard } from './LotDraftCard'

vi.mock('../chatApi', () => ({
  updateLotDraft: vi.fn(),
  setLotDraftAvailability: vi.fn(),
  confirmLotDraft: vi.fn(),
}))

const orders: OrderRecord[] = [
  {
    id: 'order-1',
    version: 1,
    session_id: 'session-1',
    buyer: 'Comprador A',
    products: 'Queijo',
    conditions: '',
    delivery_start_date: '2026-11-04',
    delivery_end_date: '2026-11-08',
    cancelled: false,
    needs_item_structuring: false,
    items: [
      {
        id: 'item-1',
        product_id: 'prod-item-1',
        quantity: '100.000',
        unit: 'kg',
        product: { id: 'prod-item-1', name: 'Queijo Coalho' },
      },
    ],
  },
  {
    id: 'order-2',
    version: 1,
    session_id: 'session-1',
    buyer: 'Comprador B',
    products: 'Mel',
    conditions: '',
    delivery_start_date: '2026-12-01',
    delivery_end_date: '2026-12-05',
    cancelled: false,
    needs_item_structuring: false,
    items: [
      {
        id: 'item-2',
        product_id: 'prod-item-2',
        quantity: '50.000',
        unit: 'kg',
        product: { id: 'prod-item-2', name: 'Mel Silvestre' },
      },
    ],
  },
]

const producers: Producer[] = [
  {
    id: 'producer-1',
    code: 'PR-1',
    name: 'Produtor Serra',
    cpf: '12345678901',
    phone: '87999990000',
    email: 'serra@exemplo.test',
    address: 'Sítio Serra, s/n',
    municipality: 'Garanhuns',
    products: [],
    active: true,
  },
]

function makeDraft(overrides: Partial<LotDraft> = {}): LotDraft {
  return {
    id: 'draft-1',
    session_id: 'session-1',
    message_id: 'msg-1',
    order_id: 'order-1',
    item_id: 'item-1',
    producer_id: 'producer-1',
    quantity: '20.000',
    unit: 'kg',
    delivery_date: '2026-11-06',
    availability_confirmed: true,
    needs_date_review: false,
    lot_id: null,
    status: 'em_revisao',
    revision: 1,
    order_deadline: {
      delivery_start_date: '2026-11-04',
      delivery_end_date: '2026-11-08',
      cancelled: false,
    },
    saved_lot: null,
    ...overrides,
  }
}

describe('LotDraftCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('bloqueia confirmação e autorização quando há alterações não salvas e envia expected_revision', async () => {
    const onDraftUpdated = vi.fn()
    const updatedDraft = makeDraft({
      quantity: '15.000',
      availability_confirmed: false,
      revision: 2,
    })
    vi.mocked(chatApi.updateLotDraft).mockResolvedValueOnce(updatedDraft)
    vi.mocked(chatApi.setLotDraftAvailability).mockResolvedValueOnce({
      ...updatedDraft,
      availability_confirmed: true,
      revision: 3,
    })

    render(
      <MemoryRouter>
        <LotDraftCard
          draft={makeDraft()}
          orders={orders}
          producers={producers}
          onDraftUpdated={onDraftUpdated}
        />
      </MemoryRouter>,
    )

    const quantityInput = screen.getByLabelText('Quantidade')
    fireEvent.change(quantityInput, { target: { value: '15.000' } })

    const availabilityButton = screen.getByRole('button', {
      name: 'Confirmar disponibilidade',
    }) as HTMLButtonElement
    const authorizeButton = screen.getByRole('button', {
      name: 'Autorizar cadastro',
    }) as HTMLButtonElement

    expect(availabilityButton.disabled).toBe(true)
    expect(authorizeButton.disabled).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: 'Salvar revisão' }))
    await waitFor(() => {
      expect(chatApi.updateLotDraft).toHaveBeenCalledWith('draft-1', {
        order_id: 'order-1',
        item_id: 'item-1',
        producer_id: 'producer-1',
        quantity: '15.000',
        unit: 'kg',
        delivery_date: '2026-11-06',
      })
    })
    expect(onDraftUpdated).toHaveBeenCalledWith(updatedDraft)
  })

  it('atualiza o prazo ao trocar o pedido e bloqueia autorização quando needs_date_review é verdadeiro', () => {
    render(
      <MemoryRouter>
        <LotDraftCard
          draft={makeDraft({ needs_date_review: true })}
          orders={orders}
          producers={producers}
          onDraftUpdated={vi.fn()}
        />
      </MemoryRouter>,
    )

    expect(screen.getByText(/2026-11-04 a 2026-11-08/)).toBeTruthy()
    const authorizeButton = screen.getByRole('button', {
      name: 'Autorizar cadastro',
    }) as HTMLButtonElement
    expect(authorizeButton.disabled).toBe(true)

    fireEvent.change(screen.getByLabelText('Pedido'), { target: { value: 'order-2' } })
    expect(screen.getByText(/2026-12-01 a 2026-12-05/)).toBeTruthy()
  })

  it('exibe motivo de rejeição detalhado do ApiError incluindo saldo disponível', async () => {
    vi.mocked(chatApi.confirmLotDraft).mockRejectedValueOnce(
      new ApiError(422, {
        detail: 'Quantidade excede o saldo disponível do item (saldo disponível: 5.000 kg).',
      }),
    )

    render(
      <MemoryRouter>
        <LotDraftCard
          draft={makeDraft()}
          orders={orders}
          producers={producers}
          onDraftUpdated={vi.fn()}
        />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Autorizar cadastro' }))

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain(
        'Quantidade excede o saldo disponível do item (saldo disponível: 5.000 kg).',
      )
    })
  })
})
