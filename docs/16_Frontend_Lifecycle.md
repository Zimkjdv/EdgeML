# Frontend modules and request lifecycle

R15 completed 2026-10-15. The backend contracts and trusted model artifacts are unchanged.

## Module boundaries

- `App.vue`: navigation shell, workspace provider and lazy page imports. Each workspace page lives in `src/pages/`; Optimization keeps its existing standalone component.
- `apiClient.ts`: typed JSON request contract, session/CSRF headers, HTTP status and validation errors, AbortSignal forwarding. The direct prediction CSV upload keeps XHR for real upload progress.
- `useWorkspace`: shared form/resource orchestration, independent from page markup. `workspaceTypes.ts` contains resource types; typed injection avoids prop chains and untyped event buses.
- `useLatestTask`: last-request-wins and cancellation; even a transport that ignores abort cannot apply an obsolete response.
- `useTrainingJob`: serial status polling with bounded retry delay and durable job-ID recovery. `useWorkspaceRoute` preserves the active page in the URL fragment without hijacking native content anchors.

Pages unmount when left; shared form selections remain in memory. Dataset and model details clear during loading, show a loading notice and ignore stale results after another selection, deletion or page change. Renaming/publishing an older selection cannot overwrite the newly selected detail. Queue refresh stops on leave/unmount; prediction uploads are aborted locally on leave/unmount. Aborting the browser does **not** roll back server-side work already accepted.

## Training navigation and refresh

1. A successful submission saves **only its UUID job ID** under `edgeml-training-job-v1` in this origin's localStorage. No CSV, token, feature values or full form is persisted by this mechanism.
2. Leaving Training stops its polling, not the worker. Other pages show a reminder to reopen Training.
3. Refresh preserves the hash page and restores the saved job. On another page, use the reminder; polling resumes only when Training is active. Do not submit the same job again.
4. Completed jobs open their detail only while Training is still active. Failure/cancellation/404 clears the stored job; transient connection errors display a warning and retry with backoff (capped at 15 seconds).
5. If model detail retrieval fails after completion, the job is already terminal: find the model in Trained Models rather than resubmitting. Storage may be disabled; recovery is then limited to the current session.

This tracks one job per browser origin. Local 5173 and Docker 5180 have separate storage. It is not a multi-user job-history system. Files/form contents do not survive refresh. The old trained-page DOM translation remains isolated until R16; it is not considered safe for arbitrary data names yet.

## Verification

```powershell
cd frontend
npm.cmd ci
npm.cmd test
npm.cmd run build
```

`npm test` runs the Node helper/contract tests and actual Vue components in jsdom. Cases cover out-of-order replies, unmount cancellation, rapid row clicks, complete regression metrics/test-upload controls, persisted jobs and pause/resume/retry. These do not replace browser validation.

For a repeatable browser E2E smoke flow, start an **isolated** local Vite and open the synthetic fixture:

```powershell
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5188 --strictPort
# http://127.0.0.1:5188/tests/workspace-e2e.html#datasets
```

The fixture mounts the real App/pages, supplies synthetic datasets/models, delays dataset/model A and intercepts API reads/writes; it does not contact a real backend/DB. It is not a production build entry point. Do not use production credentials or upload real files here.

- Quickly click dataset A then B: only B's detail may remain.
- Open Training, name a model, choose target, submit; observe progress.
- Leave for Prediction: the fixture request counter stops increasing after the page's own list request.
- Click the fixture's completion control, refresh, then reopen Training from the reminder: the completed model detail and CSV test controls appear, without a second submission.
- Repeat fast A/B model-row clicks; inspect full metrics and navigation.

Page chunks are separate, with an error/loading fallback. The shared Element Plus runtime is still large; splitting pages is not a claim that all initial JavaScript or CSS is small. R18/R29 retain broader reproducible dependency/CI work. Newly added Vitest uses a patched release; existing dependency audit warnings must not be hidden or fixed with an unrelated forced major upgrade.

2026-10-15 audit: 0 critical, 5 high findings in existing Vue/server-renderer, brace-expansion, nanoid and source-map-js dependencies. These remain tracked for R18; this change does not claim a clean dependency audit.
