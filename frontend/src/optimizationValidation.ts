export type RuleInput = {name: string; numeric: boolean; integer: boolean; optimize: boolean; value: unknown; minimum: number | null; maximum: number | null; step: number | null; choices: string[]}
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const exceedsSpan = (step: number, low: number, high: number) => step-(high-low) > Number.EPSILON * Math.max(Math.abs(low), Math.abs(high), Math.abs(step)) * 4
export function ruleErrors(r: RuleInput, baseline: boolean): string[] {
  const errors: string[] = []
  if (!r.optimize || baseline) {
    if (r.numeric ? !finite(r.value) || r.integer && !Number.isInteger(r.value) : typeof r.value !== 'string' || !r.value.trim() || r.value.length > 1000) errors.push('value')
  }
  if (r.optimize && r.numeric) {
    if (!finite(r.minimum) || !finite(r.maximum) || !Number.isFinite(r.maximum-r.minimum) || r.minimum >= r.maximum || r.integer && (!Number.isInteger(r.minimum) || !Number.isInteger(r.maximum))) errors.push('bounds')
    if (r.step != null && (!finite(r.step) || r.step <= 0 || r.integer && !Number.isInteger(r.step) || finite(r.minimum) && finite(r.maximum) && (exceedsSpan(r.step, r.minimum, r.maximum) || (r.maximum-r.minimum)/r.step > 1e9))) errors.push('step')
    if (r.step == null && r.integer && finite(r.minimum) && finite(r.maximum) && r.maximum-r.minimum > 1e9) errors.push('step')
  }
  if (r.optimize && !r.numeric && (!r.choices.length || r.choices.length > 100 || r.choices.some(v => !v.trim() || v.length > 1000))) errors.push('choices')
  return errors
}
