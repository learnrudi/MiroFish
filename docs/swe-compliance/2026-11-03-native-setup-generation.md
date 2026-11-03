# Native setup generation

## Phase 0: Baseline and manual lookup

- User requested setup generation through codex-hoff as the next full-app step.
- Base: `633e0643714d20d4e15d3d9ef8d9600ef02e9a02` (PRs 3 and 4 merged).
- Inspect: graph ontology upload; simulation preparation; ontology, persona and
  config generators; native receipt transport; normal frontend workflow.
- Manual: index, co-pilot standard, horizontal standard, Appendix C, API E2–E7.
- High risk: a local browser approves trusted native jobs on Admin.
- Existing setup uses three independent API clients and silently falls back in
  persona/config failures. The native path must preserve errors and approvals.
- Local checkout has neither a model API key nor Zep configured. Ontology can
  run without Zep. Real graph-to-persona verification needs Zep separately.

## Phase 1: Scope lock

- Add an opt-in native setup mode to the actual application: uploaded documents
  to ontology, graph entities to personas, and simulation configuration.
- Keep codex-hoff / gpt-6.1-sol / low effort, existing trusted roots and timeout.
- Reuse the native SSH transport, release/control/receipt verification and
  existing generation prompts and downstream file formats.
- Persist setup inputs and each generation request/result. Pause for exact
  review approval at each native call; replay only verified cached generations
  to resume the deterministic setup computation after restart. Never replay
  native admissions with another key. Keep terminal failures visible.
- Freeze graph entities/context before native generation. No graph mutation as
  a side effect of native preparation. Validate structured model outputs.
- New setup endpoints use the same loopback/origin/token boundary. Native setup
  mode blocks unconverted simulation/report/interview model execution.
- Non-goals: general simulation execution, reports/interviews, alternate
  accounts, Zep replacement, deployment, prediction accuracy claims.
- Horizontal disposition: consolidate native control construction/receipt
  transport; standardize JSON generation injection across the three services.
  Separate setup workflow orchestration from the fixed two-round experiment:
  different persistent domain state, shared native transport. No third runner.
- Commit slices: generation seams/structured native transport; durable setup
  workflow and application routes; frontend approvals/status; docs/proof.
- Existing feature-branch publication workflow applies: commit/push/draft PR
  after checks. Merge and Admin adoption require subsequent acceptance.
- Live inference requires a concrete newly prepared review, then user approval.

## Phase 2: Red tests

- One observable behavior at a time: no API client in injected generation;
  no fallback on native failure; exact JSON bindings; approval and restart;
  normal upload/preparation routes; UI polling/approval and failed states.
- Record exact red/green outcomes below. No provider inference in unit tests.

## Phase 3: Implementation

- Files: existing three setup generators; native transport shared helpers;
  new setup coordinator/engine/API/entrypoint; graph/simulation integration;
  frontend setup review/status and normal workflow wiring; focused tests/docs.
- Preserve legacy API mode. Native mode must never fall back to it.
- Idempotency records live for the state store's lifetime. Exact input drift,
  source drift and invalid output fail visibly with evidence retained.

## Phase 4: Green tests and refactor

- Run focused tests after each behavior, then affected regression tests after
  shared transport or service changes. No broad unrelated cleanup.

## Phase 5: Full verification

- Backend suite, frontend tests/build, JS debt scan, whitespace checks.
- Browser normal upload -> review -> status -> stored ontology using explicit
  test transport; persona/config file consumers using graph fixtures.
- Independent fresh-context Standards / Spec / Proof review.
- Prepare real inactive ontology task from the same fictional pricing scenario
  after the source checkpoint; expose exact review in the app.
- Live ontology and actual Zep-dependent setup remain separate proof gates.

## Phase 6: Docs, contracts and closure

- Document operation, per-call approvals, restart/failure behavior, outputs,
  remaining API-backed paths, Zep requirement and local-only deployment scope.
- Record tests, native review, publication and retained worktree receipt.
- Never describe fixture results or inactive preparation as live completion.

## Evidence ledger

- Implementation complete for the opt-in setup scope. No real native inference
  was admitted during implementation. Zep account/configuration remains a
  separate user setup step; reports/interviews/general simulation remain blocked.

### Red / green and refactor evidence

All backend commands used the qualified Python 3.12 OASIS environment and ran
from `backend` as `python -m pytest <listed files> -q --tb=short`.

