import { onScopeDispose, ref } from 'vue'

export function useLatestTask() {
  let revision = 0, controller: AbortController | undefined
  const pending = ref(false)
  const cancel = () => { revision++; controller?.abort(); controller = undefined; pending.value = false }
  const current = () => revision
  async function run<T>(request: (signal: AbortSignal) => Promise<T>, commit: (value: T) => void) {
    cancel()
    const token = revision, active = new AbortController()
    controller = active; pending.value = true
    try {
      const value = await request(active.signal)
      if (token === revision && !active.signal.aborted) { commit(value); return value }
    } catch (error) {
      if (token === revision && !active.signal.aborted) throw error
    } finally { if (token === revision) { pending.value = false; controller = undefined } }
  }
  onScopeDispose(cancel)
  return { run, cancel, current, pending }
}
