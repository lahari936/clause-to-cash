import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, BASE } from '../api/client'
import type { Contract } from '../api/types'
import { Button, buttonClass, Card, Empty, ErrorNote, Loading, money, Pill } from '../components/ui'

// The real order of the product flow, so the numbering carries meaning.
const STEPS: [string, string][] = [
  ['Upload the signed PDF', 'The extractor reads every clause and cites the page it came from.'],
  ['Review the flags', 'A checker verifies each field against only its cited page. Fix or confirm.'],
  ['Approve the mandate', 'The terms freeze. Agents can only act inside them.'],
  ['Deliver, then get invoiced', 'An accepted milestone becomes a PayPal invoice for the exact amount.'],
  ['Get paid, pay your team', 'When the client pays, subcontractor shares go out automatically.'],
]

function DropZone({ file, onFile }: { file: File | null; onFile: (f: File | null) => void }) {
  const [over, setOver] = useState(false)
  return (
    <label
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        const f = e.dataTransfer.files[0]
        if (f?.type === 'application/pdf') onFile(f)
      }}
      className={`flex cursor-pointer flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-4 py-7 text-center transition-colors ${
        over ? 'border-indigo-600 bg-indigo-50' : file ? 'border-emerald-400 bg-emerald-50/60' : 'border-slate-300 bg-slate-50 hover:border-indigo-400 hover:bg-indigo-50/50'
      }`}
    >
      <svg aria-hidden viewBox="0 0 24 24" className={`h-9 w-9 ${file ? 'text-emerald-600' : 'text-indigo-600'}`} fill="none" stroke="currentColor" strokeWidth={1.6}>
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
        <path d="M14 3v5h5" />
        {file ? <path d="m9 14 2 2 4-4" /> : <path d="M12 17v-6m-3 3 3-3 3 3" />}
      </svg>
      {file ? (
        <span className="text-sm">
          <span className="block max-w-[16rem] truncate font-semibold text-pp-navy">{file.name}</span>
          <span className="text-xs text-slate-500">{(file.size / 1024).toFixed(0)} KB · click to change</span>
        </span>
      ) : (
        <span className="text-sm text-slate-600">
          Drag your contract PDF here
          <span className="block text-xs text-slate-400">or</span>
        </span>
      )}
      {!file && <span className={buttonClass('ghost', 'sm')}>Choose PDF</span>}
      <input type="file" accept="application/pdf" className="sr-only" onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
    </label>
  )
}

export default function Contracts() {
  const qc = useQueryClient()
  const list = useQuery({ queryKey: ['contracts'], queryFn: () => api<Contract[]>('/contracts') })
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')

  const upload = useMutation({
    mutationFn: async () => {
      const fd = new FormData()
      fd.append('file', file!)
      fd.append('title', title)
      const c = await api<Contract>('/contracts', { method: 'POST', body: fd })
      return api<Contract>(`/contracts/${c.id}/extract`, { method: 'POST' })
    },
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ['contracts'] })
      location.hash = `#/review/${c.id}`
    },
  })

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-pp-navy sm:text-3xl">Your contracts</h1>
          <p className="mt-1 text-slate-600">Turn signed terms into invoices, late fees and payouts that follow the contract.</p>
        </div>
        <a href="#/copilot" className={buttonClass('ghost')}>
          Ask the copilot
        </a>
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6">
          <Card title="Upload a signed contract">
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault()
                if (file) upload.mutate()
              }}
            >
              <DropZone file={file} onFile={setFile} />
              <label className="block text-sm">
                <span className="font-medium text-slate-700">Title</span> <span className="text-slate-400">(optional)</span>
                <input
                  className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 outline-none transition focus:border-indigo-600 focus:ring-2 focus:ring-indigo-100"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Website redesign for Northwind"
                />
              </label>
              <Button className="w-full" disabled={!file || upload.isPending}>
                {upload.isPending ? (
                  <>
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                    Reading clauses and checking citations…
                  </>
                ) : (
                  'Upload and extract'
                )}
              </Button>
              <ErrorNote error={upload.error} />
            </form>
          </Card>
        </div>

        <div className="space-y-6 lg:col-span-2">
          <Card title="Contracts" right={list.data?.length ? <span className="text-xs text-slate-500">{list.data.length} total</span> : null}>
            {list.isPending ? (
              <Loading />
            ) : list.error ? (
              <ErrorNote error={list.error} />
            ) : !list.data?.length ? (
              <Empty>No contracts yet. Upload a signed PDF to create your first mandate.</Empty>
            ) : (
              <ul className="divide-y divide-slate-100">
                {list.data.map((c) => (
                  <li key={c.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
                    <div className="min-w-0 flex-1">
                      <a href={`#/review/${c.id}`} className="block truncate font-semibold text-pp-navy hover:underline">
                        {c.title}
                      </a>
                      <span className="text-xs text-slate-500">
                        #{c.id} · uploaded {new Date(c.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
                      </span>
                    </div>
                    <Pill value={c.status} />
                    <span className="w-28 text-right font-semibold tabular-nums">{money(c.total_amount, c.currency)}</span>
                    <span className="flex gap-1.5">
                      {c.status === 'approved' ? (
                        <a className={buttonClass('primary', 'sm')} href={`#/contract/${c.id}`}>
                          Operate
                        </a>
                      ) : (
                        <a className={buttonClass('primary', 'sm')} href={`#/review/${c.id}`}>
                          Review
                        </a>
                      )}
                      {c.status === 'approved' && (
                        <a className={buttonClass('ghost', 'sm')} href={`#/review/${c.id}`}>
                          Terms
                        </a>
                      )}
                      <a className={buttonClass('quiet', 'sm')} href={`${BASE}/contracts/${c.id}/pdf`} target="_blank" rel="noreferrer">
                        PDF ↗
                      </a>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="How it gets you paid">
            <ol className="grid gap-3 sm:grid-cols-5">
              {STEPS.map(([head, body], i) => (
                <li key={head} className="relative rounded-xl bg-slate-50 p-3">
                  <span className="mb-2 flex h-7 w-7 items-center justify-center rounded-full bg-pp-navy text-xs font-bold text-white">{i + 1}</span>
                  <span className="block text-sm font-semibold text-pp-navy">{head}</span>
                  <span className="mt-1 block text-xs leading-relaxed text-slate-600">{body}</span>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>
    </div>
  )
}
