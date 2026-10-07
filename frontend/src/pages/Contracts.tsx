import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, BASE } from '../api/client'
import type { Contract } from '../api/types'
import { Button, Card, Empty, ErrorNote, Loading, money, Pill } from '../components/ui'

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
    <div className="grid gap-4 lg:grid-cols-3">
      <Card title="Upload a signed contract">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (file) upload.mutate()
          }}
        >
          <label className="block text-sm">
            <span className="text-slate-600">Contract PDF</span>
            <input
              type="file"
              accept="application/pdf"
              required
              className="mt-1 block w-full text-sm"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <label className="block text-sm">
            <span className="text-slate-600">Title (optional)</span>
            <input
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Website redesign for Northwind"
            />
          </label>
          <Button disabled={!file || upload.isPending}>
            {upload.isPending ? 'Extracting & checking clauses…' : 'Upload and extract'}
          </Button>
          <ErrorNote error={upload.error} />
          <p className="text-xs text-slate-500">
            An extractor agent reads every clause with citations, then a context-starved checker verifies each field against
            only its cited page. You approve; the approved terms become the Mandate.
          </p>
        </form>
      </Card>
      <div className="lg:col-span-2">
        <Card title="Contracts">
          {list.isPending ? (
            <Loading />
          ) : list.error ? (
            <ErrorNote error={list.error} />
          ) : !list.data?.length ? (
            <Empty>No contracts yet. Upload one, or run <code>python scripts/seed_demo.py</code>.</Empty>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-1">Title</th>
                  <th>Status</th>
                  <th className="text-right">Total</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.data.map((c) => (
                  <tr key={c.id} className="border-t border-slate-100">
                    <td className="py-2 font-medium">{c.title}</td>
                    <td>
                      <Pill value={c.status} />
                    </td>
                    <td className="text-right tabular-nums">{money(c.total_amount, c.currency)}</td>
                    <td className="space-x-3 text-right">
                      <a className="text-indigo-700 hover:underline" href={`#/review/${c.id}`}>
                        Review
                      </a>
                      {c.status === 'approved' && (
                        <a className="text-indigo-700 hover:underline" href={`#/contract/${c.id}`}>
                          Operate
                        </a>
                      )}
                      <a className="text-slate-500 hover:underline" href={`${BASE}/contracts/${c.id}/pdf`} target="_blank" rel="noreferrer">
                        PDF
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  )
}
