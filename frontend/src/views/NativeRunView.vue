<template>
  <div class="native-page">
    <header class="topbar"><RouterLink to="/" class="brand">MIROFISH</RouterLink>
      <span>NATIVE AGENT RUN</span><RouterLink to="/runner-results">Recorded feed</RouterLink></header>
    <main>
      <div class="eyebrow">THREE AGENTS · TWO ROUNDS</div>
      <h1>Watch the conversation develop.</h1>
      <p class="intro">Alice, Bob and Casey respond to a note-taking service raising its price from $20 to $30.
        In the second round, they read each other’s first posts before responding again.</p>
      <div class="runner" v-if="runner">{{ runner.identity }} <span>{{ runner.model }} · {{ runner.effort }} effort</span></div>
      <p v-if="runner?.identity === 'test-transport'" class="error">TEST TRANSPORT — synthetic responses, no native jobs.</p>
      <div class="notice error" role="alert" v-if="error">{{ error }} <button @click="connect" :disabled="busy">Reconnect</button></div>
      <p class="notice" role="status" v-if="!connected && !error">Connecting to the local run service…</p>
      <section class="controls" v-if="connected">
        <template v-if="!run || run.status === 'completed'">
          <button class="primary" :disabled="busy" @click="perform(() => client.start())">{{ run ? 'Prepare another run' : 'Prepare three agents' }}</button>
          <p>Preparation creates inactive tasks. Review and approve each round before any jobs start.</p>
        </template>
        <template v-if="run">
          <div class="run-heading"><h2>Round {{ run.round }} of 2</h2><span class="status" role="status">{{ statusLabel }}</span></div>
          <ol class="agents" aria-label="Agent job status">
            <li v-for="agent in run.agents" :key="agent.name"><span class="avatar" :class="agent.name">{{ agent.name[0].toUpperCase() }}</span>
              <div><strong>{{ agent.name[0].toUpperCase() + agent.name.slice(1) }}</strong><small>Attempt {{ agent.attempt }}</small></div>
              <span>{{ labels[agent.status] || agent.status }}</span></li>
          </ol>
          <div v-if="run.error" class="notice error" role="alert"><p>{{ run.error.message }}</p>
            <button v-if="run.error.retryable" :disabled="busy" @click="perform(() => client.retry(run.id, run.version))">
              {{ run.error.code === 'transport_unavailable' ? 'Reconnect and reconcile' : 'Prepare failed-agent retry' }}
            </button></div>
          <p v-if="run.status === 'preparing'" class="hint">Capturing the OASIS context and preparing inactive native tasks…</p>
          <p v-if="['queued', 'running', 'applying'].includes(run.status)" class="hint">This page updates automatically. Verified posts appear below when the round is applied.</p>
          <section v-if="run.status === 'awaiting_approval'" class="review" aria-label="Round launch review">
            <h2>Review round {{ run.round }}</h2>
            <p v-if="!review">Loading the exact launch review…</p>
            <template v-else>
              <p>{{ launchCount }} fresh {{ launchCount === 1 ? 'job' : 'jobs' }} on {{ review.review.tasks[0]?.target?.host?.name || 'test transport' }}.
                Each job uses a fresh session and may write one simulated post. No real social posts are sent.</p>
              <p v-if="review.review.preserved_successes.length">Preserved successful agents: {{ review.review.preserved_successes.join(', ') }}.</p>
              <p class="permissions">Trusted access · network enabled · up to 10 minutes per job. The declared read/write roots and exact instructions are shown below.</p>
              <details v-for="task in review.review.tasks" :key="task.task_id" class="task-review">
                <summary>{{ task.name }} · {{ review.review.preserved_successes.includes(task.name) ? 'already succeeded' : 'inactive, ready for approval' }}</summary>
                <p><code>{{ task.task_id }}</code></p>
                <h3>Execution profile</h3><pre>{{ JSON.stringify(task.profile, null, 2) }}</pre>
                <h3>Exact instructions</h3><pre>{{ task.instructions_text }}</pre>
                <h3>Task definition and hashes</h3><pre>{{ JSON.stringify({ task: task.task, definition_sha256: task.definition_sha256, target: task.target }, null, 2) }}</pre>
              </details>
              <p class="digest">Review SHA-256 <code>{{ review.sha256 }}</code></p>
              <label class="acknowledge"><input type="checkbox" v-model="acknowledged" /> I approve these exact instructions, runner and trusted permissions for this round.</label>
              <button class="primary" :disabled="busy || !acknowledged" @click="approve">Approve round {{ run.round }} · start {{ launchCount }} {{ launchCount === 1 ? 'job' : 'jobs' }}</button>
            </template>
          </section>
          <details class="activity"><summary>Run activity</summary><p v-for="(event, index) in run.events" :key="index">{{ new Date(event.at).toLocaleTimeString() }} · Round {{ event.round }} · {{ event.message }}</p><code>Run {{ run.id }}</code></details>
        </template>
      </section>
      <section v-if="run?.display" class="feed"><RecordedRunFeed :run="run.display" :verified="runner?.identity === 'codex-hoff'" /></section>
      <div v-else class="empty-feed"><h2>Community feed</h2><p>The agents’ posts will appear here after a verified round completes.</p></div>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import RecordedRunFeed from '../components/RecordedRunFeed.vue'
