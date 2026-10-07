import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import postcss from 'postcss'
import { TOP_FEATURE_COUNT, visibleImportanceRankings } from '../src/featureImportanceView.ts'

const rankings = Array.from({ length: 20 }, (_, index) => ({
  rank: index + 1, feature: `中文特徵 ${index}`, importance: 0.1 - index * 0.01, std: 0.002,
}))

test('compact view defaults to top ten without changing the complete report', () => {
  const snapshot = structuredClone(rankings)
  assert.equal(TOP_FEATURE_COUNT, 10)
  assert.deepEqual(visibleImportanceRankings(rankings, false), rankings.slice(0, 10))
  assert.deepEqual(rankings, snapshot)
})

test('show-all retains every feature including negative importance', () => {
  assert.deepEqual(visibleImportanceRankings(rankings, true), rankings)
  assert.ok(visibleImportanceRankings(rankings, true).at(-1).importance < 0)
  assert.deepEqual(visibleImportanceRankings(rankings.slice(0, 3), false), rankings.slice(0, 3))
  assert.deepEqual(visibleImportanceRankings([], false), [])
})

test('card fills the detail-card width while keeping a compact chart and accessible toggle', () => {
  const component = readFileSync(new URL('../src/FeatureImportance.vue', import.meta.url), 'utf8')
  const css = postcss.parse(component.match(/<style scoped>([\s\S]*?)<\/style>/)[1])
  const properties = selector => {
    const result = {}
    css.walkRules(selector, rule => rule.walkDecls(decl => { result[decl.prop] = decl.value }))
    return result
  }
  assert.equal(properties('.feature-importance').width, '100%')
  assert.equal(properties('.feature-importance')['max-width'], 'none')
  assert.equal(properties('.importance-chart')['max-height'], '360px')
  assert.equal(properties('.importance-track').height, '12px')
  assert.match(component, /v-for="row in visibleRankings"/)
  assert.match(component, /:aria-expanded="showAll"/)
  assert.match(component, /:aria-controls="chartId"/)
  // The scale always uses the complete report, so the zero axis does not jump.
  assert.match(component, /report\.value\?\.rankings\.map/)
  assert.match(component, /@media \(max-width: 650px\)/)
})
