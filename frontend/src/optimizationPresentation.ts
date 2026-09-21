import type { RuleInput } from './optimizationValidation'

// Explicit API allow-list: presentation metadata must never enter strict request models.
export function parameterPayload(r: RuleInput) {
  return {name: r.name, optimize: r.optimize, value: r.value, minimum: r.minimum,
    maximum: r.maximum, step: r.step, choices: r.choices}
}

export function defaultsCoverage(names: string[], features: Record<string, {value?: unknown}>) {
  return names.filter(name => {
    const value = features[name]?.value
    return typeof value === 'number' ? Number.isFinite(value) : typeof value === 'string' && value.trim() !== ''
  }).length
}

export function convergenceChart(values: number[]) {
  const valid = values.map((value, index) => ({value, iteration: index + 1}))
    .filter(p => Number.isFinite(p.value) && p.value >= 0)
  const maximum = valid.reduce((max, p) => Math.max(max, p.value), 0)
  const scale = maximum || 1
  const points = valid.map(p => ({...p, x: 80 + (p.iteration - 1) / Math.max(1, values.length - 1) * 450,
    y: 170 - p.value / scale * 130}))
  return {maximum, points, line: points.map(p => `${p.x},${p.y}`).join(' ')}
}
