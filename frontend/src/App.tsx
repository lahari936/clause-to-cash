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
    const on = () => {
      setHash(location.hash)
      window.scrollTo({ top: 0 }) // new page starts at the top
    }
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
        className="rounded-full bg-white/10 px-3 py-1 text-white [color-scheme:dark]"
        value={clock.data?.today ?? ''}
        onChange={(e) => set.mutate(e.target.value || null)}
      />
      <button className="rounded-full border border-white/30 px-3 py-1 text-white/90 transition-colors hover:bg-white/10" onClick={() => set.mutate(null)}>
        reset
      </button>
    </label>
  )
}

function useScrolled(): boolean {
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 4)
    addEventListener('scroll', on, { passive: true })
    return () => removeEventListener('scroll', on)
  }, [])
  return scrolled
}

export default function App() {
  const [page, id] = useHash()
  const scrolled = useScrolled()
  const health = useQuery({ queryKey: ['health'], queryFn: () => api<{ ok: boolean }>('/health'), retry: 8, retryDelay: 5000 }) // free tier cold start ~50s
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
      <header className={`z-30 bg-pp-navy text-white transition-shadow duration-300 sm:sticky sm:top-0 ${scrolled ? 'shadow-[0_4px_20px_rgba(0,20,53,0.35)]' : ''}`}>
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <a href="#/" className="text-xl font-bold tracking-tight">
            Clause<span className="text-pp-sky">→</span>Cash
          </a>
          <nav className="-mx-1 flex max-w-full gap-1 overflow-x-auto text-sm [scrollbar-width:none]">
            {NAV.map(([href, label]) => (
              <a
                key={href}
                href={`#/${href}`}
                aria-current={(page ?? '') === href || (href === '' && ['review', 'contract'].includes(page)) ? 'page' : undefined}
                className="relative shrink-0 whitespace-nowrap px-3 py-2 text-white/80 transition-colors hover:text-white aria-[current=page]:font-semibold aria-[current=page]:text-white aria-[current=page]:after:absolute aria-[current=page]:after:inset-x-3 aria-[current=page]:after:-bottom-0.5 aria-[current=page]:after:h-0.5 aria-[current=page]:after:rounded-full aria-[current=page]:after:bg-pp-sky"
              >
                {label}
              </a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-4">
            <DemoClock />
            <span className={`text-xs ${health.data?.ok ? 'text-emerald-400' : 'text-rose-400'}`}>
              ● API {health.isPending ? 'waking up…' : health.data?.ok ? 'online' : 'offline'}
            </span>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <ErrorBoundary key={location.hash}>{body}</ErrorBoundary>
      </main>
      <footer className="pb-6 text-center text-xs text-slate-400">
        PayPal sandbox only · the contract is the policy — the LLM proposes, the Guard disposes
      </footer>
    </div>
  )
}
