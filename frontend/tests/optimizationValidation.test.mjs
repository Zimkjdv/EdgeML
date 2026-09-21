import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ruleErrors } from '../src/optimizationValidation.ts'
const rule = {name:'車速', numeric:true, integer:false, optimize:true, value:0.2, minimum:0.1, maximum:0.3, step:0.1, choices:[]}
test('valid decimal bounds and optional baseline', () => {
  assert.deepEqual(ruleErrors(rule, true), [])
  assert.deepEqual(ruleErrors({...rule, step:.2}, true), [])
  assert.deepEqual(ruleErrors({...rule, value:null}, false), [])
  assert.deepEqual(ruleErrors({...rule, value:null}, true), ['value'])
})
test('invalid bounds, steps and integer values', () => {
  assert.ok(ruleErrors({...rule, maximum:0}, false).includes('bounds'))
  assert.ok(ruleErrors({...rule, step:0}, false).includes('step'))
  assert.ok(ruleErrors({...rule, integer:true}, true).includes('value'))
  assert.ok(ruleErrors({...rule, step:Infinity}, false).includes('step'))
})
test('fixed values and categories cannot be empty', () => {
  assert.deepEqual(ruleErrors({...rule, optimize:false, value:null}, false), ['value'])
  assert.deepEqual(ruleErrors({...rule, numeric:false, choices:[' ']}, false), ['choices'])
  assert.deepEqual(ruleErrors({...rule, numeric:false, choices:['A'], value:'A'}, true), [])
})
