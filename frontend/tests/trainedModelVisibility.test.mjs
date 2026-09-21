import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import postcss from 'postcss'

test('optional cards cannot hide trained-model details by sibling order', () => {
  const css = postcss.parse(readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8'))
  const positionalHiding = []
  css.walkRules(rule => {
    if (!rule.selector.includes('.trained-models-page') || !/:nth-(?:of-type|child)/.test(rule.selector)) return
    rule.walkDecls(declaration => {
      if ((declaration.prop === 'display' && declaration.value === 'none') ||
          (declaration.prop === 'visibility' && declaration.value === 'hidden')) {
        positionalHiding.push(rule.selector)
      }
    })
  })
  assert.deepEqual(positionalHiding, [], 'Detail, classification and rename cards must remain visible regardless of optional-card order')
})
