import { parseRecordedRun } from '../utils/recordedRun.js'

export function normalizeSnapshot(run) {
  if (run === null) return null
  if (!run || !/^[a-f0-9]{32}$/.test(run.id) || !Number.isSafeInteger(run.version) || run.version < 1 ||
      ![1, 2].includes(run.round) || !['preparing', 'awaiting_approval', 'queued', 'running', 'applying', 'completed', 'failed'].includes(run.status) ||
      !Array.isArray(run.agents) || run.agents.length !== 3 || !Array.isArray(run.events) || run.events.length > 500) {
    throw new Error('The server returned an invalid run state.')
  }
  return { ...run, display: run.display ? parseRecordedRun(JSON.stringify(run.display)) : null }
}

export function createNativeClient({ fetchImpl = fetch, storage = localStorage, uuid = () => crypto.randomUUID() } = {}) {
  let token = ''
  let current = null
  const key = 'mirofish.native.request'

  async function request(path, data) {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 15000)
    try {
      const response = await fetchImpl(`/api/native-runs${path}`, {
        method: data ? 'POST' : 'GET', cache: 'no-store', signal: controller.signal,
        headers: data ? { 'Content-Type': 'application/json', 'X-Native-Token': token } : {},
        ...(data ? { body: JSON.stringify(data) } : {}),
      })
      // The endpoint bounds every review and snapshot. Also bound the received
      // stream, including when a proxy omits Content-Length.
      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8', { fatal: true })
      let size = 0
      let text = ''
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          size += value.byteLength
          if (size > 1024 * 1024) throw new Error('Native response exceeds 1 MiB.')
          text += decoder.decode(value, { stream: true })
        }
        text += decoder.decode()
      } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
      const result = JSON.parse(text)
      if (!response.ok) throw new Error(result.message || 'Native request failed. Reload the current state.')
      return result
    } finally { clearTimeout(timeout) }
  }

  function remember(run) {
    current = normalizeSnapshot(run)
    return current
  }

  return {
    async session() {
      const result = await request('/session')
      token = result.token
      return { ...result, run: remember(result.run) }
    },
    async refresh(id) { return remember(await request(`/${id}`)) },
    async start() {
      let id = storage.getItem(key)
      if (!id || (current?.status === 'completed' && id === current.id)) {
        id = uuid().replaceAll('-', '')
        storage.setItem(key, id)
      }
      return remember(await request('', { request_id: id }))
    },
    async review(id) { return request(`/${id}/review`) },
    async approve(id, reviewHash) { return remember(await request(`/${id}/approve`, { review_hash: reviewHash })) },
    async retry(id, version) { return remember(await request(`/${id}/retry`, { version })) },
  }
}
