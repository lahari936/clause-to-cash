import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ColDef } from 'ag-grid-community'
import { AllCommunityModule, ModuleRegistry } from 'ag-grid-community'
import { AgGridReact } from 'ag-grid-react'
import { useMemo, useState } from 'react'
import { api, send } from '../api/client'
import type { ActionResult, GuardEvent } from '../api/types'
import { Button, Card, Empty, ErrorNote, GuardResult, Loading, money, Pill } from '../components/ui'

ModuleRegistry.registerModules([AllCommunityModule])

const RULES: Record<string, string> = {
  G1: 'Approved mandate exists',
  G2: 'Payee is a mandate party',
  G3: 'Currency matches mandate',
  G4: 'Exact milestone amount, milestone accepted',
  G5: 'Cumulative invoiced ≤ contract total',
  G6: 'Contract-correct late fee, only after grace',
  G7: 'Exact revenue share, only after PAID',
  G8: 'No duplicate action',
  G9: 'Above threshold needs a human',
  G10: 'Free-text request must trace to a mandate rule',
}

function Approvals() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['pending'], queryFn: () => api<GuardEvent[]>('/guard/events?pending=true'), refetchInterval: 10000 })
  const [result, setResult] = useState<ActionResult | null>(null)
  const act = useMutation({
    mutationFn: ({ id, verb }: { id: number; verb: 'approve' | 'reject' }) => send<ActionResult>(`/guard/events/${id}/${verb}`, 'POST', { by: 'agency owner' }),
    onSuccess: (r) => {
      if (r && 'decision' in r) setResult(r)
      qc.invalidateQueries()
    },
  })
  if (!q.data?.length && !result) return null
  return (
    <Card title="Waiting for your approval">
      <ul className="space-y-2">
        {q.data?.map((e) => (
          <li key={e.id} className="flex flex-wrap items-center gap-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm">
            <span className="font-medium">{e.action.replace(/_/g, ' ')}</span>
            <span className="tabular-nums">{money(String(e.payload_json.amount), String(e.payload_json.currency))}</span>
            <span className="text-slate-600">to {String(e.payload_json.recipient)}</span>
            <span className="text-xs text-slate-500">{e.reason}</span>
            <span className="ml-auto flex gap-2">
              <Button onClick={() => act.mutate({ id: e.id, verb: 'approve' })} disabled={act.isPending}>
                Approve
              </Button>
              <Button tone="ghost" onClick={() => act.mutate({ id: e.id, verb: 'reject' })} disabled={act.isPending}>
                Reject
              </Button>
            </span>
          </li>
        ))}
      </ul>
      <GuardResult r={result} />
      <ErrorNote error={act.error} />
    </Card>
  )
}

export default function GuardLog() {
  const q = useQuery({ queryKey: ['guard'], queryFn: () => api<GuardEvent[]>('/guard/events'), refetchInterval: 10000 })
  const [sel, setSel] = useState<GuardEvent | null>(null)
  const cols = useMemo<ColDef<GuardEvent>[]>(
    () => [
      { field: 'ts', headerName: 'When', valueFormatter: (p) => new Date(p.value).toLocaleString(), width: 180, sort: 'desc' },
      { field: 'actor', filter: true, width: 160 },
      { field: 'action', filter: true, width: 160 },
      {
        headerName: 'Amount',
        width: 130,
        type: 'rightAligned',
        valueGetter: (p) => p.data?.payload_json.amount as string,
        valueFormatter: (p) => money(p.value, p.data?.payload_json.currency as string),
      },
      { field: 'decision', filter: true, width: 150, cellRenderer: (p: { value: string }) => <Pill value={p.value} /> },
      { field: 'rule_ids', headerName: 'Rules', width: 130, valueFormatter: (p) => (p.value as string[]).join(' ') },
      { field: 'reason', flex: 1, tooltipField: 'reason' },
    ],
    [],
  )
  const counts = (q.data ?? []).reduce<Record<string, number>>((a, e) => ({ ...a, [e.decision]: (a[e.decision] ?? 0) + 1 }), {})
  return (
    <div className="space-y-4">
      <Approvals />
      <div className="flex flex-wrap gap-3 text-sm">
        {(['ALLOW', 'DENY', 'NEEDS_APPROVAL'] as const).map((k) => (
          <div key={k} className="rounded-lg border border-slate-200 bg-white px-4 py-2 shadow-sm">
            <Pill value={k} /> <span className="ml-1 text-lg font-semibold">{counts[k] ?? 0}</span>
          </div>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <Card title="Every money action, checked against the mandate">
          {q.isPending ? (
            <Loading />
          ) : q.error ? (
            <ErrorNote error={q.error} />
          ) : !q.data?.length ? (
            <Empty>No guard decisions yet.</Empty>
          ) : (
            <div style={{ height: 520 }}>
              <AgGridReact<GuardEvent>
                rowData={q.data}
                columnDefs={cols}
                defaultColDef={{ sortable: true, resizable: true }}
                rowSelection={{ mode: 'singleRow', checkboxes: false, enableClickSelection: true }}
                onRowClicked={(e) => setSel(e.data ?? null)}
                getRowStyle={(p) => (p.data?.decision === 'DENY' ? { background: '#fff1f2' } : undefined)}
              />
            </div>
          )}
        </Card>
        <div className="space-y-4">
          <Card title={sel ? `Event #${sel.id}` : 'Details'}>
            {sel ? (
              <div className="space-y-2 text-sm">
                <div>
                  <Pill value={sel.decision} /> by <b>{sel.actor}</b>
                  {sel.approved_by && <span> · approved by {sel.approved_by}</span>}
                </div>
                <p className="text-slate-700">{sel.reason}</p>
                <pre className="overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-100">{JSON.stringify(sel.payload_json, null, 2)}</pre>
              </div>
            ) : (
              <p className="text-sm text-slate-500">Click a row to see the proposed action payload.</p>
            )}
          </Card>
          <Card title="Rules">
            <ul className="space-y-1 text-xs">
              {Object.entries(RULES).map(([k, v]) => (
                <li key={k}>
                  <span className="font-mono font-semibold">{k}</span> {v}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  )
}
