import { useQuery } from '@tanstack/react-query'
import type { ColDef } from 'ag-grid-community'
import { AllCommunityModule, ModuleRegistry } from 'ag-grid-community'
import { AgGridReact } from 'ag-grid-react'
import { useMemo } from 'react'
import { api } from '../api/client'
import type { LedgerRow } from '../api/types'
import { Card, Empty, ErrorNote, Loading, money } from '../components/ui'

ModuleRegistry.registerModules([AllCommunityModule])

const TYPE_STYLE: Record<string, string> = {
  invoice_sent: '#6d28d9',
  payment_received: '#047857',
  late_fee: '#b45309',
  payout_sent: '#0369a1',
  payout_done: '#0f766e',
  dispute: '#be123c',
  refund: '#be123c',
}

export default function Ledger() {
  const q = useQuery({ queryKey: ['ledger'], queryFn: () => api<LedgerRow[]>('/ledger'), refetchInterval: 15000 })
  const cols = useMemo<ColDef<LedgerRow>[]>(
    () => [
      { field: 'ts', headerName: 'When', valueFormatter: (p) => new Date(p.value).toLocaleString(), sort: 'desc', width: 190 },
      { field: 'contract', filter: true, flex: 1 },
      {
        field: 'type',
        filter: true,
        width: 170,
        cellRenderer: (p: { value: string }) => (
          <span style={{ color: TYPE_STYLE[p.value] ?? '#334155', fontWeight: 600 }}>{p.value.replace('_', ' ')}</span>
        ),
      },
      {
        field: 'amount',
        type: 'rightAligned',
        width: 150,
        valueFormatter: (p) => money(p.value, p.data?.currency),
        comparator: (a: string, b: string) => Number(a) - Number(b),
      },
      { field: 'ref', headerName: 'Reference', flex: 1, filter: true },
    ],
    [],
  )
  // Totals per type, summed on the server's decimal strings by cents to avoid float drift.
  const totals = useMemo(() => {
    const t: Record<string, bigint> = {}
    for (const r of q.data ?? []) {
      const [w, f = ''] = r.amount.split('.')
      t[r.type] = (t[r.type] ?? 0n) + BigInt(w) * 100n + BigInt((f + '00').slice(0, 2)) * (w.startsWith('-') ? -1n : 1n)
    }
    return Object.entries(t).map(([type, c]) => ({ type, amount: `${c / 100n}.${String(c % 100n).padStart(2, '0')}` }))
  }, [q.data])

  if (q.isPending) return <Loading what="Loading ledger" />
  if (q.error) return <ErrorNote error={q.error} />
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        {totals.map((t) => (
          <div key={t.type} className="rounded-lg border border-slate-200 bg-white px-4 py-2 shadow-sm">
            <div className="text-xs uppercase text-slate-500">{t.type.replace('_', ' ')}</div>
            <div className="text-lg font-semibold tabular-nums" style={{ color: TYPE_STYLE[t.type] }}>
              {money(t.amount)}
            </div>
          </div>
        ))}
      </div>
      <Card title="Ledger">
        {!q.data?.length ? (
          <Empty>No money has moved yet.</Empty>
        ) : (
          <div style={{ height: 520 }}>
            <AgGridReact<LedgerRow> rowData={q.data} columnDefs={cols} defaultColDef={{ sortable: true, resizable: true }} pagination paginationPageSize={50} />
          </div>
        )}
      </Card>
    </div>
  )
}
