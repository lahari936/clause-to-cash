import { Component, type ReactNode } from 'react'
import type { Cited } from '../api/types'

export function money(v: string | null | undefined, currency?: string | null): string {
  if (v == null) return '—'
  // Intl formats the decimal string; no arithmetic happens on the client.
  try {
    return new Intl.NumberFormat(undefined, {
      style: currency ? 'currency' : 'decimal',
      currency: currency ?? undefined,
      minimumFractionDigits: 2,
    }).format(Number(v))
  } catch {
    return `${v} ${currency ?? ''}`
  }
}

const PILL: Record<string, string> = {
  ALLOW: 'bg-emerald-100 text-emerald-800',
  DENY: 'bg-rose-100 text-rose-800',
  NEEDS_APPROVAL: 'bg-amber-100 text-amber-800',
  ok: 'bg-emerald-100 text-emerald-800',
  wrong: 'bg-rose-100 text-rose-800',
  unsupported: 'bg-amber-100 text-amber-800',
  planned: 'bg-slate-100 text-slate-700',
  delivered: 'bg-sky-100 text-sky-800',
  accepted: 'bg-indigo-100 text-indigo-800',
  invoiced: 'bg-violet-100 text-violet-800',
  paid: 'bg-emerald-100 text-emerald-800',
  PAID: 'bg-emerald-100 text-emerald-800',
  SUCCESS: 'bg-emerald-100 text-emerald-800',
  disputed: 'bg-rose-100 text-rose-800',
  SENT: 'bg-violet-100 text-violet-800',
  FAILED: 'bg-rose-100 text-rose-800',
  approved: 'bg-emerald-100 text-emerald-800',
  review: 'bg-amber-100 text-amber-800',
  uploaded: 'bg-slate-100 text-slate-700',
}

export function Pill({ value }: { value: string | null | undefined }) {
  if (!value) return null
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${PILL[value] ?? 'bg-slate-100 text-slate-700'}`}>
      {value.replace('_', ' ')}
    </span>
  )
}

export function CitationChip({ cite, onOpen }: { cite: Cited | null | undefined; onOpen?: (page: number) => void }) {
  if (!cite) return <span className="text-xs text-slate-400">no citation</span>
  return (
    <span className="group relative inline-block">
      <button
        type="button"
        onClick={() => onOpen?.(cite.page)}
        className="rounded border border-slate-300 bg-white px-1.5 py-0.5 text-xs text-slate-700 hover:border-indigo-400 hover:text-indigo-700"
        aria-label={`Citation page ${cite.page}`}
      >
        p.{cite.page} · {Math.round(cite.confidence * 100)}%
      </button>
      <span className="pointer-events-none absolute left-0 top-full z-20 mt-1 hidden w-80 rounded-md border border-slate-200 bg-white p-3 text-xs leading-relaxed text-slate-700 shadow-lg group-hover:block group-focus-within:block">
        <span className="mb-1 block font-semibold text-slate-500">Page {cite.page}</span>“{cite.quote}”
      </span>
    </span>
  )
}

export function Button(props: React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: 'primary' | 'ghost' | 'danger' }) {
  const { tone = 'primary', className = '', ...rest } = props
  const tones = {
    primary: 'bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-slate-300',
    ghost: 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:text-slate-300',
    danger: 'bg-rose-600 text-white hover:bg-rose-700 disabled:bg-slate-300',
  }
  return <button {...rest} className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed ${tones[tone]} ${className}`} />
}

export function Card({ title, children, right }: { title?: ReactNode; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      {(title || right) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
          {right}
        </div>
      )}
      {children}
    </section>
  )
}

export function Loading({ what = 'Loading' }: { what?: string }) {
  return <p className="animate-pulse p-4 text-sm text-slate-500">{what}…</p>
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-md border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">{children}</p>
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null
  return <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-700">{error instanceof Error ? error.message : String(error)}</p>
}

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  render() {
    if (this.state.error)
      return (
        <div className="m-6 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          Something broke on this page: {this.state.error.message}
          <button className="ml-3 underline" onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      )
    return this.props.children
  }
}

export function GuardResult({ r }: { r: { decision: string; rule_ids: string[]; reason: string } | null | undefined }) {
  if (!r) return null
  return (
    <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 p-2 text-sm">
      <Pill value={r.decision} /> <span className="ml-1 font-mono text-xs text-slate-600">{r.rule_ids.join(' ')}</span>
      <div className="mt-1 text-slate-700">{r.reason}</div>
    </div>
  )
}
