# UI translation and user-data boundaries

R16 completed 2026-10-15. Switching language changes presentation, never model artifacts, names, feature arrays, IDs, CSV headers/data or API payloads.

## Rules

- Use explicit typed keys through `t(key)`. Trained-model detail labels, OOF strategy/coverage, regression metric labels, R² tooltips, legacy notices and help text are defined in `trainedModelMessages.ts` and included in the shared catalog.
- Use named values with `t(key, {count, ...})`; substitution is one pass and preserves unknown placeholders. Values are inserted as text and are not retranslated or recursively substituted.
- Render model/feature/target/dataset names directly from data using Vue interpolation. Never call `t(userData)`, scan text nodes, replace body text, or use `v-html` for labels or imported values.
- Do not reuse a training-input label with validation constraints as a neutral detail label. Classification targets may be categorical.
- Canonical model IDs remain the API IDs. Short display/ellipsis and translated copy hints must not alter the copied string.
- Keep translation ownership in components. Element Plus overflow tooltips and explicit raw feature `title` text replace the old global DOM tooltip/translation lifecycle.

The trained-page TreeWalker, reverse translation table, onUpdated text rewriting and global document listeners have been removed. No exclusion selector list is needed to protect child components. Existing native bilingual components retain their own reactive labels; this is not a platform-wide rewrite of every existing inline bilingual message.

## Regression checks

```powershell
cd frontend
npm.cmd test
npm.cmd run build
```

Actual Vue component tests cover repeated zh-TW/en switching with model/feature names equal to UI labels (`狀態`, `發布`, `模型名稱`, `Model Name`), raw target/rename input, all regression metric rows and R² help, legacy notes, safe text rendering, unchanged training request data and full ID copying in both locales. Numeric values/formulas are unchanged.

Use the isolated browser fixture from [Frontend lifecycle](16_Frontend_Lifecycle.md), not a production model:

1. Open model A, switch English/Chinese repeatedly; compare raw feature tags with the chart and original data.
2. Confirm both validation/test Pearson R, R² and the remaining metric rows and supplemental CSV controls remain visible.
3. Open Registry and copy its synthetic ID in both languages. Both must equal `00000000-0000-4000-8000-000000000016`, with translated tooltip/accessible name.
4. Return to Trained Models: selected model and raw rename input remain unchanged. The fixture does not call a real backend or DB.

The fixture intercepts JSON fetch calls and blocks direct XHR uploads, preventing the development proxy from receiving real Prediction files during testing.
