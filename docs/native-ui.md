# Bounded native run controls

`/native-run` runs the existing three-character price-change experiment through
`codex-hoff`, `gpt-6.1-sol`, low effort. It prepares real OASIS contexts, creates
inactive native tasks, displays their exact review, and admits a round only after
its review is approved. Round two is prepared from the actual first-round posts
and needs its own approval. The community feed updates after receipt validation
and successful OASIS application. `/runner-results` remains a read-only importer.

This is a **local operator experiment**, not the full application run workflow.
Ontology, persona/config generation, reports and interviews remain separate
API-backed paths. Zep remains a separate graph service. The fixed three personas,
two rounds, create_post-only action and selected identity/model are intentional.

## Start the local services

Use an existing backend environment with the repository dependencies installed.
Create a private JSON config outside Git containing:

- `target`: the current codex-hoff **manual** target object from the operator skill;
  includes the SSH alias, pinned worker interpreter/bundle/manifest and account.
- `remote_outputs_root`: the approved absolute output directory on that host.
- `shared_roots`: the three owner-approved trusted read/write roots.
- `state_root`: a fresh absolute local directory outside the source checkout.
- `http`: `{ "port": 5001, "origins": ["http://127.0.0.1:5179"] }`.

Do not include credentials. Do not substitute another account or worker release.
Preparation uses trusted access and enabled network under the owner's existing
policy; this is not a sandbox against malicious native agents. Review all roots,
permissions, instructions, task hashes and target details before approval.

From `backend`, run `python scripts/run_native_ui.py --config /absolute/private/config.json`.
From `frontend`, run `npm ci --ignore-scripts` and
`npm run dev -- --host 127.0.0.1 --port 5179 --strictPort`.
The existing Vite proxy targets backend port 5001. Open
`http://127.0.0.1:5179/native-run`. Keep both services local. Do not expose this
operator API through a public tunnel, a wildcard CORS proxy or a deployment.
The native backend explicitly excludes legacy simulation routes and does not
require model API or Zep keys. It does not modify the normal application startup.

## Workflow and recovery

1. Prepare three agents. The request UUID is kept in browser storage and SQLite;
   repeated clicks, refreshes and lost HTTP replies reuse the same run.
2. Expand the review for each agent. Approve the displayed review hash and trusted
   permissions. That approves only the currently displayed round/attempts.
3. Observe queued/running/verified status. The coordinator validates the stored
   task revision, controls, input bytes and pinned release before submission.
4. It verifies completion/launch hashes, job/task/request bindings, observed
   account, native model/effort and output bytes before accepting a decision.
   Only three valid decisions can reach OASIS. It then compares posts and action
   traces against the database before displaying the round.
5. Review round two after the first feed exists. Its fresh sessions contain each
   character's own previous post and the shared first-round feed.

A terminal native failure permits **one fresh attempt for failed agents only**,
with a new task and approval. Successful agents remain preserved. A connection
failure instead reconciles the existing task and **same admission key**; unknown
outcomes never justify a new native job. The one-active-run restriction includes
failed runs. Non-retryable drift or partial application needs operator inspection;
there is intentionally no destructive Reset/Force button. Preserve that state
root and all associated remote artifacts. A new root is an explicit operator
recovery choice, not an automatic retry.

SQLite stores snapshots, revisions, approvals, job evidence and events. Request
IDs and native admission keys are retained for the life of the state store, with
no automatic expiry. A process lock prevents a second service from owning the
same root. Restarting the service resumes the same run and rotates the browser
request token; reconnect the UI. Source/target drift stops the run. Finish and
commit code changes before preparing real tasks. A complete OASIS result can be
reconciled after a crash; an incomplete application is preserved and not replayed.
Private `diagnostics.log` and `oasis.log` files contain operator failure details.
No credentials, runtime databases or job artifacts belong in Git.

## HTTP contract

All endpoints are beneath `/api/native-runs`; every response is `no-store`.
Only configured loopback Host/Origin values are accepted. Mutations require
`X-Native-Token` from `GET /session`, and exactly the documented JSON key.
The token is process-local, never persisted in the browser or placed in a URL.
Browser inputs cannot choose models, accounts, prompts, shell, paths or permissions.

| Request | Input | Result |
| --- | --- | --- |
| `GET /session` | none | token, selected runner, latest/unfinished public run |
| `POST /` (no trailing slash) | `request_id`: lowercase 32-character UUID hex | existing or new preparation |
| `GET /:id` | none | snapshot, agent status, events, verified display bundle |
| `GET /:id/review` | none | concrete review and SHA-256 |
| `POST /:id/approve` | `review_hash` | durable approval; asynchronous admission |
| `POST /:id/retry` | `version`: failed snapshot version | reconciliation or fresh inactive retry |

Conflicts return 409; invalid origin/token 403; missing run 404; invalid request
400/413/415; unavailable state 503. Errors have stable `error` and `message`
fields, without private diagnostics. Public snapshots exclude packets and native
receipts; the separate review deliberately exposes the owner-reviewed controls.

## Verification

From backend: `python -m pytest tests -q`. From frontend:
`npm run test:runner` and `npm run build`. New tests cover concurrent Start,
exact per-round approval, duplicate approval, failed-agent preservation/retry,
ambiguous admission/restart, source drift, receipt tampering, origin/CSRF input
boundaries and actual two-round OASIS application/recovery. Browser fixture
transport is explicitly labeled and is not evidence of live native execution.
Live native execution requires approval of newly prepared concrete tasks.
