import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, send } from '../api/client'
import type { Cited, ContractDetail, Field } from '../api/types'
import { Button, Card, CitationChip, Empty, ErrorNote, Loading, money, Pill } from '../components/ui'

function citeFor(x: ContractDetail['extraction_json'] | null, path: string): Cited | null | undefined {
  if (!x) return null
  const m = path.match(/^(\w+)\[(\d+)\]$/)
  if (m) return (x[m[1]] as { cite: Cited }[] | undefined)?.[Number(m[2])]?.cite
  if (['currency', 'total_amount', 'deposit_amount'].includes(path)) return x.total_cite
  if (path === 'net_days') return x.net_days_cite
  if (path === 'late_fee') return x.late_fee?.cite
  if (path === 'auto_accept_days') return x.auto_accept_cite
  return null
}

const LABEL: Record<string, string> = {
  currency: 'Currency',
  total_amount: 'Contract total',
  net_days: 'Payment terms (net days)',
  deposit_amount: 'Deposit',
  late_fee: 'Late fee',
  auto_accept_days: 'Deemed acceptance (days)',
  parties: 'Parties (validator)',
}

function label(path: string): string {
  const m = path.match(/^(\w+)\[(\d+)\]$/)
  if (m) return `${m[1] === 'parties' ? 'Party' : 'Milestone'} ${Number(m[2]) + 1}`
  return LABEL[path] ?? path
}

function Value({ v }: { v: unknown }) {
  if (v === null || v === undefined) return <span className="text-slate-400">none</span>
  if (typeof v !== 'object') return <span className="font-medium">{String(v)}</span>
  const o = v as Record<string, unknown>
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-3 text-xs">
      {Object.entries(o).map(([k, val]) => (
        <div key={k} className="contents">
          <dt className="text-slate-500">{k}</dt>
          <dd className="break-words">{Array.isArray(val) ? val.join('; ') : val === null ? '—' : String(val)}</dd>
        </div>
      ))}
    </dl>
  )
}

function FieldRow({ f, cite, contractId, onPage, locked }: { f: Field; cite: Cited | null | undefined; contractId: number; onPage: (p: number, q?: string) => void; locked: boolean }) {
  const qc = useQueryClient()
  const current = f.user_override_json ? f.user_override_json.value : f.value_json
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const save = useMutation({
    mutationFn: (value: unknown) => send(`/contracts/${contractId}/fields/${encodeURIComponent(f.path)}`, 'PATCH', { value }),
    onSuccess: () => {
      setEditing(false)
      qc.invalidateQueries({ queryKey: ['contract', contractId] })
    },
  })
  const [parseErr, setParseErr] = useState('')
  return (
    <tr className={`border-t border-slate-100 align-top ${f.flagged ? 'bg-amber-50' : ''}`}>
      <td className="py-2 pr-3 text-sm font-medium">{label(f.path)}</td>
      <td className="py-2 pr-3 text-sm">
        {editing ? (
          <div className="space-y-1">
            <textarea
              className="h-28 w-full rounded border border-slate-300 p-1 font-mono text-xs"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              aria-label={`Edit ${label(f.path)}`}
            />
            <div className="flex gap-2">
              <Button
                onClick={() => {
                  try {
                    setParseErr('')
                    save.mutate(JSON.parse(draft))
                  } catch {
                    setParseErr('Not valid JSON (strings need "quotes")')
                  }
                }}
              >
                Save
              </Button>
              <Button tone="ghost" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </div>
            <ErrorNote error={parseErr || save.error} />
          </div>
        ) : (
          <Value v={current} />
        )}
        {f.user_override_json && <div className="mt-1 text-xs text-indigo-700">reviewed by you</div>}
      </td>
      <td className="py-2 pr-3">
        <CitationChip cite={cite} onOpen={(p) => onPage(p, cite?.quote)} />
      </td>
      <td className="py-2 pr-3 text-xs">
        <Pill value={f.checker_verdict} />
        {f.confidence < 0.7 && <span className="ml-1 text-amber-700">low confidence</span>}
        <div className="mt-1 max-w-xs text-slate-600">{f.checker_reason}</div>
      </td>
      <td className="whitespace-nowrap py-2 text-right">
        {!editing && !locked && (
          <div className="flex justify-end gap-1">
            {f.flagged && (
              <Button tone="ghost" title="I checked the clause; the value is right" onClick={() => save.mutate(current)}>
                Confirm
              </Button>
            )}
            <Button
              tone="ghost"
              onClick={() => {
                setDraft(JSON.stringify(current, null, 2))
                setEditing(true)
              }}
            >
              Edit
            </Button>
          </div>
        )}
      </td>
    </tr>
  )
}

