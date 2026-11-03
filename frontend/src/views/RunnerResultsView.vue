<template>
  <div class="results-page">
    <header class="results-header">
      <RouterLink to="/" class="brand">MIROFISH</RouterLink>
      <span class="view-label">AGENT RUN RESULTS</span>
      <label class="file-button">Open run file
        <input type="file" accept="application/json,.json" @change="openFile" />
      </label>
    </header>

    <main>
      <div class="eyebrow"><span class="status-dot"></span> READ-ONLY REPLAY</div>
      <p v-if="loading" role="status" class="notice">Loading recorded run…</p>
      <div v-else-if="error" role="alert" class="notice error">
        <h1>Run could not be loaded</h1>
        <p>{{ error }}</p>
        <p>Choose a recorded-run JSON file with “Open run file”.</p>
      </div>

      <template v-if="run">
        <h1>{{ run.title }}</h1>
        <p class="scenario">{{ run.scenario }}</p>
        <div class="run-meta">
          <span>{{ run.runner.identity }}</span><span>{{ run.runner.model }}</span>
          <span>{{ run.runner.effort }} effort</span><span>{{ recordedTime }}</span>
        </div>
        <div class="summary">
          <div><strong>3</strong><span>AGENTS</span></div>
          <div><strong>{{ rounds.length }}</strong><span>ROUNDS</span></div>
          <div><strong>{{ run.posts.length }}</strong><span>POSTS</span></div>
          <p>Recorded posts from a completed run. In round two, each agent reads
            the first-round feed and its own earlier post.</p>
        </div>

        <div class="filters">
          <div class="round-buttons" aria-label="Filter by round">
            <button :aria-pressed="selectedRound === 0" @click="selectedRound = 0">All rounds</button>
            <button v-for="round in rounds" :key="round" :aria-pressed="selectedRound === round"
              @click="selectedRound = round">Round {{ round }}</button>
          </div>
          <label class="agent-filter">Agent
            <select v-model="selectedAgent" aria-label="Filter by agent">
              <option value="all">All agents</option>
              <option v-for="name in names" :key="name" :value="name">{{ displayName(name) }}</option>
            </select>
          </label>
        </div>

        <section v-for="round in visibleRounds" :key="round" class="round-section" :aria-label="`Round ${round} posts`">
          <div class="round-heading">
            <h2>Round {{ round }}</h2>
            <span>{{ round === 1 ? 'Initial reactions' : 'After reading the shared feed' }}</span>
          </div>
          <div class="post-grid">
            <article v-for="post in postsFor(round)" :key="`${round}-${post.user_name}`" class="post-card">
              <header><div class="avatar">{{ displayName(post.user_name)[0] }}</div>
                <h3>{{ displayName(post.user_name) }}</h3><span class="post-label">POST</span></header>
              <p>{{ post.content }}</p>
              <footer>ROUND {{ round }} <span>OASIS · Topic Community</span></footer>
            </article>
          </div>
        </section>
        <details class="source-details">
          <summary>Recorded data source</summary>
          <p>Original result SHA-256: <code>{{ run.source_sha256 }}</code></p>
          <p>This view displays an imported record. It does not independently verify native execution receipts.</p>
        </details>
      </template>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { MAX_RUN_BYTES, parseRecordedRun, readRecordedStream } from '../utils/recordedRun.js'

const names = ['alice', 'bob', 'casey']
const run = ref(null)
const error = ref('')
const loading = ref(false)
const selectedRound = ref(0)
const selectedAgent = ref('all')
let generation = 0
const controller = new AbortController()
const rounds = computed(() => run.value ? [...new Set(run.value.posts.map(post => post.round))] : [])
const visibleRounds = computed(() => rounds.value.filter(round => !selectedRound.value || round === selectedRound.value))
const recordedTime = computed(() => new Date(run.value.recorded_at).toLocaleString())
const displayName = name => name[0].toUpperCase() + name.slice(1)
const postsFor = round => run.value.posts.filter(post => post.round === round &&
  (selectedAgent.value === 'all' || post.user_name === selectedAgent.value))

async function load(readText) {
  const current = ++generation
  run.value = null
  error.value = ''
  loading.value = true
  selectedRound.value = 0
  selectedAgent.value = 'all'
  try {
    const parsed = parseRecordedRun(await readText())
    if (current === generation) run.value = parsed
  } catch (failure) {
    if (current === generation) error.value = failure.message || 'Unable to read the run file.'
  } finally {
    if (current === generation) loading.value = false
  }
}

function openFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  controller.abort()
  load(() => {
    if (file.size > MAX_RUN_BYTES) throw new Error('Run files must be at most 64 KiB.')
    return readRecordedStream(file.stream())
  })
  event.target.value = ''
}

