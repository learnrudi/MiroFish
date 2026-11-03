# Setup generation through codex-hoff

Native setup is an explicit local mode of the normal MiroFish application.
Document upload generates an ontology; a completed Zep graph supplies entities
for personas and simulation settings. Every model generation uses the pinned
codex-hoff manual runner, gpt-6.1-sol, low effort. Model API credentials are not
required for these paths. Zep remains a separate Cloud graph service and needs
its own project and configuration.

This does **not** connect the general simulation runner, reports or interviews.
Those operations are blocked in native setup mode, including alternate legacy
generation endpoints. The existing bounded three-agent experiment remains at
`/native-run` in its separate process. Native setup currently supports 1–30 graph
entities, sequential persona generation, and at most 64 reviewed generations per
workflow. It does not change the default API-backed application mode.

## Start

Use a qualified backend environment with the repository dependencies. Prepare a
private JSON config outside Git using the same target, remote output root and
trusted shared-root contract described in [native-ui.md](native-ui.md). Use a
fresh `state_root` for setup and, for example:

```json
"http": {"port": 5003, "origins": ["http://127.0.0.1:5181"]}
```

Keep credentials out of that file. `target` comes from the codex-hoff operator
skill's current manual-target metadata; do not substitute a worker or account.
The trusted profile, enabled network and ten-minute timeout are visible in each
review. Instructions authorize only the supplied generation and its output.
Trusted access is not a sandbox against a malicious agent or host.

From `backend`:

```sh
python scripts/run_native_setup.py --config /absolute/private/setup-config.json
```

From `frontend`:

```sh
npm ci --ignore-scripts
MIROFISH_BACKEND_URL=http://127.0.0.1:5003 npm run dev:native-setup -- --port 5181 --strictPort
```

Open `http://127.0.0.1:5181/`. Both processes must remain on loopback. Native
Vite mode rejects wildcard/non-loopback development and preview binds, including
native mode loaded from an environment file. Do not use a public proxy, tunnel,
shared deployment or another static-server configuration for these controls.

## Review and use

Upload PDF, Markdown or text documents and enter the simulation requirement using
the normal home screen. Native setup retains extracted text and file hashes,
not the original uploaded binary files. Inputs are capped at 8 MiB per HTTP
upload, 10 documents and a 2 MiB extracted workflow snapshot.

The Native setup panel shows saved work and each queued/running/completed step.
Read its exact launch review, including the account, host, model, permissions,
input prompt, task revision, output path and hashes. Approve that review to admit
one manual job. Merely uploading/preparing a task starts no native inference.
After verified completion, the ontology appears in the normal project screen.
Without Zep, the app explicitly waits for graph configuration. Configure a new
Zep Cloud project privately, restart the backend, and reopen the saved project
to continue graph building. Never paste an API key into a chat or repository.

Once its graph is complete, normal simulation preparation freezes entities and
graph context. Each persona and each configuration section receives a separate
review. Results are validated before the existing file writers produce
`reddit_profiles.json`, `twitter_profiles.csv` and `simulation_config.json`.
The normal persona and settings screens read these files. General simulation
Start remains disabled until that runner is connected separately.

## Persistence and failure behavior

`state_root/coordinator/setup.sqlite3` retains immutable generation inputs,
requests, reviews, approval hashes, native evidence, results and state changes.
`state_root/uploads` contains the normal project/simulation files. A process
lock allows one owner of this root. Restart resumes the same work and rotates
the in-memory browser token; refresh the UI to reconnect.

Replay means running deterministic setup code over already verified responses;
it does not repeat model calls. Prompts must match captured requests exactly.
Source, locale, target, input or receipt drift fails visibly. Commit source
before preparing a real review, and preserve that worktree unchanged until the
workflow completes. Consumer normalization cannot mutate saved native evidence.
Atomic application writes can recover from interruption; an already applied
ontology does not roll back later graph progress.

Repeated submission for the same upload request or simulation retains one
workflow. Conflicting input is rejected. A transport failure can reconnect only
to the same task and admission key. A terminal job failure, invalid output,
conflicting application artifact or source drift has no automatic fresh retry;
preserve the evidence and inspect private `diagnostics.log`. There is no
destructive Reset button. No fallback API request, invented default persona, or
replacement native job is used to hide a failure. Existing format defaults for
optional persona fields remain deterministic.

## HTTP contract

Normal upload returns 202 with `project_id` and a `setup` snapshot. Normal
simulation preparation returns 202 with a durable `task_id`; its existing status
endpoint reports progress from SQLite. Native controls are:

| Request | Result or mutation input |
| --- | --- |
| `GET /api/native-setup/session` | process token, runner, Zep presence, saved snapshots |
| `GET /api/native-setup/:id` | saved public status |
| `GET /api/native-setup/:id/review` | exact review and SHA-256 |
| `POST /api/native-setup/:id/approve` | `{ "review_hash": "..." }` |
| `POST /api/native-setup/:id/reconcile` | `{ "version": 1 }` for a retryable connection failure |

Mutations require `X-Native-Token`. Host, Origin and cross-site requests are
checked; responses are no-store. Normal destructive routes and unconverted
execution routes are blocked. Review controls deliberately expose the exact
operator-approved inputs; normal snapshots omit inputs and receipts.

## Proof limits

Backend tests cover native receipts, capture/replay, exact approvals, restart,
lost admission, invalid outputs, normal upload/preparation routes and their
actual profile/config consumers. Browser smoke uses an explicitly separate
fixture transport; it is not live codex-hoff proof. A real prepared inactive task
is also not live execution. Live ontology needs approval of its concrete review;
live graph/persona/config verification additionally needs a configured Zep
project. Run `python -m pytest -q` from backend and `npm run test:runner` plus
`VITE_NATIVE_SETUP=1 npm run build` from frontend.