function PageViewer({ contractId, page, quote }: { contractId: number; page: number; quote?: string }) {
  const q = useQuery({
    queryKey: ['page', contractId, page],
    queryFn: () => api<{ text: string }>(`/contracts/${contractId}/pages/${page}`),
  })
  if (q.isPending) return <Loading what={`Loading page ${page}`} />
  const text = q.data?.text ?? ''
  const norm = (s: string) => s.replace(/\s+/g, ' ')
  const flat = norm(text)
  const i = quote ? flat.indexOf(norm(quote).slice(0, 60)) : -1
  return (
    <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap text-xs leading-relaxed text-slate-700">
      {i < 0 ? (
        flat
      ) : (
        <>
          {flat.slice(0, i)}
          <mark className="bg-yellow-200">{flat.slice(i, i + norm(quote!).length)}</mark>
          {flat.slice(i + norm(quote!).length)}
        </>
      )}
    </pre>
  )
}

export default function Review({ id }: { id: number }) {
  const qc = useQueryClient()
  const c = useQuery({ queryKey: ['contract', id], queryFn: () => api<ContractDetail>(`/contracts/${id}`) })
  const [view, setView] = useState<{ page: number; quote?: string } | null>(null)
  const [by, setBy] = useState('')
  const extract = useMutation({
    mutationFn: () => send(`/contracts/${id}/extract`, 'POST'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contract', id] }),
  })
  const approve = useMutation({
    mutationFn: () => send(`/contracts/${id}/approve`, 'POST', { approved_by: by }),
    onSuccess: () => {
      qc.invalidateQueries()
      location.hash = `#/contract/${id}`
    },
  })
  if (c.isPending) return <Loading what="Loading contract" />
  if (c.error) return <ErrorNote error={c.error} />
  const d = c.data!
  const groups: [string, Field[]][] = [
    ['Payment terms', d.fields.filter((f) => !f.path.includes('['))],
    ['Parties', d.fields.filter((f) => f.path.startsWith('parties['))],
    ['Milestones', d.fields.filter((f) => f.path.startsWith('milestones['))],
  ]
  const approved = d.status === 'approved'

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold">{d.title}</h1>
          <Pill value={d.status} />
          {d.total_amount && <span className="text-sm text-slate-600">{money(d.total_amount, d.currency)}</span>}
          {approved && (
            <a className="ml-auto text-sm text-indigo-700 underline" href={`#/contract/${id}`}>
              Operate this contract →
            </a>
          )}
        </div>
        {!d.fields.length && (
          <Card>
            <Empty>Not extracted yet.</Empty>
            <Button className="mt-3" disabled={extract.isPending} onClick={() => extract.mutate()}>
              {extract.isPending ? 'Extracting…' : 'Run extraction'}
            </Button>
            <ErrorNote error={extract.error} />
          </Card>
        )}
        {groups.map(([title, fs]) =>
          fs.length ? (
            <Card key={title} title={title}>
              <table className="w-full">
                <thead className="text-left text-xs uppercase text-slate-500">
                  <tr>
                    <th className="w-40">Field</th>
                    <th>Value</th>
                    <th>Source</th>
                    <th>Checker</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {fs.map((f) => (
                    <FieldRow key={f.id} f={f} cite={citeFor(d.extraction_json, f.path)} contractId={id} locked={approved} onPage={(page, quote) => setView({ page, quote })} />
                  ))}
                </tbody>
              </table>
            </Card>
          ) : null,
        )}
      </div>
      <div className="space-y-4 lg:sticky lg:top-4 lg:self-start">
        <Card title="Approve mandate">
          {approved ? (
            <p className="text-sm text-emerald-700">
              Approved by {d.mandate?.approved_by}. Agents may now act only inside these terms. Payments above{' '}
              {money(d.mandate?.approval_threshold, d.currency)} need a human click.
            </p>
          ) : (
            <form
              className="space-y-2"
              onSubmit={(e) => {
                e.preventDefault()
                approve.mutate()
              }}
            >
              <p className="text-sm text-slate-600">
                {d.open_flags ? (
                  <span className="font-medium text-amber-700">{d.open_flags} field(s) need review before approval.</span>
                ) : (
                  'All fields verified.'
                )}
              </p>
              <input
                required
                placeholder="Your name"
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                value={by}
                onChange={(e) => setBy(e.target.value)}
              />
              <Button disabled={d.open_flags > 0 || !d.fields.length || approve.isPending} className="w-full">
                Approve mandate
              </Button>
              <ErrorNote error={approve.error} />
            </form>
          )}
        </Card>
        <Card title={view ? `Contract page ${view.page}` : 'Source'}>
          {view ? <PageViewer contractId={id} page={view.page} quote={view.quote} /> : <p className="text-sm text-slate-500">Click a citation chip to see the clause in context.</p>}
        </Card>
      </div>
    </div>
  )
}
