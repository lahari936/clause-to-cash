import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, send } from './api/client'
import { ErrorBoundary } from './components/ui'
import ContractPage from './pages/Contract'
import Contracts from './pages/Contracts'
import Copilot from './pages/Copilot'
import Disputes from './pages/Disputes'
import GuardLog from './pages/GuardLog'
import Ledger from './pages/Ledger'
import Review from './pages/Review'

function useHash(): string[] {
  const [hash, setHash] = useState(location.hash)
  useEffect(() => {
    const on = () => setHash(location.hash)
    addEventListener('hashchange', on)
    return () => removeEventListener('hashchange', on)
  }, [])
  return hash.replace(/^#\/?/, '').split('/').filter(Boolean)
}

const NAV = [
  ['', 'Contracts'],
  ['ledger', 'Ledger'],
  ['guard', 'Guard log'],
  ['disputes', 'Disputes'],
  ['copilot', 'Copilot'],
]

function DemoClock() {
  const qc = useQueryClient()
  const clock = useQuery({ queryKey: ['clock'], queryFn: () => api<{ today: string }>('/demo/clock') })
  const set = useMutation({
    mutationFn: (today: string | null) => send<{ today: string }>('/demo/clock', 'POST', { today }),
    onSuccess: () => qc.invalidateQueries(),
  })
  return (
    <label className="flex items-center gap-2 text-xs text-slate-300" title="Demo clock: fast-forward time for late fees">
      Today
      <input
        type="date"
        className="rounded bg-slate-800 px-2 py-1 text-slate-100"
        value={clock.data?.today ?? ''}
        onChange={(e) => set.mutate(e.target.value || null)}
      />
      <button className="underline" onClick={() => set.mutate(null)}>
        reset
      </button>
    </label>
  )
}

export default function App() {
  const [page, id] = useHash()
  const health = useQuery({ queryKey: ['health'], queryFn: () => api<{ ok: boolean }>('/health'), retry: 1 })
  let body
  if (page === 'review' && id) body = <Review id={Number(id)} />
  else if (page === 'contract' && id) body = <ContractPage id={Number(id)} />
  else if (page === 'ledger') body = <Ledger />
  else if (page === 'guard') body = <GuardLog />
  else if (page === 'disputes') body = <Disputes />
  else if (page === 'copilot') body = <Copilot />
  else body = <Contracts />

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="bg-slate-900 text-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <a href="#/" className="text-lg font-semibold">
            Clause<span className="text-indigo-400">→</span>Cash
          </a>
          <nav className="flex flex-wrap gap-1 text-sm">
            {NAV.map(([href, label]) => (
              <a
                key={href}
                href={`#/${href}`}
                className={`rounded px-2 py-1 hover:bg-slate-700 ${(page ?? '') === href || (href === '' && ['review', 'contract'].includes(page)) ? 'bg-slate-700' : ''}`}
              >
                {label}
              </a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-4">
            <DemoClock />
            <span className={`text-xs ${health.data?.ok ? 'text-emerald-400' : 'text-rose-400'}`}>
              ● API {health.isPending ? '…' : health.data?.ok ? 'online' : 'offline'}
            </span>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl p-4">
        <ErrorBoundary key={location.hash}>{body}</ErrorBoundary>
      </main>
      <footer className="pb-6 text-center text-xs text-slate-400">
        PayPal sandbox only · the contract is the policy — the LLM proposes, the Guard disposes
      </footer>
    </div>
  )
}
