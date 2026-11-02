# Reviewed native runner / OASIS experiment

The experiment connects a real OASIS `SocialAgent` to a custom CAMEL
`BaseModelBackend`. It captures the actual messages and `create_post` tool schema,
accepts a reviewed native Codex response, converts it into a `ChatCompletion` tool
call, and lets OASIS execute that call. The OpenAI response **type** is used for
CAMEL compatibility; no OpenAI API client is constructed by this adapter.

This is deliberately a file exchange with an approval checkpoint. It does not
automatically create jobs, reuse logins, or turn a subscription into an API server.

## Components

- `backend/app/agent_runners/oasis_model.py`: explicit runner metadata, canonical
  request hash, strict single-action validation, sync/async CAMEL response adapter.
- `backend/app/agent_runners/exchange.py`: bounded UTF-8 JSON files, duplicate-key
  rejection, no final symlinks, and rejection of a changed request.
- `backend/app/agent_runners/oasis_smoke.py`: one synthetic character, one round,
  one allowed action, concurrency one, fresh SQLite state, bounded execution.
- `backend/scripts/run_oasis_runner.py`: prepare/apply commands.
- `backend/tests/test_oasis_runner.py`: real OASIS tests with deterministic runner
  responses, plus boundary and failure tests. These tests do not invoke Codex.

The fixture uses Alice's reaction to a note-taking subscription rising from $20
to $30 against her $25 budget. The event is supplied in her context; the simulated
feed starts empty. Reddit's local recommendation implementation avoids a Twitter
embedding-model download. There is no Zep ingestion, model API key, second agent,
or live social-media account involved.

## Prepare the actual OASIS request

From `backend`, install the existing pinned dependencies and use a new directory:

```sh
uv sync --frozen --python 3.12
uv run --frozen python scripts/run_oasis_runner.py prepare \
  --directory /tmp/mirofish-oasis-test \
  --identity codex-hoff --model gpt-6.1-sol --effort low
```

This creates `request.json` and a `prepare.db` with no posts. The JSON status is
`awaiting_review`. Library diagnostics go to stderr/log files. A `ReviewRequired`
diagnostic in upstream logs is expected during capture; other errors are failures.
The directory must not already exist. No inference or Compute admission occurs.

## Obtain a reviewed response

Use the selected identity's Compute workflow outside this source repository.
Verify its pinned deployment and model catalog. Bind the **entire request packet**
into the reviewed instructions; do not substitute a simplified prompt. Prepare
an inactive task, review its identity/model/effort, exact instructions, permissions,
paths and hashes, and obtain approval before running that revision.

Ask the runner to return exactly this envelope, using the actual request digest:

```json
{
  "schema_version": 1,
  "request_sha256": "THE_DIGEST_FROM_REQUEST_JSON",
  "tool_call": {
    "name": "create_post",
    "arguments": {"content": "The character's original response, at most 280 characters."}
  }
}
```

The tool schema describes simulated actions, not permission to post externally.
The native task only writes the response file. After completion, verify the
Compute completion and launch receipts, observed identity, selected model/effort,
and output hash. Transfer only the verified response needed by this experiment;
keep native credentials and runtime controls on their original host.

The packet's identity is a **requested routing setting**, not authentication
proof. The local adapter validates content and request binding; the operator's
verified native receipts establish where the response came from. A matching hash
alone does not establish provenance or model quality.

## Apply the decision through OASIS

```sh
uv run --frozen python scripts/run_oasis_runner.py apply \
  --directory /tmp/mirofish-oasis-test \
  --response /path/to/verified-response.json
```

This regenerates the same real OASIS request and requires an exact match, then
validates the response and executes its tool call. It writes a fresh `apply.db`
and `result.json`. Success requires exactly one post and one `create_post` trace.
Reusing `apply.db` fails rather than overwriting or appending. This protects this
exchange directory; it is not a global exactly-once guarantee across copied runs.

OASIS catches model exceptions internally. The harness checks the adapter's
recorded error and the database so a missing, rejected, or failed runner response
cannot silently count as a successful simulation. Failed runs retain evidence;
prepare a new reviewed exchange instead of blindly retrying into an existing DB.

## Verification and limits

```sh
uv run --frozen python -m pytest tests/test_oasis_runner.py -q
uv run --frozen python -m pytest tests -q
```

The real-engine test was first observed red (no post), then green after implementing
tool-call translation. Further red/green checks cover stale responses, unsupported
actions, extra arguments, blank content, file boundaries, swallowed OASIS errors,
and JSON-only CLI output. Round-trip, timeout propagation and database reuse checks
verify the resulting integration. See the task's local review for run evidence.

On 2026-11-02, a live reviewed run using `codex-hoff`, `gpt-6.1-sol`, and low
reasoning effort completed through native ChatGPT authentication. The native
completion/launch receipts and response hash were checked before applying the
response. OASIS regenerated the matching request and stored exactly one post and
one `create_post` trace. The native job took 28.5 seconds including runner/file
overhead; this single observation is not a throughput benchmark. The backend
suite passed all 142 tests, including the 13 new runner/OASIS tests.

An independent pre-merge technical review caught a request-comparison edge case:
Python treats JSON booleans and numbers as equal in some comparisons. Matching
now uses canonical JSON serialization, preserving types. A real-OASIS regression
first reproduced an unwanted post, then passed with rejection and zero posts.
The reviewer confirmed the correction; the full backend suite passed 143 tests.

This is not yet the main web application's inference backend. Persona/config
generation, reports, interviews, multiple rounds, other tools, streaming, other
providers, automatic job admission and concurrent agents are outside this slice.
The byte-based context counter is a conservative fixture budget, not measured
token usage or a production tokenizer. The full app retains its original model
API and Zep requirements. Source stays in Git; account profiles, keys, databases,
generated packets and Compute controls stay outside it.
