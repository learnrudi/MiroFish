<template>
  <div class="results-page">
    <header class="results-header">
      <RouterLink to="/" class="brand">MIROFISH</RouterLink>
      <span class="view-label">COMMUNITY FEED</span>
      <RouterLink to="/native-run" class="native-link">Run three agents</RouterLink>
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

      <RecordedRunFeed v-if="run" :run="run" :key="run.source_sha256" />
    </main>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import RecordedRunFeed from '../components/RecordedRunFeed.vue'
import { MAX_RUN_BYTES, parseRecordedRun, readRecordedStream } from '../utils/recordedRun.js'

const run = ref(null)
const error = ref('')
const loading = ref(false)
let generation = 0
const controller = new AbortController()
async function load(readText) {
  const current = ++generation
  run.value = null
  error.value = ''
  loading.value = true
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
.brand { color: inherit; text-decoration: none; font-size: 20px; font-weight: 800; }
.view-label, .eyebrow { font-size: 11px; letter-spacing: .07em; }
.native-link { color: #406b4b; font-size: 13px; }
.file-button { margin-left: auto; padding: 10px 15px; border: 1px solid #cbd0c4; border-radius: 5px; cursor: pointer; font-size: 13px; position: relative; }
.file-button:focus-within { outline: 2px solid #406b4b; outline-offset: 3px; }
.file-button input { position: absolute; inset: 0; width: 100%; opacity: 0; cursor: pointer; }
main { max-width: 960px; margin: auto; padding: 36px 32px; }
.eyebrow { color: #4b6551; font-weight: 700; margin-bottom: 18px; }
.notice { padding: 30px 0; line-height: 1.8; }
.error { color: #843d32; }
@media (max-width: 800px) { .view-label { display: none; } main { padding: 30px 20px; } .results-header { gap: 15px; flex-wrap: wrap; } }
</style>
