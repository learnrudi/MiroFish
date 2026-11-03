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
- `backend/app/agent_runners/oasis_smoke.py`: one or three synthetic characters,
  one round, one allowed action, concurrency one, fresh SQLite state, bounded execution.
- `backend/app/agent_runners/oasis_group.py`: three file exchanges with validation
  of every response and regenerated context before application.
- `backend/scripts/run_oasis_runner.py`: single-agent and group prepare/apply commands.
- `backend/tests/test_oasis_runner.py`: real OASIS tests with deterministic runner
  responses, plus boundary and failure tests. These tests do not invoke Codex.

The fixture uses Alice's reaction to a note-taking subscription rising from $20
to $30 against her $25 budget. The event is supplied in her context; the simulated
feed starts empty. Reddit's local recommendation implementation avoids a Twitter
embedding-model download. There is no Zep ingestion, model API key, or live
social-media account involved.

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

## Three agents sharing a world

The group fixture keeps Alice and adds Bob (daily work use, $50 budget) and Casey
(team administrator concerned about predictable costs and migration effort).
All receive the same $20-to-$30 announcement. Each has a separate model instance,
persona context, request digest, and native response. They share one OASIS world.
This is one round from an empty feed, not a conversation or a test of reactions
to each other's posts. OASIS action concurrency remains one.

```sh
uv run --frozen python scripts/run_oasis_runner.py prepare-group \
  --directory /tmp/mirofish-group \
  --identity codex-hoff --model gpt-6.1-sol --effort low
```

This captures `alice/request.json`, `bob/request.json`, and `casey/request.json`
and a `prepare.db` with zero posts. Review three separate native tasks, one per
packet, using the workflow above. Separate fresh sessions keep the characters'
prompt contexts apart; they do not create a filesystem security boundary in
trusted execution mode. No native tasks are created or run by these commands.

After verifying all three native receipts and output hashes, save the responses
as `alice.json`, `bob.json`, and `casey.json` in a separate response directory:

```sh
uv run --frozen python scripts/run_oasis_runner.py apply-group \
  --directory /tmp/mirofish-group --responses /path/to/verified-responses
```

The command validates and snapshots all response files, then regenerates and
compares all three actual OASIS requests in a fresh `verify.db` without posting.
Only after that does it create `apply.db` and execute the three decisions.
Success requires exactly one post and one `create_post` trace for each expected
user; `result.json` includes attribution and all three request digests.
Missing, swapped, malformed, or stale responses fail before application. A changed
later request also fails before any posts. A runtime failure during application
is reported as a failure and can leave partial SQLite evidence; this is not a
database-wide transaction. Existing databases are never reused or overwritten.

The group tests use the real OASIS engine and deterministic response fixtures.
They establish context separation, shared database attribution, request/response
validation, CLI round trips, preserved failure evidence, and refusal to repeat
application. They do not establish live Codex completion or model quality.

The three-agent extension passed all 151 backend tests (eight new group cases).
Independent review found that escaped lone-surrogate text could reach SQLite
after other agents had posted. Strict UTF-8 content validation now rejects it
during preflight; the reviewer confirmed the regression and approved this bounded
implementation. Existing upstream igraph/SQLite deprecation warnings remain.

### Live three-agent result

On 2026-11-02 (America/New_York), all three reviewed native jobs completed on their
first attempt through `codex-hoff`, `gpt-6.1-sol`, low effort, with observed ChatGPT
authentication and three distinct native sessions. Completion and launch receipts,
reviewed task hashes, identity/model/effort, and output hashes were verified before
importing the responses. OASIS then regenerated the exact three requests and stored
three posts and three `create_post` traces, correctly attributed to Alice, Bob,
and Casey. A direct SQLite check also matched each post to its native response.

| Agent | Observed reaction | Native job duration |
| --- | --- | --- |
| Alice | The new $30 price exceeds her $25 budget; plans to find a cheaper option. | 30.32 seconds |
| Bob | Daily work use and a $50 budget favor staying, while comparing alternatives. | 36.45 seconds |
| Casey | Wants clarity on future pricing and import/export effort before choosing for a team. | 38.78 seconds |

All posts met the 280-character limit. Durations include native runner/file
overhead, exclude queue waiting, and are not a throughput benchmark. Native jobs
and OASIS actions were serialized. This proves separate persona responses and
shared-world application for one round; in that run, the agents had not yet read
or replied to each other's posts. It does not establish real-world predictive accuracy.

### Execution hosts

The accepted single-agent source was cloned to Admin through Git at merge
`f34b3cb01d039aee0d480a0dc50586d39f853cea`. On 2026-11-02, installing the pinned
backend on macOS Intel stopped because `torch==2.9.1` has no compatible wheel.
Backend validation therefore runs on the Apple Silicon workstation. Native
Codex tasks can still run on Admin, with verified response files brought back
for local OASIS application. No dependencies were changed to bypass this limit.

