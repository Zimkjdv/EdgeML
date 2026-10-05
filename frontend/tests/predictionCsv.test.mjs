import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parseCsv, predictionCsvStats, csvNaValues } from '../src/csv.ts'

const cases = JSON.parse(readFileSync(new URL('../../backend/tests/fixtures/prediction_csv_cases.json', import.meta.url), 'utf8'))
test('frontend and backend share CSV row-count and NA contract', () => {
  assert.deepEqual(csvNaValues, cases.na_values)
  for (const data of cases.valid) {
    const csv = parseCsv(data.csv)
    const stats = predictionCsvStats(csv, data.required.map(name => ({ name, required: true })), data.truth)
    assert.equal(stats.totalRows, data.total)
    assert.equal(stats.missingRows, data.dropped)
    assert.equal(stats.predictedRows, data.total - data.dropped)
  }
})
test('malformed CSV rejected, missing headers reported, optional fields ignored', () => {
  for (const text of cases.invalid) assert.throws(() => parseCsv(text))
  const csv = parseCsv('x,extra\n1,\n2,\n')
  assert.deepEqual(predictionCsvStats(csv, [{ name: 'missing', required: true }]).missingColumns, ['missing'])
  assert.equal(predictionCsvStats(csv, [{ name: 'x', required: true }, { name: 'optional', required: false }]).missingRows, 0)
})
