export const MAX_RUN_BYTES = 64 * 1024
const names = ['alice', 'bob', 'casey']

export async function readRecordedStream(stream) {
  if (!stream) throw new Error('Run file has no readable content.')
  const reader = stream.getReader()
  const chunks = []
  let size = 0
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > MAX_RUN_BYTES) throw new Error('Run files must be at most 64 KiB.')
      chunks.push(value)
    }
    const bytes = new Uint8Array(size)
    let offset = 0
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength }
    try {
      return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
    } catch {
      throw new Error('Invalid recorded run: file must contain valid UTF-8.')
    }
  } catch (error) {
    // Preserve the original read/validation error if canceling also fails.
    await reader.cancel().catch(() => {})
    throw error
  } finally { reader.releaseLock() }
}

function validText(value, limit) {
  return typeof value === 'string' && value.trim().length > 0 &&
    Array.from(value).length <= limit &&
    new TextDecoder().decode(new TextEncoder().encode(value)) === value
}

function invalid() {
  throw new Error('Invalid recorded run: expected a complete three-agent run with valid metadata and posts.')
}

// This display format is bounded to the one- and two-round OASIS experiment.
// Metadata describes the imported file; it is not proof of native provenance.
export function parseRecordedRun(text) {
  if (typeof text !== 'string' || new TextEncoder().encode(text).length > MAX_RUN_BYTES) invalid()
  let data
  try { data = JSON.parse(text) } catch { invalid() }
  if (!data || data.schema_version !== 1 || !validText(data.title, 120) ||
      !validText(data.scenario, 1000) || !validText(data.recorded_at, 40) ||
      !Number.isFinite(Date.parse(data.recorded_at)) ||
      typeof data.source_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(data.source_sha256) ||
      !data.runner || !['identity', 'model', 'effort'].every(key => validText(data.runner[key], 80)) ||
      !Array.isArray(data.posts) || ![3, 6].includes(data.posts.length)) invalid()

  const posts = data.posts.map((post, index) => {
    if (!post || post.user_name !== names[index % 3] || !validText(post.content, 280)) invalid()
    return { user_name: post.user_name, content: post.content, round: Math.floor(index / 3) + 1 }
  })
  return {
    title: data.title, scenario: data.scenario, recorded_at: data.recorded_at,
    source_sha256: data.source_sha256,
    runner: { identity: data.runner.identity, model: data.runner.model, effort: data.runner.effort },
    posts,
  }
}