onMounted(() => load(async () => {
  const timeout = setTimeout(() => controller.abort(), 10000)
  try {
    const response = await fetch('/runner-results/latest.json', { cache: 'no-store', signal: controller.signal })
    if (!response.ok) throw new Error('No recorded run is installed in this preview.')
    return await readRecordedStream(response.body)
  } finally { clearTimeout(timeout) }
}))
onUnmounted(() => { generation++; controller.abort() })
</script>

<style scoped>
.results-page { min-height: 100vh; background: #fafaf8; font-family: 'Space Grotesk', system-ui, sans-serif; color: #20251f; }
.results-header { min-height: 72px; border-bottom: 1px solid #dedfd7; display: flex; align-items: center; gap: 28px; padding: 16px 5vw; background: white; }
.brand { color: inherit; font-family: 'JetBrains Mono', monospace; text-decoration: none; font-size: 20px; font-weight: 800; letter-spacing: 1px; }
.view-label, .eyebrow, .run-meta, .post-label, .post-card footer, .summary span { font-size: 11px; letter-spacing: .07em; }
.view-label { color: #6a7165; }
.file-button { margin-left: auto; padding: 10px 15px; border: 1px solid #cbd0c4; border-radius: 5px; cursor: pointer; font-size: 13px; position: relative; }
.file-button:focus-within { outline: 2px solid #406b4b; outline-offset: 3px; }
.file-button input { position: absolute; inset: 0; width: 100%; opacity: 0; cursor: pointer; }
main { max-width: 1280px; margin: auto; padding: 48px 32px; }
.eyebrow { display: flex; align-items: center; gap: 8px; color: #4b6551; font-weight: 700; margin-bottom: 18px; }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: #477c51; }
h1 { font-size: clamp(28px, 3.5vw, 42px); letter-spacing: -.04em; font-weight: 600; line-height: 1.15; }
.scenario { margin-top: 18px; max-width: 780px; font-size: 16px; line-height: 1.7; color: #5f675b; }
.run-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 22px; }
.run-meta span { background: #f0f1eb; padding: 7px 10px; border-radius: 4px; letter-spacing: 0; }
.summary { display: flex; gap: 36px; align-items: center; margin: 32px 0; padding: 24px 0; border-block: 1px solid #dedfd7; }
.summary div { display: flex; flex-direction: column; gap: 5px; min-width: 65px; }
.summary strong { font-size: 30px; font-weight: 500; }
.summary span { color: #6a7165; }
.summary p { margin-left: auto; max-width: 460px; font-size: 13px; line-height: 1.7; color: #67705f; }
.filters { display: flex; align-items: center; gap: 18px; justify-content: space-between; margin-bottom: 36px; }
.round-buttons { display: flex; gap: 6px; }
.round-buttons button { padding: 10px 16px; border: 1px solid #d4d8ce; background: transparent; border-radius: 5px; cursor: pointer; font-size: 12px; }
.round-buttons button[aria-pressed=true] { background: #253e2d; color: white; border-color: #253e2d; }
.agent-filter { font-size: 12px; display: flex; align-items: center; gap: 10px; }
select { padding: 9px 12px; border: 1px solid #d4d8ce; border-radius: 5px; background: white; color: inherit; }
.round-section { margin-bottom: 38px; }
.round-heading { display: flex; align-items: baseline; gap: 15px; margin-bottom: 15px; }
h2 { font-size: 17px; font-weight: 600; }
.round-heading span { font-size: 12px; color: #78806f; }
.post-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
.post-card { background: white; border: 1px solid #e0e3d9; border-radius: 7px; overflow: hidden; display: flex; flex-direction: column; }
.post-card header { display: flex; align-items: center; gap: 10px; padding: 20px 22px 0; }
.avatar { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; background: #e8eee3; color: #456044; font-size: 12px; }
h3 { font-size: 14px; font-weight: 600; }
.post-label { margin-left: auto; color: #8a9181; font-size: 9px; }
.post-card > p { padding: 22px; flex: 1; line-height: 1.8; font-size: 14px; overflow-wrap: anywhere; white-space: pre-wrap; }
.post-card footer { display: flex; justify-content: space-between; gap: 10px; padding: 14px 22px; border-top: 1px solid #eef0e9; font-size: 9px; color: #798270; }
.source-details { font-size: 12px; color: #78806f; line-height: 1.8; }
.source-details summary { cursor: pointer; }
.source-details p { margin-top: 10px; }
code { overflow-wrap: anywhere; }
.notice { padding: 30px 0; line-height: 1.8; }
.notice h1 { font-size: 26px; margin-bottom: 15px; }
.error { color: #843d32; }
@media (max-width: 800px) { .post-grid { grid-template-columns: 1fr; } .summary { flex-wrap: wrap; gap: 25px; } .summary p { margin-left: 0; max-width: none; } .view-label { display: none; } main { padding: 30px 20px; } .filters { align-items: flex-start; flex-direction: column; } .round-buttons button { padding: 10px 12px; } }
</style>
