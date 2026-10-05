import { parseCsv } from './csv.ts'

export type EvaluationContext = {
  source: 'csv' | 'dataset'; source_name: string; dataset_id: string | null
  input_rows: number; evaluated_rows: number; dropped_rows: number; evaluated_at: string
}
export type EvaluationResult = { metrics: Record<string, number | null>; context?: EvaluationContext | null }
export type ApiRequest = <T>(url: string, init?: RequestInit) => Promise<T>
export type EvaluationInput = { kind: 'csv'; file: File } | { kind: 'dataset'; datasetId: string }

export function validateEvaluationCsv(text: string, features: string[], target: string) {
  const csv = parseCsv(text)
  const missing = [...features, target].filter(name => !csv.headers.includes(name))
  return { rowCount: csv.rows.length, missing }
}

export async function evaluateModel(api: ApiRequest, modelId: string, input: EvaluationInput): Promise<EvaluationResult> {
  const path = `/api/trained-models/${encodeURIComponent(modelId)}`
  if (input.kind === 'csv') {
    const body = new FormData()
    body.append('file', input.file)
    return api<EvaluationResult>(`${path}/evaluate-csv`, { method: 'POST', body })
  }
  return api<EvaluationResult>(`${path}/evaluate`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_id: input.datasetId }) })
}

export function applyEvaluation<T extends { id: string; test_metrics?: Record<string, number | null>; test_rmse?: number | null; test_r2?: number | null; test_evaluation?: EvaluationContext | null }>(
  model: T, modelId: string, result: EvaluationResult): T {
  return model.id === modelId ? { ...model, test_metrics: result.metrics, test_rmse: result.metrics.rmse ?? null,
    test_r2: result.metrics.r2 ?? null, test_evaluation: result.context ?? null } : model
}
