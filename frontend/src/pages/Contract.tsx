import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, send } from '../api/client'
import type { ActionResult, ContractDetail, Delivery, Invoice, Milestone, Payout } from '../api/types'
import MilestoneGantt from '../components/MilestoneGantt'
import { Button, buttonClass, Card, Empty, ErrorNote, GuardResult, Loading, money, Pill } from '../components/ui'

function DeliverForm({ m, onDone }: { m: Milestone; onDone: () => void }) {
  const [notes, setNotes] = useState('')
  const [links, setLinks] = useState('')
  const deliver = useMutation({
    mutationFn: () =>
      send(`/milestones/${m.id}/deliveries`, 'POST', {
        notes,
        links: links.split(/\s+/).filter(Boolean),
      }),
    onSuccess: onDone,
  })
  return (
    <form
      className="mt-2 space-y-2 rounded-md border border-sky-200 bg-sky-50 p-3"
      onSubmit={(e) => {
        e.preventDefault()
        deliver.mutate()
      }}
    >
      <textarea
        required
        className="h-20 w-full rounded border border-slate-300 p-2 text-sm"
        placeholder="What was delivered? The acceptance agent checks this against the criteria."
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      <input
        className="w-full rounded border border-slate-300 p-2 text-sm"
        placeholder="Links (space separated): Figma, staging URL, PR…"
        value={links}
        onChange={(e) => setLinks(e.target.value)}
      />
      <Button disabled={deliver.isPending}>{deliver.isPending ? 'Reviewing evidence…' : 'Mark delivered'}</Button>
      <ErrorNote error={deliver.error} />
    </form>
  )
}