| Test file | Observed red | Green behavior |
| --- | --- | --- |
| `tests/test_setup_generation.py` | persona fell back; config failed to raise; API key required | injected generation, no API client, failure preserved |
| `tests/test_setup_compute.py` | action-envelope/task-ID rejection | exact setup JSON/request binding over shared native transport |
| `tests/test_setup_coordinator.py` | no generation advancement/reconciliation; polling changed version; uncertain job allowed a new workflow | persisted inputs, per-call approval, same-key reconnect, stable polls, uncertain outcome blocks new work |
| `tests/test_setup_validation.py` | missing/type/range cases did not raise | five setup result kinds reject malformed consumer data |
| `tests/test_setup_engine.py` | missing engine; unknown-agent results accepted; receipt mutated; replay rolled graph status back | real generators and normal file consumers, deterministic replay, exact IDs, evidence preserved, later state preserved |
| `tests/test_setup_http.py` | missing app integration; simulation prepare blocked; realtime consumers404; interrupted upload lost text | normal routes, frozen graph once, real consumer endpoints, recoverable atomic project/text writes |
| `frontend/tests/nativeSetup.test.js` | missing client; wildcard frontend bind accepted, including env-file mode | exact review token/hash transport, no automatic retry, loopback guard in resolved Vite mode |

- Every red was followed by its unchanged behavior assertions passing. Atomic
  file refactor moved failure injection to the actual rename boundary while
  retaining the recovery/no-duplicate assertions. Consumer tests use a fresh
  SimulationManager per request, matching the real route lifecycle.
- Shared native control construction and HTTP boundary extraction preserved
  existing native tests. Shared bounded frontend transport preserved the existing
  run-control test. Refactor verification also covered all setup tests.
- Browser found the completed ontology still displayed a generating badge. The
  corrected screen now shows completion and the explicit graph-setup requirement.

### Final verification

- Full backend suite: **212 passed**, 167 existing OASIS/igraph/SQLite deprecation
  warnings, 92.04 seconds. Subsequent one-active-workflow uncertainty guard:
  coordinator + normal setup HTTP regression **8 passed**.
- Focused setup + shared native transport/HTTP regression: **46 passed** before
  that final guard; its affected tests passed after the guard.
- Frontend: **11 tests passed**; `VITE_NATIVE_SETUP=1 npm run build` passed.
- `git diff --check` passed.
- Debt scan: frontend source graph (12 JS files; 5 changed JS files reported)
  and separate Vite/test neighborhood (16 graph files; 2 reported), **zero
  findings**. Vue SFC imports are not traversed by this scanner; their actual JS
  entrypoints were supplied explicitly and Vue changes were built/browser-tested.
- Browser fixture smoke: normal upload API -> `/process/:projectId` -> read
  exact review -> approve -> queued -> completed -> generated entity types in
  the existing ontology card. Reload preserves completed state. No real jobs.
- Actual normal simulation prepare and realtime persona/config consumer APIs
  are covered by graph-fixture tests; live Zep-dependent proof is pending.
- Private evidence root: operator output `mirofish-native-setup-20261103`, with
  `backend-tests.txt`, `frontend-tests.txt`, `frontend-build.txt`,
  `fixture-ontology-completed.png`, and pinned-release/model/controller preflight.
- Native runtime preflight verified the pinned deployment, registered controller,
  and catalog support for gpt-6.1-sol / low. This is not execution/auth receipt proof.

### Independent review and boundaries

- Fresh-context reviewer: `setup_generation_review`, following rudi-code-review.
  Findings fixed with red/green proof: live consumer storage path, interrupted
  project/text write recovery, frontend proxy bind including env-file mode, and
  ontology replay after later graph progress. Receipt mutation was also closed
  with an independent direct proof. Final verdict: Standards pass, Spec pass,
  Proof pass for code/fixture scope; overall pass for source delivery. Reviewer
  independently reran 46 focused backend, 11 frontend and 8 final guard/HTTP
  tests, and inspected the full-suite/build/debt/browser artifacts. Reviewed
  31-file code-manifest SHA-256:
  `d7013d34849d468aa773421ed8f42876bcb02b3faeeb231f769dcd3df879bd25`.
  This verdict does not authorize admission, merge, deployment or Admin adoption.
- Existing debt: npm's unchanged lockfile reports 13 advisories (1 moderate,
  12 high); dependency remediation is outside this generation change. Existing
  bundle-size and mixed static/dynamic import build warnings remain. Owner: repo
  maintainers; reassess before broader deployment and dependency upgrades.
- Horizontal obligations resolved here: shared receipt/control transport,
  loopback boundary, and bounded browser transport. Separate setup state machine
  remains justified by per-generation capture/replay versus the fixed two-round
  OASIS experiment. Reassess before introducing another workflow coordinator.
- Publication: transport/generation committed as `8a9169e`; durable app integration
  committed as `a080fdb`. The third frontend/docs commit contains this record;
  push/draft-PR and private live-review evidence follow that source checkpoint.
  No merge, Admin source adoption, deployment, worker restart, cleanup or native
  inference authorized by this code delivery. Admin accepted main stays unchanged
  until merge acceptance; native tasks use its existing qualified worker.
- Retain this source worktree and private evidence while the live setup proof is
  pending. Repo Steward receipt and final inactive ontology review are delivery
  artifacts; neither proves execution or accepted integration.
