# DECISIONS
| Date | Decision | Reason | Rejected alternative |
|---|---|---|---|
| 2026-10-06 | Client pays agency via Invoicing; agency pays subs via Payouts | No holding of third-party funds; simplest compliant flow | Platform escrow via Orders authorize/capture |
| 2026-10-06 | Guard rules are deterministic Python, LLM only proposes | Money safety + strongest demo story | LLM-judged policy |
| 2026-10-07 | Python 3.13 locally, 3.12 on Render | 3.12 not installed on dev laptop; code uses only 3.12 features | Installing 3.12 just for parity |
| 2026-10-07 | React 19 (Vite template default) instead of 18 | Current Vite template ships 19; TanStack Query + AG Grid support it | Pinning back to 18 |
| 2026-10-07 | Tailwind v4 via `@tailwindcss/vite` | No PostCSS/config files needed | Tailwind v3 + postcss config |
| 2026-10-07 | Local dev Postgres from `pgserver` wheel binaries (port 5433) | Docker Desktop would not start; same major version (16) as Render | Waiting on Docker |
| 2026-10-07 | Gemini provider stubbed (NotImplementedError) | Anthropic is the default; add when needed | Writing an unused impl now |
| 2026-10-07 | Default LLM = Gemini 2.5 Flash (free tier) via REST, Anthropic kept as option | Zero-cost requirement; Anthropic account has no credits | Paid Claude API |
| 2026-10-07 | Recommend Neon free Postgres over Render free Postgres for prod | Render free DB expires after 30 days (before Nov 12 deadline) | Paid Render DB |
| 2026-10-07 | Eval PDFs rendered with PyMuPDF `Story`, not reportlab | PyMuPDF already a dependency | Adding reportlab |
| 2026-10-07 | Disable ligatures in text extraction | PDFs emit "ﬁ" which breaks verbatim quote checks | Normalising after the fact |
| 2026-10-07 | Sections split at page boundaries too | Citations must carry the page the sentence is on, not where its section began | Section-level page only |
| 2026-10-07 | Checker items batched in one call, each with only its own cited page | Free-tier rate limits; still context-starved per field | One call per field |
| 2026-10-07 | Party/milestone reviewed as one object field | Fewer, more meaningful review rows; citation is per object anyway | Per-attribute fields |
| 2026-10-07 | PDF bytes + page texts stored in Postgres | Render free disk is ephemeral | S3/R2 bucket |
| 2026-10-07 | Unverified webhooks are stored but never processed; poll job (60s) syncs invoice/payout status from PayPal | Simulated events can't be verified; truth always re-fetched from PayPal | Processing unverified events |
| 2026-10-07 | Copilot plans with one structured call (tool list), server executes | Same provider path as other agents; works on Gemini free tier | Native multi-turn function calling |
| 2026-10-07 | Copilot told to forward money requests instead of refusing | The Guard is the policy; model refusals hid the enforcement and are not a security boundary | Relying on model refusals |
| 2026-10-07 | Milestone timeline built with CSS instead of Bryntum Gantt | Bryntum trial needs a registry login and has licence watermarks; zero-cost requirement | Bryntum trial |
| 2026-10-07 | `/disputes/demo` creates dry-run disputes | Sandbox disputes on invoice payments are unreliable (plan §12) | Waiting on sandbox |
| 2026-10-07 | MCP server (4.3) cut | Plan cut order #1 | Building it |
| 2026-10-07 | No auth on the API | Hackathon demo on sandbox money only; all money paths still go through the Guard | Adding login for the demo |
