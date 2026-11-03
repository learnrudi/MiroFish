<template>
  <details class="native-setup" open>
    <summary>Native setup · codex-hoff <span v-if="selected">· {{ selected.status.replaceAll('_', ' ') }}</span></summary>
    <div class="setup-body">
      <p>Ontology, personas and settings run through codex-hoff, with one review per generation.</p>
      <p v-if="!session?.zep_configured" class="notice">Zep is not configured. Ontology can run now; graph building needs a new Zep Cloud project.</p>
      <p v-if="error" role="alert" class="notice">{{ error }}</p>
      <template v-if="session?.workflows.length">
        <label>Saved setup
          <select v-model="selectedId" @change="review = null">
            <option v-for="item in session.workflows" :key="item.id" :value="item.id">{{ item.kind }} · {{ item.resource }} · {{ item.status }}</option>
          </select>
        </label>
        <template v-if="selected">
          <router-link :to="selected.kind === 'ontology' ? `/process/${selected.resource}` : `/simulation/${selected.resource}`">Open this setup</router-link>
          <p aria-live="polite">{{ selected.error?.message || selected.events.at(-1)?.message }}</p>
          <ol v-if="selected.calls.length" class="calls">
            <li v-for="(call, index) in selected.calls" :key="index">{{ call.kind }} — {{ call.status }}</li>
          </ol>
          <template v-if="selected.status === 'awaiting_approval'">
            <button :disabled="busy" @click="showReview">Read launch review</button>
            <template v-if="review">
              <p>gpt-6.1-sol · low effort · one manual job · up to 10 minutes. The exact workspace, access and prompt are below.</p>
              <details open><summary>Exact launch review</summary><pre>{{ JSON.stringify(review.review, null, 2) }}</pre></details>
              <p class="hash">Review SHA-256: {{ review.sha256 }}</p>
              <button :disabled="busy" @click="approve">Approve this generation</button>
            </template>
          </template>
          <button v-if="selected.error?.retryable" :disabled="busy" @click="reconcile">Reconnect to the existing job</button>
          <p v-if="selected.status === 'completed'">Generated results are saved in the application.</p>
        </template>
      </template>
      <p v-else>Upload your documents using the normal app controls to prepare the first review.</p>
      <button :disabled="busy" @click="refresh">Refresh status</button>
    </div>
  </details>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { setupClient } from '../api/nativeSetup.js'

const session = ref(null)
const route = useRoute()
const selectedId = ref('')
const review = ref(null)
const error = ref('')
const busy = ref(false)
const selected = computed(() => session.value?.workflows.find(item => item.id === selectedId.value))
let timer
let stopped = false

async function refresh() {
  clearTimeout(timer)
  try {
    const value = await setupClient.session()
    if (stopped) return
    session.value = value
    if (!selectedId.value && value.workflows.length) {
      const resource = route.params.projectId || route.params.simulationId
      selectedId.value = (value.workflows.find(item => item.resource === resource) || value.workflows[0]).id
    }
    if (selected.value?.status !== 'awaiting_approval') review.value = null
    error.value = ''
  } catch (failure) { error.value = failure.message }
  if (!stopped) timer = setTimeout(refresh, 3000)
}

async function action(callback) {
  if (busy.value) return
  busy.value = true
  clearTimeout(timer)
  try { await callback(); await refresh() }
  catch (failure) {
    error.value = failure.message + ' Refresh status before trying again.'
    // Preserve the error until an explicit refresh after an uncertain reply.
  } finally { busy.value = false }
}
const showReview = () => action(async () => { review.value = await setupClient.review(selectedId.value) })
const approve = () => action(() => setupClient.approve(selectedId.value, review.value.sha256))
const reconcile = () => action(() => setupClient.reconcile(selectedId.value, selected.value.version))
onMounted(refresh)
watch(() => route.fullPath, () => { selectedId.value = ''; review.value = null; refresh() })
onUnmounted(() => { stopped = true; clearTimeout(timer) })
</script>

<style scoped>
.native-setup { position: fixed; right: 18px; bottom: 18px; width: min(510px, calc(100vw - 36px)); z-index: 100; background: #fff; border: 1px solid #243c32; box-shadow: 0 6px 28px #0002; border-radius: 8px; font: 13px/1.5 system-ui, sans-serif; }
summary { padding: 12px; cursor: pointer; font-weight: 650; }
.setup-body { padding: 0 14px 14px; max-height: 65vh; overflow: auto; }
p, label, button, a, .calls { display: block; margin-top: 10px; }
.notice { padding: 10px; background: #fff2d7; }
select { display: block; width: 100%; padding: 7px; }
button { padding: 8px 12px; background: #163e30; color: white; border: 0; border-radius: 4px; cursor: pointer; }
button:disabled { opacity: .5; cursor: wait; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font: 11px/1.5 monospace; max-height: 240px; overflow: auto; background: #f3f5f4; padding: 8px; }
.hash { overflow-wrap: anywhere; font-size: 11px; }
.calls { padding-left: 20px; }
</style>
