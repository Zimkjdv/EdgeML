/** Shared CSV reader for prediction previews and optimization imports. */
export type CsvData = { headers: string[]; rows: string[][] }
export const csvNaValues = ['', '#N/A', '#N/A N/A', '#NA', '-1.#IND', '-1.#QNAN', '-NaN', '-nan', '1.#IND', '1.#QNAN', '<NA>', 'N/A', 'NA', 'NULL', 'NaN', 'None', 'n/a', 'nan', 'null']

export function parseCsv(text: string, limits: { maxRows?: number; maxColumns?: number; maxCellChars?: number } = {}): CsvData {
  text = text.replace(/^\uFEFF/, '')
  const records: string[][] = []
  let row: string[] = [], field = '', quoted = false, closed = false, syntax = false
  function pushField() {
    if (limits.maxCellChars && field.length > limits.maxCellChars) throw new Error(`CSV cell exceeds ${limits.maxCellChars.toLocaleString('en-US')} characters.`)
    row.push(field); field = ''; closed = false
    if (limits.maxColumns && row.length > limits.maxColumns) throw new Error(`CSV exceeds ${limits.maxColumns} columns.`)
  }
  function pushRow() {
    pushField()
    // A blank physical line is skipped; ",," and quoted empty cells are data.
    if (syntax || row.some(cell => cell.trim() !== '')) records.push(row)
    row = []; syntax = false
    if (limits.maxRows && records.length > limits.maxRows + 1) throw new Error(`CSV exceeds ${limits.maxRows.toLocaleString('en-US')} rows.`)
  }
  for (let i = 0; i < text.length; i++) {
    const char = text[i]
    if (quoted) {
      if (char === '"') {
        if (text[i + 1] === '"') { field += '"'; i++ } else { quoted = false; closed = true }
      } else field += char
    } else if (char === ',') { syntax = true; pushField() }
    else if (char === '\n' || char === '\r') { pushRow(); if (char === '\r' && text[i + 1] === '\n') i++ }
    else if (char === '"' && !field && !closed) { quoted = true; syntax = true }
    else if (closed || char === '"') throw new Error('CSV contains malformed quotes.')
    else field += char
  }
  if (quoted) throw new Error('CSV contains an unclosed quoted field.')
  if (field || row.length || closed) pushRow()
  if (records.length < 2) throw new Error('CSV requires headers and at least one data row.')
  const headers = records[0]
  if (headers.some(value => !value.trim()) || new Set(headers).size !== headers.length) throw new Error('CSV headers must be nonempty and unique.')
  const rows = records.slice(1)
  if (rows.some(values => values.length !== headers.length)) throw new Error('Every CSV row must match the header column count.')
  return { headers, rows }
}

export function predictionCsvStats(csv: CsvData, features: { name: string; required: boolean }[], groundTruth = '') {
  const required = [...features.filter(f => f.required).map(f => f.name), ...(groundTruth ? [groundTruth] : [])]
  const missingColumns = required.filter(name => !csv.headers.includes(name))
  if (missingColumns.length) return { totalRows: csv.rows.length, missingRows: 0, predictedRows: 0, missingColumns }
  const indices = required.map(name => csv.headers.indexOf(name))
  const missingRows = csv.rows.filter(row => indices.some(index => csvNaValues.includes(row[index]))).length
  return { totalRows: csv.rows.length, missingRows, predictedRows: csv.rows.length - missingRows, missingColumns }
}
