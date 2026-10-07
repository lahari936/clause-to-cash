import { useQuery } from '@tanstack/react-query'
import { api } from './api/client'

export default function App() {
  const health = useQuery({ queryKey: ['health'], queryFn: () => api<{ ok: boolean }>('/health') })
  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-3xl font-semibold">Clause-to-Cash</h1>
      <p className="mt-2 text-gray-600">The contract is the policy.</p>
      <p className="mt-6 text-sm">
        API:{' '}
        {health.isPending ? 'checking…' : health.data?.ok ? (
          <span className="text-green-700">online</span>
        ) : (
          <span className="text-red-700">offline</span>
        )}
      </p>
    </main>
  )
}
