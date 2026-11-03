export function createNativeTransport({ base, fetchImpl = fetch, getToken = () => '' }) {
  return async function request(path, data) {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 15000)
    try {
      const response = await fetchImpl(`${base}${path}`, {
        method: data ? 'POST' : 'GET', cache: 'no-store', signal: controller.signal,
        headers: data ? { 'Content-Type': 'application/json', 'X-Native-Token': getToken() } : {},
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

}
