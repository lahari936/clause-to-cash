import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, BASE, send } from '../api/client'
import type { Dispute, Invoice } from '../api/types'
import { Button, Card, Empty, ErrorNote, Loading, money, Pill } from '../components/ui'

export default function Disputes() {
  const qc = useQueryClient()
  const list = useQuery({ queryKey: ['disputes'], queryFn: () => api<Dispute[]>('/disputes') })
  const paid = useQuery({ queryKey: ['invoices', 'all'], queryFn: () => api<Invoice[]>('/invoices') })
  const [invoiceId, setInvoiceId] = useState('')
  const open = useMutation({
    mutationFn: () => send<Dispute>('/disputes/demo', 'POST', { invoice_id: Number(invoiceId) }),
    onSuccess: () => qc.invalidateQueries(),
  })
  const submit = useMutation({
    mutationFn: (id: number) => send<{ status: string }>(`/disputes/${id}/submit`, 'POST', { by: 'agency owner' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['disputes'] }),
  })
  const paidInvoices = paid.data?.filter((i) => i.status === 'PAID' && i.kind === 'milestone') ?? []
  return (
    <div className="space-y-4">
      <Card title="Simulate a client dispute (sandbox dry run)">
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            open.mutate()
          }}
        >
          <select required className="rounded-md border border-slate-300 px-2 py-1.5 text-sm" value={invoiceId} onChange={(e) => setInvoiceId(e.target.value)}>
            <option value="">Pick a paid invoice…</option>
            {paidInvoices.map((i) => (
              <option key={i.id} value={i.id}>
                #{i.id} {i.paypal_invoice_id} · {money(i.amount)}
              </option>
            ))}
          </select>
          <Button disabled={!invoiceId || open.isPending}>{open.isPending ? 'Dispute agent building evidence…' : 'Open dispute'}</Button>
        </form>
        <p className="mt-2 text-xs text-slate-500">
          Real disputes arrive via the <code>CUSTOMER.DISPUTE.CREATED</code> webhook. Sandbox disputes on invoice payments are unreliable, so this
          creates a dry-run dispute that runs the same evidence-pack agent.
        </p>
        <ErrorNote error={open.error} />
      </Card>
      {list.isPending ? (
        <Loading />
      ) : !list.data?.length ? (
        <Empty>No disputes.</Empty>
      ) : (
        list.data.map((d) => (
          <Card
            key={d.id}
            title={
              <span>
                Dispute {d.paypal_dispute_id} {d.dry_run && <span className="normal-case text-amber-700">(dry run)</span>}
              </span>
            }
            right={<Pill value={d.status} />}
          >
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <h3 className="mb-1 text-xs font-semibold uppercase text-slate-500">Evidence pack</h3>
                <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs">{d.evidence_md ?? 'not built'}</pre>
                <a className="mt-2 inline-block text-sm text-indigo-700 underline" href={`${BASE}/disputes/${d.id}/pdf`} target="_blank" rel="noreferrer">
                  Download evidence PDF
                </a>
              </div>
              <div>
                <h3 className="mb-1 text-xs font-semibold uppercase text-slate-500">Proposed response</h3>
                <p className="rounded bg-slate-50 p-3 text-sm">{d.proposed_response}</p>
                <Button className="mt-3" disabled={!!d.submitted_at || submit.isPending} onClick={() => submit.mutate(d.id)}>
                  {d.submitted_at ? 'Submitted' : 'Approve & submit evidence'}
                </Button>
                <ErrorNote error={submit.error} />
              </div>
            </div>
          </Card>
        ))
      )}
    </div>
  )
}
