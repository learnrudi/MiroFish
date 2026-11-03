# Bounded native OASIS run controls

## Phase 0: Baseline And Manual Lookup

- Base: `486b95ed00e53d7f73da0d43f37bbe7d2eb559be`, PR #3's recorded stream.
- Worktree: `mirofish-native-controls`, branch `feat/oasis-native-controls`.
- PR #2 is merged at `6bdf586`; local main and Admin main adopted it. PR #3 is
  still draft; this change is stacked on it, not permission to merge it.
- Inspected: OASIS group/follow-up exchanges, exact decision validation, Flask
  factory, native launch/import evidence scripts, frontend stream/parser.
- Manual: index; API standard E2/E3/E5/E7; agent co-pilot standard; testing
  Appendix C; horizontal engineering standard.
- Risk: **high**, because a browser approval can admit a trusted native job on
  another execution host. This is a loopback-only operator interface, not a
  production multi-user service.
- Horizontal scan: existing harness owns request capture, decisions and OASIS
  application. Existing artifact scripts own historical proof, not a reusable
  service. Consolidate new operational use into one Compute adapter, reuse the
  harness, and share the recorded feed component. Do not create another model
  API shim or duplicate legacy simulation execution. General model-provider
  integration remains a separate future change owned by the MiroFish maintainer.

## Phase 1: Scope Lock

- In scope: three fixed personas, the same price-change scenario, exactly two
  rounds, native codex-hoff with the previously selected model/effort; prepare,
  exact review, approve, queued/running status, verified application, feed.
- Each round requires its own review. Round two's context does not exist until
  round one succeeds. A terminally failed native job may have one fresh retry
  after a new review; successful agents are never rerun for that retry.
- Non-goals: ontology/profile/config generation, other models/accounts/actions,
  threaded replies, reports/interviews, Zep changes, deployment, general loops.
- Files: `backend/app/agent_runners/native_*`, native API/entrypoint, bounded
  Flask-factory wiring, focused backend tests; frontend native API/view, shared
  recorded feed, router, focused tests; this plan and operator guide.
- Trust boundaries: operator-owned target config only; browser cannot supply
  paths, shell, model, identity or prompts. Loopback Host/origin checks and a
  per-process request token protect native endpoints. No tokens in URLs/logs.
- Durable state: SQLite, explicit states/revisions and events, client request
  UUID idempotency retained for the life of the store. One coordinator process
  owns the store; local process ownership is locked. One active run at a time.
- Native IDs/keys are deterministic per run/round/agent/attempt. Transport
  ambiguity reconciles the existing job and same key. A new attempt is allowed
  only after an authoritative terminal failure and another exact review.
- Reviewed bytes and source fingerprint must remain unchanged. Native outputs
  require receipt/hash/account/model/effort checks before OASIS validation.
- Partial application is preserved and cannot be blindly replayed. A complete
  result can be reconciled after a restart; ambiguous partial state fails closed.
- Authorized: local implementation/tests/preview, inactive native preparation,
  the established feature-branch publication/review workflow. Live inference
  requires approval of the concrete newly prepared review. No new merge or
  Admin adoption of unaccepted feature code is authorized.
- Commit slices: coordinator/adapter and contract tests; API/frontend and tests;
  final documentation/proof. Each slice must pass its focused checks.

## Phase 2: Red Tests

- Build one observable behavior at a time: duplicate Start; approval binding;
  two-round progression; failed-agent retry; ambiguous admission; recovery;
  request auth/boundaries; actual OASIS application; frontend control states.
- Record red/green commands and observed failures here as they run.

## Phase 3: Implementation

- Shared interfaces: engine `prepare/apply`, Compute `prepare/inspect/admit`,
  store `create/get/save` with revision checks, coordinator state transitions.
- API returns stable error codes and public snapshots. Full review is a
  separate read; private receipts and runtime data remain outside Git.
- Emit durable run events with run/round/agent/job identifiers and transitions.
- No automatic fallback, retries with new keys, or execution before approval.

## Phase 4: Green Tests And Refactor

- Reuse the pinned backend environment and existing harness; no dependency
  changes. Refactor only after focused tests pass.
- Verify shared feed component still renders the existing recorded view.

## Phase 5: Full Verification

- Focused coordinator/adapter/API tests, existing backend suite, frontend
  tests/build, JS debt scan, whitespace checks.
- Browser: prepare/review/status controls, repeated Start, failed job/retry,
  final feed using deterministic test transport; clearly label test transport.
- Independent read-only Standards/Spec/Proof review in fresh context.
- Prepare the real inactive codex-hoff round-one tasks and expose exact review
  in the UI. Do not press Approve on the user's behalf without its approval.
- Live happy-path proof remains pending until that concrete approval is given.

## Phase 6: Docs, Contracts, And Closure

- Update operator/API contracts, state transitions, retry semantics, model/API
  limits and launch instructions; record source/runtime evidence separately.
- Preserve task worktree with a closeout receipt; do not clean/delete it.
- Definition of Done: implemented and verified bounded controls; no unresolved
  independent findings; exact live approval pending is explicit, not completion
  of live execution. Publication, merge, Admin adoption and deployment are
  separate statuses.
- Current status: implementation and local verification complete; concrete native
  preparation and its final Proof confirmation follow the clean source checkpoint.

## Implementation proof ledger (in progress)

