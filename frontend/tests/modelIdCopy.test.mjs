import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import postcss from 'postcss'
import { copyText } from '../src/clipboard.ts'

const modelId = '67f88ae0-ad99-4f5c-b099-16a9c8059756'

function legacyDocument(success = true) {
  const state = { removed: false, restoredFocus: false, selected: false, range: null, copied: null }
  const input = { value: '', readOnly: false, style: {}, focus() {}, select() { state.selected = true },
    setSelectionRange(start, end) { state.range = [start, end] }, remove() { state.removed = true } }
  const savedRange = {}
  const selection = { rangeCount: 1, getRangeAt() { return { cloneRange: () => savedRange } },
    removeAllRanges() {}, addRange(range) { state.restoredRange = range } }
  const document = { activeElement: { focus() { state.restoredFocus = true } }, getSelection: () => selection,
    createElement(tag) { assert.equal(tag, 'textarea'); return input }, body: { appendChild() {} },
    execCommand(command) { assert.equal(command, 'copy'); state.copied = input.value; return success } }
  return { state, document, savedRange }
}

test('modern clipboard copies the entire API ID verbatim, not an abbreviated display value', async () => {
  let copied
  await copyText(modelId, { clipboard: { async writeText(value) { copied = value } },
    document: { createElement() { assert.fail('legacy fallback should not run') } } })
  assert.equal(copied, modelId)
})

test('HTTP clipboard fallback copies full ID and restores focus/selection without residual input', async () => {
  const { document, state, savedRange } = legacyDocument()
  await copyText(modelId, { document })
  assert.equal(state.copied, modelId)
  assert.deepEqual(state.range, [0, modelId.length])
  assert.equal(state.selected, true)
  assert.equal(state.removed, true)
  assert.equal(state.restoredFocus, true)
  assert.equal(state.restoredRange, savedRange)
})

test('clipboard permission rejection falls back; blocked fallback rejects rather than reporting success', async () => {
  const clipboard = { async writeText() { throw new Error('Permission denied') } }
  const allowed = legacyDocument()
  await copyText('中文-id-with-no-quotes', { clipboard, document: allowed.document })
  assert.equal(allowed.state.copied, '中文-id-with-no-quotes')
  const blocked = legacyDocument(false)
  await assert.rejects(copyText(modelId, { clipboard, document: blocked.document }), /blocked/)
  assert.equal(blocked.state.removed, true)
  assert.equal(blocked.state.restoredFocus, true)
})

test('registry binds model ID, not package name; displayed and copied IDs share the same prop', () => {
  const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const table = app.split('<el-table class="registry-table"')[1].split('</el-table>')[0]
  assert.match(table, /prop="id" :label="t\('modelId'\)"/)
  assert.match(table, /<ModelIdCell :model-id="scope\.row\.id"/)
  assert.doesNotMatch(table, /prop="package_name"/)
  const cell = readFileSync(new URL('../src/ModelIdCell.vue', import.meta.url), 'utf8')
  assert.match(cell, /await copyText\(props\.modelId\)/)
  assert.match(cell, /:content="modelId"/)
  assert.match(cell, /\{\{ modelId \}\}/)
  assert.match(cell, /<el-button\b[^>]*:icon="DocumentCopy"[^>]*\/>/)
  assert.match(cell, /:content="t\('copyModelId'\)"/)
  assert.match(cell, /:aria-label="t\('copyModelId'\)"/)
  assert.doesNotMatch(cell, /t\('copy'\)/, 'copy button should be icon-only')
})

test('registry limits ID width while preserving full tooltip/copy text and action space', () => {
  const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const table = app.split('<el-table class="registry-table"')[1].split('</el-table>')[0]
  assert.match(table, /prop="id"[^>]* width="200"/)
  assert.doesNotMatch(table, /prop="id"[^>]*min-width=/, 'ID must not expand into spare table width')
  assert.match(table, /prop="name"[^>]*min-width="180"[^>]*show-overflow-tooltip/)
  assert.match(table, /width="220" class-name="registry-actions-cell"/)
  const component = readFileSync(new URL('../src/ModelIdCell.vue', import.meta.url), 'utf8')
  const rules = postcss.parse(component.split('<style scoped>')[1].split('</style>')[0])
  const declarations = new Map()
  rules.walkRules('.model-id-value', rule => rule.walkDecls(declaration => declarations.set(declaration.prop, declaration.value)))
  assert.equal(declarations.get('min-width'), '0')
  assert.equal(declarations.get('overflow'), 'hidden')
  assert.equal(declarations.get('text-overflow'), 'ellipsis')
  assert.match(component, /await copyText\(props\.modelId\)/)
  assert.match(component, /:content="modelId"/)
})
