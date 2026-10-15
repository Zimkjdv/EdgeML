import { onScopeDispose, ref, watch, type Ref } from 'vue'
import { ApiError } from '../apiClient'
import type { ApiRequest } from '../modelEvaluation'

export const TRAINING_JOB_KEY = 'edgeml-training-job-v1'
type Job = { id: string; status: 'queued'|'running'|'completed'|'failed'|'cancelled'; progress:number; message:string; result_model_id?:string; error?:string }
export function useTrainingJob(api: ApiRequest, enabled: Ref<boolean>, completed: (modelId:string) => Promise<void>, failed: (message:string) => void,
                               storage: Pick<Storage,'getItem'|'setItem'|'removeItem'> = localStorage, interval = 700) {
  const id = ref(''), busy = ref(false), progress = ref(0), message = ref(''), error = ref('')
  let timer: ReturnType<typeof setTimeout> | undefined, controller: AbortController | undefined, revision = 0, disposed = false, failures = 0
  try { const saved = storage.getItem(TRAINING_JOB_KEY); if (saved && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(saved)) id.value = saved } catch { /* storage may be disabled */ }
  busy.value = Boolean(id.value)
  const stop = () => { revision++; clearTimeout(timer); controller?.abort(); controller = undefined }
  const forget = () => { try { storage.removeItem(TRAINING_JOB_KEY) } catch { /* optional persistence */ }; id.value = ''; busy.value = false }
  async function poll() {
    if (!enabled.value || !id.value || disposed) return
    const token = revision, jobId = id.value, active = new AbortController(); controller = active
    try {
      const job = await api<Job>(`/api/training/jobs/${encodeURIComponent(jobId)}`, { signal:active.signal })
      if (token !== revision || active.signal.aborted || !enabled.value) return
      progress.value = job.progress; message.value = job.message; error.value = ''; failures = 0
      if (job.status === 'completed') {
        forget()
        if (job.result_model_id) await completed(job.result_model_id)
        return
      }
      if (job.status === 'failed' || job.status === 'cancelled') { error.value = job.error || job.message; forget(); failed(error.value); return }
    } catch (reason) {
      if (token !== revision || active.signal.aborted || disposed) return
      error.value = reason instanceof Error ? reason.message : String(reason)
      if (reason instanceof ApiError && reason.status === 404) { forget(); failed(error.value); return }
      failures++
    } finally { if (controller === active) controller = undefined }
    if (token === revision && enabled.value && id.value && !disposed) timer = setTimeout(() => void poll(), Math.min(15000, interval * 2 ** Math.min(failures, 4)))
  }
  function attach(jobId:string) {
    if (disposed) return
    stop(); id.value = jobId; busy.value = true; error.value = ''; failures = 0
    try { storage.setItem(TRAINING_JOB_KEY, jobId) } catch { /* optional persistence */ }
  }
  watch([enabled,id], () => { stop(); if (enabled.value && id.value) void poll() }, { immediate:true })
  onScopeDispose(() => { disposed = true; stop() })
  return { id,busy,progress,message,error,attach,stop }
}
