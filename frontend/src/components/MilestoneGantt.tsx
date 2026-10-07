import type { Milestone } from '../api/types'
import { money } from './ui'

const COLOR: Record<Milestone['status'], string> = {
  planned: 'bg-slate-300',
  delivered: 'bg-sky-400',
  accepted: 'bg-indigo-500',
  invoiced: 'bg-violet-500',
  paid: 'bg-emerald-500',
  disputed: 'bg-rose-500',
}
const DAY = 86_400_000

/** Lightweight Gantt: each milestone runs from the previous due date to its own. */
export default function MilestoneGantt({ milestones, start, today, currency }: { milestones: Milestone[]; start: string; today: string; currency: string | null }) {
  const dated = milestones.filter((m) => m.due_date)
  if (!dated.length) return <p className="text-sm text-slate-500">No due dates in the contract.</p>
  const t0 = Math.min(Date.parse(start), Date.parse(today))
  const t1 = Math.max(...dated.map((m) => Date.parse(m.due_date!)), Date.parse(today)) + 7 * DAY
  const pct = (t: number) => `${((t - t0) / (t1 - t0)) * 100}%`
  const months: number[] = []
  for (let d = new Date(t0); d.getTime() <= t1; d = new Date(d.getFullYear(), d.getMonth() + 1, 1)) {
    if (d.getTime() >= t0) months.push(d.getTime())
  }
  let prev = Date.parse(start)
  return (
    <div className="relative">
      <div className="relative mb-1 h-5 border-b border-slate-200 text-[10px] text-slate-500">
        {months.map((m) => (
          <span key={m} className="absolute -translate-x-1/2" style={{ left: pct(m) }}>
            {new Date(m).toLocaleDateString(undefined, { month: 'short', year: '2-digit' })}
          </span>
        ))}
      </div>
      <div className="space-y-2">
        {milestones.map((m) => {
          const end = m.due_date ? Date.parse(m.due_date) : prev + 14 * DAY
          const from = Math.min(prev, end - 3 * DAY)
          prev = end
          return (
            <div key={m.id} className="relative h-8">
              <div
                className={`absolute top-0 flex h-8 items-center overflow-hidden rounded px-2 text-xs font-medium text-white shadow-sm ${COLOR[m.status]}`}
                style={{ left: pct(from), width: `calc(${pct(end)} - ${pct(from)})`, minWidth: '6rem' }}
                title={`${m.title} · ${money(m.amount, currency)} · due ${m.due_date} · ${m.status}`}
              >
                <span className="truncate">
                  M{m.seq} {m.title} · {m.status}
                </span>
              </div>
            </div>
          )
        })}
      </div>
      <div className="pointer-events-none absolute bottom-0 top-0 w-px bg-rose-500" style={{ left: pct(Date.parse(today)) }}>
        <span className="absolute -top-1 left-1 text-[10px] font-semibold text-rose-600">today</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-slate-600">
        {Object.entries(COLOR).map(([s, c]) => (
          <span key={s} className="flex items-center gap-1">
            <span className={`inline-block h-2.5 w-2.5 rounded-sm ${c}`} />
            {s}
          </span>
        ))}
      </div>
    </div>
  )
}
