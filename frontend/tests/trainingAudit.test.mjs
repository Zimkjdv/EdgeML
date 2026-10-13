import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { scoreKeys, previewRange } from '../src/trainingAudit.ts'
import { applyEvaluation } from '../src/modelEvaluation.ts'

test('classification summaries use accuracy and F1, regression keeps R² and RMSE', () => {
  assert.deepEqual(scoreKeys('classification'), ['validation_accuracy','validation_f1'])
  assert.deepEqual(scoreKeys('regression', true), ['test_r2','test_rmse'])
  const list = readFileSync(new URL('../src/TrainedModelList.vue', import.meta.url), 'utf8')
  assert.match(list, /RMSE \/ F1/)
  assert.match(list, /R² \/ Accuracy/)
  assert.match(list, /problem_type === filter\.value/)
  assert.match(list, /typeof value === 'number'/)
})

test('later tests update only test scores and matrices for the matching model', () => {
  const validation = { accuracy: 0.8 }, previous = { labels:['甲','乙'], matrix:[[2,1],[0,3]], sample_count:6 }
  const model = { id:'one', validation_metrics:validation, validation_confusion:previous }
  const result = { metrics:{accuracy:0.9,f1:0.88}, confusion:previous, context:null }
  const updated = applyEvaluation(model, 'one', result)
  assert.equal(updated.validation_metrics, validation)
  assert.equal(updated.validation_confusion, previous)
  assert.equal(updated.test_confusion, previous)
  assert.equal(updated.test_accuracy, 0.9)
  assert.equal(applyEvaluation(model, 'two', result), model)
})

test('dataset preview range, bounded paging and stale-response guards', () => {
  assert.equal(previewRange({offset:50,rows:[['中文'],['另一列']],total_rows:102}), '51–52 / 102')
  assert.equal(previewRange({offset:100,rows:[],total_rows:0}), '0 / 0')
  const component = readFileSync(new URL('../src/DatasetPreview.vue', import.meta.url), 'utf8')
  assert.match(component, /limit=50/)
  assert.match(component, /current === revision && id === props\.datasetId/)
  assert.match(component, /onUnmounted\(\(\) => \{ revision\+\+ \}\)/)
  assert.ok(!component.includes('v-html'))
})

test('new native i18n components cannot be mutated by legacy text replacement or hide regression details', () => {
  const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  assert.match(app, /\.training-audit, \.classification-evaluation, \.trained-model-list/)
  assert.match(app, /<ClassificationEvaluation/)
  assert.match(app, /<DatasetPreview/)
  assert.match(app, /<TrainingProvenance/)
  assert.match(app, /驗證 相關係數 Pearson R/)
  assert.match(app, /class="result-card unified-model-detail"/)
})
