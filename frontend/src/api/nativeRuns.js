import { createNativeTransport } from './nativeTransport.js'
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

  const request = createNativeTransport({ base:'/api/native-runs', fetchImpl, getToken:() => token })

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
