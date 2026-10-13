export type Confusion = { labels: (string | number | boolean)[]; matrix: number[][]; sample_count: number; binary?: { negative_label: string | number | boolean; positive_label: string | number | boolean; tn: number; fp: number; fn: number; tp: number } | null }
export type Provenance = { version: string; data: { dataset_id: string; name: string; sha256: string; input_rows: number; column_count: number; role: string }[]; runtime: Record<string, string | null>; resolved_parameters: Record<string, unknown>; validation: Record<string, unknown>; target_column: string; feature_columns: string[] }
export type ModelListItem = { id: string; name: string; completed_at: string; target_column: string; algorithm: string; problem_type: string; status: 'draft' | 'published'; validation_r2?: number | null; validation_rmse?: number | null; test_r2?: number | null; test_rmse?: number | null; validation_accuracy?: number | null; validation_f1?: number | null; test_accuracy?: number | null; test_f1?: number | null }
export type Preview = { dataset_id: string; columns: string[]; rows: (string | number | boolean | null)[][]; total_rows: number; offset: number; limit: number }

export function scoreKeys(problem: string, test = false) {
  const prefix = test ? 'test_' : 'validation_'
  return problem === 'classification' ? [prefix + 'accuracy', prefix + 'f1'] : [prefix + 'r2', prefix + 'rmse']
}

export function previewRange(page: Preview) {
  return page.rows.length ? `${page.offset + 1}–${page.offset + page.rows.length} / ${page.total_rows}` : `0 / ${page.total_rows}`
}