function MilestoneCard({ m, currency }: { m: Milestone; currency: string | null }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [result, setResult] = useState<ActionResult | null>(null)
  const deliveries = useQuery({
    queryKey: ['deliveries', m.id],
    queryFn: () => api<Delivery[]>(`/milestones/${m.id}/deliveries`),
    enabled: m.status !== 'planned',
  })
  const accept = useMutation({
    mutationFn: () => send<ActionResult>(`/milestones/${m.id}/accept`, 'POST', { by: 'agency' }),
    onSuccess: (r) => {
      setResult(r)
      qc.invalidateQueries()
    },
    onError: () => qc.invalidateQueries(),
  })
  const last = deliveries.data?.[0]
  const acc = last?.acceptance_json
  return (
    <div className="rounded-md border border-slate-200 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">
          M{m.seq}. {m.title}
        </span>
        <Pill value={m.status} />
        <span className="ml-auto tabular-nums">{money(m.amount, currency)}</span>
      </div>
      <p className="mt-1 text-sm text-slate-600">
        {m.deliverable} · due {m.due_date ?? 'n/a'}
      </p>
      <ul className="mt-1 list-inside list-disc text-xs text-slate-500">
        {m.acceptance_criteria.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      {acc && (
        <div className="mt-2 rounded bg-slate-50 p-2 text-xs">
          <span className="font-semibold">Acceptance agent:</span>{' '}
          {acc.meets_criteria === null ? 'unavailable' : acc.meets_criteria ? '✓ meets criteria' : '✗ gaps found'}
          {acc.gaps.length > 0 && <span className="text-rose-700"> — {acc.gaps.join('; ')}</span>}
          <div className="mt-1 text-slate-600">{acc.summary_for_client}</div>
        </div>
      )}
      <div className="mt-2 flex gap-2">
        {(m.status === 'planned' || m.status === 'delivered') && (
          <Button tone="ghost" onClick={() => setOpen(!open)}>
            {m.status === 'planned' ? 'Mark delivered' : 'Add delivery'}
          </Button>
        )}
        {(m.status === 'delivered' || m.status === 'accepted') && (
          <Button tone="pay" disabled={accept.isPending} onClick={() => accept.mutate()}>
            {accept.isPending ? 'Invoicing via PayPal…' : m.status === 'accepted' ? 'Retry invoice' : 'Accept & invoice'}
          </Button>
        )}
      </div>
      {open && (
        <DeliverForm
          m={m}
          onDone={() => {
            setOpen(false)
            qc.invalidateQueries()
          }}
        />
      )}
      <GuardResult r={result} />
      <ErrorNote error={accept.error} />
    </div>
  )
}

export default function ContractPage({ id }: { id: number }) {
  const qc = useQueryClient()
  const c = useQuery({ queryKey: ['contract', id], queryFn: () => api<ContractDetail>(`/contracts/${id}`) })
  const invoices = useQuery({ queryKey: ['invoices', id], queryFn: () => api<Invoice[]>(`/invoices?contract_id=${id}`), refetchInterval: 15000 })
  const payouts = useQuery({ queryKey: ['payouts'], queryFn: () => api<Payout[]>('/payouts'), refetchInterval: 15000 })
  const clock = useQuery({ queryKey: ['clock'], queryFn: () => api<{ today: string }>('/demo/clock') })
  const collections = useMutation({
    mutationFn: () => send<{ actions: (ActionResult & { kind: string; invoice_id: number; message?: string; error?: string })[] }>('/collections/run', 'POST'),
    onSuccess: () => qc.invalidateQueries(),
  })
  const sync = useMutation({
    mutationFn: (invId: number) => send(`/invoices/${invId}/sync`, 'POST'),
    onSuccess: () => qc.invalidateQueries(),
  })
  if (c.isPending) return <Loading what="Loading contract" />
  if (c.error) return <ErrorNote error={c.error} />
  const d = c.data!
  if (d.status !== 'approved')
    return (
      <Empty>
        Approve the mandate first. <a className={`ml-2 ${buttonClass('primary', 'sm')}`} href={`#/review/${id}`}>Go to review</a>
      </Empty>
    )
  const invIds = new Set(invoices.data?.map((i) => i.id))
  const t = d.payment_terms
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-pp-navy sm:text-3xl">{d.title}</h1>
        <Pill value={d.status} />
        <span className="text-sm text-slate-600">{money(d.total_amount, d.currency)}</span>
        <a className={`ml-auto ${buttonClass('ghost', 'sm')}`} href={`#/review/${id}`}>
          Terms & citations
        </a>
      </div>
      <Card title="Milestones">
        <MilestoneGantt milestones={d.milestones} start={d.created_at.slice(0, 10)} today={clock.data?.today ?? new Date().toISOString().slice(0, 10)} currency={d.currency} />
      </Card>
      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="space-y-3">
          {d.milestones.map((m) => (
            <MilestoneCard key={m.id} m={m} currency={d.currency} />
          ))}
        </div>
        <div className="space-y-4">
          <Card title="Mandate">
            <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-sm">
              {d.parties.map((p) => (
                <div key={p.id} className="contents">
                  <dt className="text-slate-500">{p.role}</dt>
                  <dd>
                    {p.name}
                    {p.share_pct && <span className="text-indigo-700"> · {p.share_pct}%</span>}
                    <div className="truncate text-xs text-slate-500">{p.paypal_email}</div>
                  </dd>
                </div>
              ))}
              {t && (
                <>
                  <dt className="text-slate-500">terms</dt>
                  <dd>net {t.net_days} days</dd>
                  <dt className="text-slate-500">late fee</dt>
                  <dd>
                    {t.late_fee_type === 'none'
                      ? 'none'
                      : `${t.late_fee_value}${t.late_fee_type.startsWith('pct') ? '%' : ` ${d.currency}`} ${t.late_fee_type === 'pct_monthly' ? '/month' : ''} after ${t.grace_days}d grace${t.late_fee_cap ? `, cap ${money(t.late_fee_cap, d.currency)}` : ''}`}
                  </dd>
                </>
              )}
              <dt className="text-slate-500">approval</dt>
              <dd>human click above {money(d.mandate?.approval_threshold, d.currency)}</dd>
            </dl>
          </Card>
          <Card
            title="Collections"
            right={
              <Button tone="ghost" disabled={collections.isPending} onClick={() => collections.mutate()}>
                Run now
              </Button>
            }
          >
            <p className="text-xs text-slate-500">Overdue invoices get a reminder; after due date + grace a contract-correct late fee is invoiced. Fast-forward with the clock in the header.</p>
            {collections.data && (
              <ul className="mt-2 space-y-2 text-sm">
                {collections.data.actions.length === 0 && <li className="text-slate-500">Nothing overdue on {clock.data?.today}.</li>}
                {collections.data.actions.map((a, i) => (
                  <li key={i} className="rounded bg-slate-50 p-2">
                    <span className="font-medium">{a.kind.replace(/_/g, ' ')}</span> on invoice #{a.invoice_id} <Pill value={a.decision} />
                    {a.error && <div className="text-rose-700">{a.error}</div>}
                    {a.message && <div className="mt-1 text-xs italic text-slate-600">“{a.message}”</div>}
                  </li>
                ))}
              </ul>
            )}
            <ErrorNote error={collections.error} />
          </Card>
        </div>
      </div>
      <Card title="PayPal invoices">
        {!invoices.data?.length ? (
          <Empty>No invoices yet. Accept a delivered milestone to invoice it.</Empty>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr>
                <th>#</th>
                <th>Kind</th>
                <th>PayPal id</th>
                <th className="text-right">Amount</th>
                <th>Due</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {invoices.data.map((i) => (
                <tr key={i.id} className="border-t border-slate-100">
                  <td className="py-1.5">{i.id}</td>
                  <td>{i.kind === 'late_fee' ? `late fee on #${i.base_invoice_id}` : `M${d.milestones.find((m) => m.id === i.milestone_id)?.seq}`}</td>
                  <td className="font-mono text-xs">{i.paypal_invoice_id ?? '—'}</td>
                  <td className="text-right tabular-nums">{money(i.amount, d.currency)}</td>
                  <td>{i.due_date}</td>
                  <td>
                    <Pill value={i.status} />
                  </td>
                  <td className="text-right">
                    {i.status === 'SENT' && (
                      <button className={buttonClass('ghost', 'sm')} onClick={() => sync.mutate(i.id)}>
                        check PayPal
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <ErrorNote error={sync.error} />
      </Card>
      <Card title="Subcontractor payouts">
        {!payouts.data?.filter((p) => invIds.has(p.invoice_id)).length ? (
          <Empty>Payouts are sent automatically when the client pays a milestone invoice.</Empty>
        ) : (
          <table className="w-full text-sm">
            <tbody>
              {payouts.data
                .filter((p) => invIds.has(p.invoice_id))
                .map((p) => (
                  <tr key={p.id} className="border-t border-slate-100">
                    <td className="py-1.5">{p.party}</td>
                    <td className="text-xs text-slate-500">{p.email}</td>
                    <td>invoice #{p.invoice_id}</td>
                    <td className="text-right tabular-nums">{money(p.amount, d.currency)}</td>
                    <td className="text-right">
                      <Pill value={p.status} />
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
