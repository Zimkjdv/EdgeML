export class CsvImportError extends Error {
  zh: string
  constructor(zh: string, en: string) { super(en); this.zh = zh }
}
export type CsvData = { headers: string[]; rows: string[][] }
export type FixedRule = { name: string; numeric: boolean; integer: boolean; optimize: boolean }
const fail = (zh: string, en: string): never => { throw new CsvImportError(zh, en) }

/** Strict CSV parsing: quoted commas/newlines, escaped quotes, BOM and CRLF. */
export function parseFixedCsv(text: string): CsvData {
  text = text.replace(/^\uFEFF/, '')
  const records: string[][] = []
  let row: string[] = [], field = '', quoted = false, closed = false
  function pushField() {
    if (field.length > 1000) fail('CSV 欄位內容不可超過 1000 字元。', 'CSV cells must not exceed 1,000 characters.')
    row.push(field); field = ''; closed = false
    if (row.length > 512) fail('CSV 不可超過 512 欄。', 'CSV must not exceed 512 columns.')
  }
  function pushRow() {
    pushField()
    if (row.some(cell => cell.trim() !== '')) records.push(row)
    row = []
    if (records.length > 10001) fail('CSV 不可超過 10000 筆資料。', 'CSV must not exceed 10,000 data rows.')
  }
  for (let i = 0; i < text.length; i++) {
    const char = text[i]
    if (quoted) {
      if (char === '"') {
        if (text[i + 1] === '"') { field += '"'; i++ } else { quoted = false; closed = true }
      } else field += char
    } else if (char === ',') pushField()
    else if (char === '\n' || char === '\r') { pushRow(); if (char === '\r' && text[i + 1] === '\n') i++ }
    else if (char === '"' && !field && !closed) quoted = true
    else if (closed || char === '"') fail('CSV 引號格式不正確。', 'CSV contains malformed quotes.')
    else field += char
  }
  if (quoted) fail('CSV 引號未關閉。', 'CSV contains an unclosed quoted field.')
  if (field || row.length || closed) pushRow()
  if (records.length < 2) fail('CSV 需要特徵名稱 header 及至少一筆資料。', 'CSV requires feature headers and at least one data row.')
  const headers = records[0].map(value => value.trim())
  if (headers.some(value => !value) || new Set(headers).size !== headers.length) fail('CSV header 不可空白或重複。', 'CSV headers must be nonempty and unique.')
  const rows = records.slice(1)
  if (rows.some(values => values.length !== headers.length)) fail('CSV 每筆資料的欄數必須與 header 一致。', 'Every CSV row must match the header column count.')
  return { headers, rows }
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
