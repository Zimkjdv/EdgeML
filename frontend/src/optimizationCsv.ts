import { parseCsv, type CsvData } from './csv.ts'
export type { CsvData } from './csv.ts'

export class CsvImportError extends Error {
  zh: string
  constructor(zh: string, en: string) { super(en); this.zh = zh }
}
export type FixedRule = { name: string; numeric: boolean; integer: boolean; optimize: boolean }
const fail = (zh: string, en: string): never => { throw new CsvImportError(zh, en) }

/** Strict CSV parsing: quoted commas/newlines, escaped quotes, BOM and CRLF. */
export function parseFixedCsv(text: string): CsvData {
  try {
    const csv = parseCsv(text, { maxRows: 10000, maxColumns: 512, maxCellChars: 1000 })
    csv.headers = csv.headers.map(value => value.trim())
    if (new Set(csv.headers).size !== csv.headers.length) fail('CSV header 不可重複。', 'CSV headers must be unique.')
    return csv
  } catch (error) {
    if (error instanceof CsvImportError) throw error
    return fail('CSV 格式或大小不符合匯入要求。', error instanceof Error ? error.message : 'Invalid CSV.')
  }
}

/** Validate the entire selected row before returning any updates. */
export function fixedCsvValues(csv: CsvData, rowIndex: number, rules: FixedRule[]): Map<string, string | number> {
  const values = csv.rows[rowIndex]
  if (!values) fail('請選擇有效的資料列。', 'Select a valid data row.')
  const fixed = rules.filter(rule => !rule.optimize)
  if (!fixed.length) fail('目前沒有固定參數可匯入。', 'There are no fixed features to import.')
  const missing = fixed.filter(rule => !csv.headers.includes(rule.name)).map(rule => rule.name)
  if (missing.length) fail(`缺少固定參數欄位：${missing.join('、')}`, `Missing fixed feature columns: ${missing.join(', ')}`)
  const result = new Map<string, string | number>()
  for (const rule of fixed) {
    const value = values[csv.headers.indexOf(rule.name)].trim()
    if (!value) fail(`固定參數「${rule.name}」不可空白。`, `Fixed feature "${rule.name}" must not be empty.`)
    if (rule.numeric) {
      const number = Number(value)
      if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value) || !Number.isFinite(number) || (rule.integer && !Number.isSafeInteger(number))) {
        fail(`「${rule.name}」必須是有效的${rule.integer ? '整數' : '數值'}。`, `"${rule.name}" must be a valid ${rule.integer ? 'safe integer' : 'finite number'}.`)
      }
      result.set(rule.name, number)
    } else result.set(rule.name, value)
  }
  return result
}
