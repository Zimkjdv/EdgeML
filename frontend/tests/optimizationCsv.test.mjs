import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseFixedCsv, fixedCsvValues } from '../src/optimizationCsv.ts'

const rules = [
  { name: '速度', numeric: true, integer: false, optimize: true },
  { name: '重量', numeric: true, integer: false, optimize: false },
  { name: '紙種', numeric: false, integer: false, optimize: false },
]
test('BOM, quoted commas, escaped quotes, multiline values and CRLF', () => {
  const csv = parseFixedCsv('\uFEFF重量,紙種\r\n20,"A,""B""\nC"\r\n')
  assert.deepEqual(csv.headers, ['重量', '紙種'])
  assert.deepEqual(csv.rows, [['20', 'A,"B"\nC']])
})
test('selected row maps headers, skips adjustable/extra columns, keeps category strings', () => {
  const csv = parseFixedCsv('紙種,重量,速度,Y\n001,20,invalid,99\n002,3e1,ignored,100')
  assert.deepEqual([...fixedCsvValues(csv, 1, rules)], [['重量', 30], ['紙種', '002']])
  assert.equal(rules[0].optimize, true)
})
test('all fixed headers and nonempty valid numbers are required', () => {
  assert.throws(() => fixedCsvValues(parseFixedCsv('重量\n20'), 0, rules), /Missing fixed/)
  for (const value of ['', 'NaN', 'Infinity', '0xff', '1e999']) {
    assert.throws(() => fixedCsvValues(parseFixedCsv(`重量,紙種\n${value},A`), 0, rules))
  }
  assert.throws(() => fixedCsvValues(parseFixedCsv('重量,紙種\n20,A'), 9, rules), /valid data row/)
})
test('integer validation and changing the adjustable selection', () => {
  const csv = parseFixedCsv('重量,紙種\n2.5,A')
  assert.throws(() => fixedCsvValues(csv, 0, rules.map(r => ({ ...r, integer: r.name === '重量' }))), /safe integer/)
  assert.throws(() => fixedCsvValues(csv, 0, rules.map(r => ({ ...r, optimize: false }))), /速度/)
})
test('malformed CSV rejected before applying values', () => {
  for (const text of ['a,a\n1,2', ',b\n1,2', 'a,b\n1', 'a\n"broken', 'a\n"ok"bad', 'a', 'a\n', 'a\nx"y', 'a\n' + 'x'.repeat(1001)]) {
    assert.throws(() => parseFixedCsv(text))
  }
  assert.throws(() => parseFixedCsv('a\n' + '1\n'.repeat(10001)), /10,000/)
})
