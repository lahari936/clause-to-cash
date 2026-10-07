const RAW = (import.meta.env.VITE_API_URL as string | undefined) || 'http://localhost:8000'
// Render's fromService passes a bare host name; add the scheme when it's missing.
export const BASE = RAW.startsWith('http') ? RAW : `https://${RAW}`

export class ApiError extends Error {}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init)
  if (!res.ok) {
    let msg = `${res.status}`
    try {
      const body = await res.json()
      msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch {
      msg = `${res.status} ${res.statusText}`
    }
    throw new ApiError(msg)
  }
  return res.json() as Promise<T>
}

export function send<T>(path: string, method: 'POST' | 'PATCH', body?: unknown): Promise<T> {
  return api<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}
