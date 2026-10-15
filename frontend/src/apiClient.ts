import { sessionHeaders, sessionExpired } from './webAuth'
import type { ApiRequest } from './modelEvaluation'

export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) { super(message); this.name = 'ApiError'; this.status = status }
}

export function createApiClient(fetcher: typeof fetch = (...args) => fetch(...args)): ApiRequest {
  return async <T>(url: string, init?: RequestInit): Promise<T> => {
    const headers = new Headers(init?.headers)
    for (const [key, value] of Object.entries(sessionHeaders())) headers.set(key, value)
    const response = await fetcher(url, { ...init, headers, credentials: 'same-origin' })
    if (response.status === 401) sessionExpired()
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      const detail = typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail)
        ? body.detail.map((item: {msg?:string}) => item.msg || 'Validation error').join('; ') : `HTTP ${response.status}`
      throw new ApiError(detail, response.status)
    }
    return response.status === 204 ? undefined as T : response.json() as Promise<T>
  }
}