## Reviewed second round

`prepare-followup` accepts the verified first-round `result.json` and its exact
SHA-256. It validates three attributed posts, creates a fresh world, and replays
those posts through OASIS `ManualAction` calls. It restores each character's own
post as a CAMEL assistant memory message. The other posts arrive through the real
OASIS feed, with a user-ID/name map in the persona context. No new inference is
used to reconstruct round one, and the original result/database remain untouched.

```sh
uv run --frozen python scripts/run_oasis_runner.py prepare-followup \
  --directory /tmp/mirofish-round2 \
  --previous-result /path/to/verified-first-round/result.json \
  --previous-sha256 THE_EXACT_FILE_SHA256 \
  --identity codex-hoff --model gpt-6.1-sol --effort low
```

Review three new native tasks containing these full packets, including memory
and feed. Each task writes one follow-up response; the character can maintain or
revise its position, with no instruction to agree. After verifying native receipts
and response hashes, apply the three separately named response files:

```sh
uv run --frozen python scripts/run_oasis_runner.py apply-followup \
  --directory /tmp/mirofish-round2 --responses /path/to/verified-round2-responses
```

Capture and preflight databases contain only the three replayed posts. Successful
application requires six posts and six `create_post` traces, two per character.
The resulting `posts` list is in creation order: the three earlier posts, then
the three follow-ups. Changed history or a mismatched response fails before new
posts are applied; unexpected runtime failures may retain partial evidence.

Reconstruction restores the earlier post text, not a full native session or all
CAMEL tool history. Synthetic timestamps use a fixed clock so capture and apply
receive identical feeds; original wall-clock timestamps are not retained. All
characters observe the same round-one feed, not earlier decisions from round two.
These are follow-up `create_post` actions, not threaded `create_comment` actions.
The snapshot/hash proves which input was used, not who originally generated it;
the operator must verify the first-round receipts and result before preparation.
Only the first-round three-post result is accepted: this is not a general loop.

Assess the live outputs for references to other posts, consistency with budgets
and roles, and continuity with the earlier position. Technical success does not
require agreement or prove that another agent caused a change of opinion.

Verification: 158 backend tests passed, including seven new follow-up cases.
An independent reviewer reran all 29 runner/group/follow-up cases and returned
Standards/Spec/Proof pass with no findings.

### Live second-round result

On 2026-11-02 (America/Chicago), all three approved second-round native jobs
completed on their first attempt through `codex-hoff`, `gpt-6.1-sol`, low effort,
with observed ChatGPT authentication. Each used a distinct fresh native session,
different from the first-round sessions. Reviewed task bindings, completion and
launch receipts, identity/model/effort, and response hashes passed verification.

OASIS regenerated the three exact packets before applying the responses. Direct
SQLite inspection confirmed six posts and six `create_post` traces, two per
character. The first three posts match round one and the last three match the
verified native outputs. Capture and preflight databases each contain only the
three replayed posts. The original first-round result and database hashes remain
unchanged.

| Agent | Observed follow-up | Native job duration |
| --- | --- | --- |
| Alice | Acknowledges Bob's daily work use, keeps her $25 limit, and adopts Casey's suggestion to check note export while comparing affordable options. | 30.39 seconds |
| Bob | Recognizes Alice's budget concern and Casey's export question; stays for daily work within his $50 budget while adding a migration check. | 37.14 seconds |
| Casey | Weighs Alice's budget limit against Bob's daily reliance; defers the team decision pending pricing clarity and import/export assessment. | 28.83 seconds |

All three explicitly reference both other characters and retain their own role
and budget constraints. Their posts are 200, 229, and 222 characters respectively.
This demonstrates use of the supplied shared feed and restored own-post context
in one follow-up round. It does not isolate causal influence, establish predictive
accuracy, or prove persistent native memory. All observe round one rather than
one another's new follow-ups, and the actions are posts rather than threaded
comments. Durations include native runner/file overhead and exclude queue time;
this is not a throughput benchmark.

Independent live-evidence review returned Standards/Spec/Proof pass with no
findings, including read-only verification of the original execution-host files
and direct SQLite checks. No behavior code changed for this live run.

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
generation, reports, interviews, unbounded round loops, other tools, streaming, other
providers, automatic job admission and parallel action execution are outside this slice.
The byte-based context counter is a conservative fixture budget, not measured
token usage or a production tokenizer. The full app retains its original model
API and Zep requirements. Source stays in Git; account profiles, keys, databases,
generated packets and Compute controls stay outside it.