import { createNativeClient } from '../api/nativeRuns.js'

const client = createNativeClient()
const run = ref(null)
const runner = ref(null)
const review = ref(null)
const acknowledged = ref(false)
const error = ref('')
const connected = ref(false)
const busy = ref(false)
let timer
let disposed = false
let epoch = 0
const labels = { preparing: 'Preparing', awaiting_approval: 'Awaiting approval', queued: 'Queued', running: 'Running',
  applying: 'Verifying and applying', completed: 'Completed', failed: 'Failed', unprepared: 'Preparing', prepared: 'Ready for review', succeeded: 'Verified' }
const statusLabel = computed(() => labels[run.value?.status] || '')
const launchCount = computed(() => 3 - (review.value?.review.preserved_successes.length || 0))

function accept(next) {
  if (disposed || (run.value && next && run.value.id === next.id && run.value.version > next.version)) return
  if (next?.review_hash !== run.value?.review_hash || next?.status !== 'awaiting_approval') {
    review.value = null
    acknowledged.value = false
  }
  run.value = next
}

async function loadReview() {
  const current = run.value
  if (current?.status !== 'awaiting_approval' || review.value) return
  const result = await client.review(current.id)
  if (!disposed && run.value?.review_hash === result.sha256 && run.value.status === 'awaiting_approval') review.value = result
}

async function connect() {
  busy.value = true
  error.value = ''
  ++epoch
  try {
    const session = await client.session()
    runner.value = session.runner
    accept(session.run)
    connected.value = true
    await loadReview()
  } catch (failure) { error.value = failure.message; connected.value = false }
  finally { busy.value = false }
}

async function perform(action) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  ++epoch
  try { accept(await action()); await loadReview() }
  catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}

function approve() {
  if (!acknowledged.value || review.value?.sha256 !== run.value?.review_hash) return
  const id = run.value.id
  const hash = review.value.sha256
  perform(() => client.approve(id, hash))
}

async function poll() {
  const currentEpoch = epoch
  if (connected.value && run.value && !busy.value) {
    try {
      const next = await client.refresh(run.value.id)
      if (currentEpoch === epoch) { accept(next); await loadReview() }
    } catch (failure) { if (currentEpoch === epoch && !disposed) error.value = failure.message }
  }
  if (!disposed) timer = setTimeout(poll, 1500)
}
onMounted(async () => { await connect(); if (!disposed) poll() })
onUnmounted(() => { disposed = true; ++epoch; clearTimeout(timer) })
</script>

