// Money arrives as strings from the API (never floats); format, don't do math on it.
export type Money = string

export interface Field {
  id: number
  path: string
  value_json: unknown
  confidence: number
  checker_verdict: 'ok' | 'wrong' | 'unsupported' | null
  checker_reason: string | null
  user_override_json: { value: unknown } | null
  flagged: boolean
}

export interface Cited {
  page: number
  quote: string
  confidence: number
}

export interface Milestone {
  id: number
  seq: number
  title: string
  deliverable: string
  acceptance_criteria: string[]
  amount: Money
  due_date: string | null
  status: 'planned' | 'delivered' | 'accepted' | 'invoiced' | 'paid' | 'disputed'
  clause_id: number | null
}

export interface Party {
  id: number
  role: 'client' | 'agency' | 'subcontractor'
  name: string
  email: string | null
  paypal_email: string | null
  share_pct: Money | null
}

export interface Clause {
  id: number
  kind: string
  page: number
  quote: string
}

export interface Contract {
  id: number
  title: string
  status: 'uploaded' | 'extracted' | 'review' | 'approved' | 'archived'
  currency: string | null
  total_amount: Money | null
  created_at: string
  pages?: number
}

export interface ContractDetail extends Contract {
  extraction_json: Record<string, unknown> & {
    milestones?: { cite: Cited }[]
    parties?: { cite: Cited }[]
    total_cite?: Cited
    net_days_cite?: Cited
    late_fee?: { cite: Cited | null }
    auto_accept_cite?: Cited | null
  }
  fields: Field[]
  open_flags: number
  mandate: { id: number; approved_by: string; approved_at: string; approval_threshold: Money } | null
  milestones: Milestone[]
  parties: Party[]
  payment_terms: {
    net_days: number
    late_fee_type: string
    late_fee_value: Money
    grace_days: number
    late_fee_cap: Money | null
  } | null
  clauses: Clause[]
}

export interface Invoice {
  id: number
  contract_id: number
  milestone_id: number | null
  base_invoice_id: number | null
  kind: 'milestone' | 'late_fee'
  paypal_invoice_id: string | null
  amount: Money
  due_date: string | null
  status: string
  issued_on: string | null
  reminded_on: string | null
  paid_amount: Money | null
}

export interface Payout {
  id: number
  invoice_id: number
  party: string
  email: string
  amount: Money
  status: string
  paypal_batch_id: string | null
}

export interface LedgerRow {
  id: number
  contract_id: number
  contract: string
  currency: string
  ts: string
  type: string
  amount: Money
  ref: string | null
}

export interface GuardEvent {
  id: number
  ts: string
  contract_id: number | null
  actor: string
  action: string
  payload_json: Record<string, unknown>
  decision: 'ALLOW' | 'DENY' | 'NEEDS_APPROVAL'
  rule_ids: string[]
  reason: string
  approved_by: string | null
  resolution: 'pending' | 'approved' | 'rejected' | null
}

export interface Delivery {
  id: number
  notes: string
  links: string[]
  source: string
  created_at: string
  acceptance_json: { meets_criteria: boolean | null; gaps: string[]; summary_for_client: string } | null
}

export interface Dispute {
  id: number
  paypal_dispute_id: string
  contract_id: number | null
  invoice_id: number | null
  reason: string | null
  status: string
  evidence_md: string | null
  proposed_response: string | null
  dry_run: boolean
  submitted_at: string | null
}

export interface ActionResult {
  decision: 'ALLOW' | 'DENY' | 'NEEDS_APPROVAL'
  rule_ids: string[]
  reason: string
  guard_event_id: number
  [k: string]: unknown
}
