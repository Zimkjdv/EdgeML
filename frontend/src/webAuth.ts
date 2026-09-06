import { ref } from 'vue'
let csrfToken = ''
export const sessionAuthenticated = ref(false)
export function setCsrf(value: string | null) { csrfToken = value || ''; sessionAuthenticated.value = Boolean(csrfToken) }
export function sessionHeaders(): Record<string, string> { return csrfToken ? { 'X-CSRF-Token': csrfToken } : {} }
export function sessionExpired() { window.dispatchEvent(new Event('edgeml-session-expired')) }
export async function logout() {
  const response = await fetch('/api/auth/session', { method: 'DELETE', credentials: 'same-origin', headers: { ...sessionHeaders(), 'X-EdgeML-Login': '1' } })
  if (!response.ok) throw new Error('Logout failed. Please try again.')
  setCsrf(null)
  sessionExpired()
}