<style scoped>
.native-page { min-height: 100vh; background: #fafaf8; color: #20251f; font-family: 'Space Grotesk', system-ui, sans-serif; }
.topbar { display: flex; align-items: center; gap: 28px; min-height: 74px; padding: 18px 5vw; background: white; border-bottom: 1px solid #dedfd7; }
.topbar a { color: #406b4b; font-size: 13px; text-decoration: none; }
.topbar .brand { color: #20251f; font-size: 20px; font-weight: 800; }
.topbar > span { font-size: 11px; letter-spacing: .08em; color: #78806f; }
.topbar > a:last-child { margin-left: auto; }
main { max-width: 960px; padding: 40px 32px; margin: auto; }
.eyebrow { color: #4b6551; font-size: 11px; font-weight: 700; letter-spacing: .08em; margin-bottom: 18px; }
h1 { font-size: clamp(28px, 4vw, 38px); font-weight: 600; letter-spacing: -.04em; }
h2 { font-size: 18px; font-weight: 600; }
h3 { font-size: 13px; margin: 18px 0 8px; }
.intro { max-width: 770px; color: #5f675b; line-height: 1.8; margin: 18px 0; }
.runner { display: inline-flex; flex-wrap: wrap; gap: 14px; background: #eef1e8; padding: 9px 12px; border-radius: 5px; font-size: 12px; margin: 4px 0 26px; }
.runner span { color: #67705f; }
.controls { border-block: 1px solid #dedfd7; padding: 26px 0; }
.controls > p, .hint { margin-top: 14px; color: #78806f; font-size: 13px; line-height: 1.7; }
button { border: 1px solid #cbd0c4; background: white; border-radius: 5px; padding: 11px 16px; font: inherit; font-size: 13px; cursor: pointer; }
button:disabled { opacity: .45; cursor: default; }
button.primary { background: #253e2d; color: white; border-color: #253e2d; }
button:focus-visible, summary:focus-visible { outline: 2px solid #477c51; outline-offset: 3px; }
.run-heading { display: flex; align-items: center; gap: 20px; margin: 26px 0 18px; }
.status { margin-left: auto; font-size: 12px; border: 1px solid #d4d8ce; padding: 7px 10px; border-radius: 20px; }
.agents { list-style: none; padding: 0; display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.agents li { display: flex; align-items: center; gap: 10px; padding-block: 14px; border-block: 1px solid #e5e8de; }
.agents strong { display: block; font-size: 14px; }.agents small { color: #78806f; font-size: 11px; }.agents li > span:last-child { margin-left: auto; color: #4b6551; font-size: 12px; }
.avatar { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: #e8eee3; color: #456044; font-size: 12px; }.avatar.bob { background: #e8edf5; color: #466182; }.avatar.casey { background: #f3ebdf; color: #846849; }
.review { background: white; border: 1px solid #d4d8ce; border-radius: 7px; padding: 24px; margin-top: 24px; }
.review p { font-size: 13px; line-height: 1.8; margin: 14px 0; }.permissions { color: #67705f; }
.task-review { border-top: 1px solid #e5e8de; padding: 14px 0; font-size: 13px; }summary { cursor: pointer; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 440px; overflow: auto; background: #f5f6f1; padding: 15px; font-size: 11px; line-height: 1.7; }
code { overflow-wrap: anywhere; font-size: 11px; }.digest { color: #78806f; }.digest code { display: block; }
.acknowledge { display: flex; align-items: flex-start; gap: 10px; font-size: 13px; line-height: 1.6; margin: 20px 0; }.acknowledge input { margin-top: 4px; }
.activity { margin-top: 22px; font-size: 12px; color: #78806f; }.activity p { margin: 12px 0; }
.notice { padding: 18px 0; line-height: 1.8; font-size: 13px; }.notice button { margin-top: 12px; }.error { color: #843d32; }
.feed { margin-top: 36px; }.empty-feed { padding: 36px 0; }.empty-feed p { color: #78806f; font-size: 14px; margin-top: 15px; }
@media (max-width: 700px) { main { padding: 30px 20px; }.agents { grid-template-columns: 1fr; gap: 0; }.topbar { gap: 14px; }.topbar > span { display: none; }.review { padding: 18px; } }
</style>
