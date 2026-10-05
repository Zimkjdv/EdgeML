import test from 'node:test'
import assert from 'node:assert/strict'
import { evaluateModel, validateEvaluationCsv, applyEvaluation } from '../src/modelEvaluation.ts'

test('test CSV requires all training features and ground truth, supports Chinese multiline', () => {
  const result = validateEvaluationCsv('數值,類別,目標\n1,"甲\n乙",2\n', ['數值', '類別'], '目標')
  assert.equal(result.rowCount, 1)
  assert.deepEqual(result.missing, [])
  assert.deepEqual(validateEvaluationCsv('數值,類別\n1,甲\n', ['數值', '類別'], '目標').missing, ['目標'])
})
test('CSV evaluation uploads multipart, existing dataset uses original JSON endpoint', async () => {
  const calls = [], result = { metrics: { rmse: .1, r2: .9 } }
  const api = async (path, init) => { calls.push({ path, init }); return result }
  const file = new File(['x,y\n1,2\n'], '中文測試.csv', { type: 'text/csv' })
  assert.equal(await evaluateModel(api, 'model-1', { kind: 'csv', file }), result)
  assert.equal(calls[0].path, '/api/trained-models/model-1/evaluate-csv')
  assert.equal(calls[0].init.body.get('file').name, file.name)
  assert.equal(calls[0].init.headers, undefined)
  await evaluateModel(api, 'model-1', { kind: 'dataset', datasetId: 'data-1' })
  assert.equal(calls[1].path, '/api/trained-models/model-1/evaluate')
  assert.deepEqual(JSON.parse(calls[1].init.body), { dataset_id: 'data-1' })
})
test('evaluation updates test detail and summary without changing validation or another selected model', () => {
  const model = { id: 'first', validation_metrics: { r2: .8 }, validation_r2: .8, test_r2: null, test_rmse: null }
  const result = { metrics: { rmse: .1, r2: .9, pearson_r: .95 }, context: { source_name: 'test.csv' } }
  const updated = applyEvaluation(model, 'first', result)
  assert.equal(updated.validation_metrics, model.validation_metrics)
  assert.equal(updated.validation_r2, .8)
  assert.equal(updated.test_r2, .9)
  assert.equal(updated.test_rmse, .1)
  assert.equal(updated.test_metrics, result.metrics)
  assert.equal(updated.test_evaluation, result.context)
  assert.equal(applyEvaluation(model, 'other', result), model)
})
