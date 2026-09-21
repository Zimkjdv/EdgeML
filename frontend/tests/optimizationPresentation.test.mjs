import test from 'node:test'
import assert from 'node:assert/strict'
import {parameterPayload, defaultsCoverage, convergenceChart} from '../src/optimizationPresentation.ts'

test('request excludes category-truncation and UI-only flags', () => {
  const payload = parameterPayload({name:'紙種', numeric:false, integer:false, optimize:true, value:'A', minimum:null, maximum:null, step:null, choices:['A'], choices_truncated:true})
  assert.deepEqual(Object.keys(payload).sort(), ['choices','maximum','minimum','name','optimize','step','value'])
  assert.deepEqual(payload.choices, ['A'])
})
test('defaults coverage distinguishes empty, partial, zero and unrelated defaults', () => {
  assert.equal(defaultsCoverage(['A','B'], {}), 0)
  assert.equal(defaultsCoverage(['A','B'], {A:{value:0}, C:{value:1}}), 1)
  assert.equal(defaultsCoverage(['A','B'], {A:{value:NaN}, B:{value:' '}}), 0)
  assert.equal(defaultsCoverage(['A','B'], {A:{value:0}, B:{value:'紙'}}), 2)
})
test('convergence scales small errors and renders single or all-zero points', () => {
  const chart = convergenceChart([0.00002,0.00001,0])
  assert.equal(chart.points[0].y,40)
  assert.equal(chart.points[2].y,170)
  assert.equal(chart.points[2].x,530)
  assert.equal(convergenceChart([0]).points.length,1)
  assert.equal(convergenceChart([0,0]).maximum,0)
  assert.deepEqual(convergenceChart([]).points,[])
  assert.equal(convergenceChart([NaN,1]).points[0].iteration,2)
})