- Commands below run from `backend` with the existing group-worktree Python.
- `pytest tests/test_native_coordinator.py -q --tb=short`: red duplicate Start
  produced four IDs; green one durable ID under four concurrent requests.
- Same command: red remained preparing; green both separately approved rounds.
- Same command: red remained running after Bob failure; green preserved Alice
  and Casey, one new Bob attempt and a fresh review; repeated retry is idempotent.
- Same command: red propagated lost admission reply; green restart reconciles
  the existing task without another admission. Source drift red queued -> green
  failed closed. Coordinator refactor reran all five green.
- `pytest tests/test_native_engine.py -q --tb=short`: red repeated application
  failed on existing DB; green two actual OASIS rounds, stable recovered result
  hashes, exactly three/six posts and validated database action counts.
- `pytest tests/test_native_http.py -q --tb=short`: red foreign Host returned200;
  green rejects foreign Host/Origin/Fetch Metadata. Next red missing Start route;
  green authenticated idempotent Start, exact approval and session restoration.
- Receipt adapter's initial contract checks were written after its implementation
  (gap in strict red-first ordering); they exercise eight independent tampering
  cases and idempotent inactive preparation. Actual OASIS packet provider-field
  mismatch was then reproduced red and fixed green.
- Frontend client initial lost-Start test was written alongside implementation
  (also not red-first); browser integration remains necessary. Shared feed is a
  layout extraction, validated by build and forthcoming browser proof.
- Initial focused backend:16passed; frontend:8passed; Vite build passed with the
  existing mixed pendingUpload import and >500KiB main-chunk warnings.
- JS debt:13graph files,3reported,0findings. Explicit JS entrypoints used because
  the scanner does not resolve Vue SFC imports; SFC behavior needs browser/build.
- Full backend, browser workflow and independent review pending.

## Final verification and independent findings

- Browser fixture completed: one durable run despite double Prepare; Alice/Casey
  preserved on Bob failure; double retry prepares only Bob attempt2; separate
  retry review; refresh restores queued run; first three posts appear; separate
  round2 review; completed six-post stream; round2/Casey filter yields one post.
  Seven fixture admissions correspond to six successes plus one failed Bob.
  This is explicitly labeled test transport; no native model jobs were launched.
- Recorded importer regression: existing real six-post run loads through the
  extracted shared component. Screenshots and SQLite evidence are private runtime
  artifacts, outside Git. The browser exposed an empty-state null dereference;
  fixed and verified through successful initial preparation.
- Independent review found two live Compute contract mismatches: queued jobs
  start at attempt0, and terminal failure is `dead`. Reviewer verified both on
  the exact pinned Admin interpreter. Parametrized red tests reproduced both;
  green maps queued0/running1/dead1 correctly and tolerates non-atomic status
  reads. Current bridge sets max_attempts=1; extra attempts remain fail-closed.
- Concurrent four-request retry exposed a CAS conflict; red/green correction
  serializes retry transitions while preserving version-based idempotency.
- Focused final backend21passed, including actual OASIS recovery and preserved
  partial application. Initial full suite175passed; final full rerun pending.
- Independent Standards/Spec currently pass after fixes. Final Proof acceptance
  awaits the completed ledger and concrete inactive preparation. Live native
  inference remains pending user approval of that exact review.
- Admin readiness checked read-only: deployment pin verified, Compute health ok,
  launchd controller running, exact model/low effort in the installed catalog,
  trusted config link resolves to the host's existing Codex configuration. No
  worker restart, credential mutation, task activation or native job occurred.
- Publication remains a stacked draft against PR3's branch. No merge, Admin
  source adoption or deployment is authorized for this feature. Retain worktree
  and runtime artifacts for the upcoming live test.

## Verified source checkpoint

- Final full backend: `python -m pytest tests -q --tb=short` **179passed**,
  167 existing OASIS/SQLite deprecation warnings, 76.49seconds.
- Final frontend: `npm run test:runner` **8passed**; `npm run build` passed.
  Existing Vite mixed-import and large-main-chunk warnings remain unchanged.
- Repeated final JS debt scan:0findings; whitespace and native-source parsing pass.
- Independent reviewer confirmed both P1 fixes and independently reran focused
  backend19passed plus real OASIS2passed. Standards/Spec pass; remaining Proof
  item is the concrete inactive live preparation after committing this source.
  Browser final feed and recorded-view regression are now completed above.
- No unresolved implementation findings. Native end-to-end inference is pending
  concrete user approval. Preparing inactive tasks is the next authorized step.
- Commit slices: backend coordinator/transport/API plus tests; shared feed and
  native UI; operator contract and this evidence ledger. After these commits,
  capture the concrete review and final reviewer confirmation in private runtime
  evidence and the stacked draft PR. Do not change the reviewed source revision.
- Worktree enrolled narrowly in Repo Steward without fetch. Receipt will retain
  the exact clean feature checkout and preserve unmerged work and live artifacts;
  no cleanup or deployment is authorized.

## Commit ledger

- `5d6a8da`: durable backend coordinator, native transport, operator API and tests.
- `5c57f27`: native UI controls, shared feed and frontend tests.
- This documentation commit records the operator contract and verification.
- Publication: authorized stacked draft, pending final inactive-preparation proof.
- Merge/Admin source adoption/deployment: deferred until separately accepted.
