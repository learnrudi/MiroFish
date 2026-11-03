import test from 'node:test'
import assert from 'node:assert/strict'
import { MAX_RUN_BYTES, parseRecordedRun, readRecordedStream } from '../src/utils/recordedRun.js'

function bundle() {
  return {
    schema_version: 1,
    title: 'Note-taking service price increase',
    scenario: 'The monthly price rises from $20 to $30 next month.',
    recorded_at: '2026-11-03T05:21:11.683552Z',
    runner: { identity: 'codex-hoff', model: 'gpt-6.1-sol', effort: 'low' },
    source_sha256: 'a'.repeat(64),
    posts: ['alice', 'bob', 'casey', 'alice', 'bob', 'casey'].map((name, index) => ({
      user_name: name, content: `Post ${index + 1}`,
    })),
  }
}

test('cancels an oversized headerless download before consuming the whole body', async () => {
  let chunksRead = 0
  let canceled = false
  const stream = new ReadableStream({
    pull(controller) {
      chunksRead++
      if (chunksRead <= 10) controller.enqueue(new Uint8Array(16384))
      else controller.close()
    },
    cancel() { canceled = true },
  }, { highWaterMark: 0 })
  const response = new Response(stream)
  assert.equal(response.headers.get('content-length'), null)
  await assert.rejects(readRecordedStream(response.body), /64 KiB/)
  assert.equal(canceled, true)
  assert.equal(chunksRead, 5)
})

test('rejects invalid UTF-8 bytes for both local files and fetched records', async () => {
  const data = bundle()
  data.posts[0].content = 'BROKEN_X_BYTE'
  const bytes = new TextEncoder().encode(JSON.stringify(data))
  const marker = new TextEncoder().encode(JSON.stringify(data).split('BROKEN_')[0] + 'BROKEN_').length
  bytes[marker] = 0xff
  for (const stream of [new Blob([bytes]).stream(), new Response(bytes).body]) {
    await assert.rejects(readRecordedStream(stream), /UTF-8/)
  }
})

test('preserves valid Unicode across byte-chunk boundaries and accepts the exact size limit', async () => {
  const data = bundle()
  data.posts[0].content = 'Notes café 日本語 📝'
  const bytes = new TextEncoder().encode(JSON.stringify(data))
  let index = 0
  const stream = new ReadableStream({
    pull(controller) {
      if (index < bytes.length) controller.enqueue(bytes.slice(index, ++index))
      else controller.close()
    },
  })
  const run = parseRecordedRun(await readRecordedStream(stream))
  assert.equal(run.posts[0].content, data.posts[0].content)
  const padded = JSON.stringify(data) + ' '.repeat(MAX_RUN_BYTES - bytes.length)
  const exact = await readRecordedStream(new Blob([padded]).stream())
  assert.equal(new TextEncoder().encode(exact).length, MAX_RUN_BYTES)
  assert.equal(parseRecordedRun(exact).posts[0].content, data.posts[0].content)
})

test('rejects an incorrectly attributed post before displaying a recorded run', () => {
  const data = bundle()
  data.posts[3].user_name = 'bob'
  assert.throws(() => parseRecordedRun(JSON.stringify(data)), /Invalid recorded run/)
})

test('rejects incomplete rounds and malformed text instead of displaying partial results', () => {
  const incomplete = bundle()
  incomplete.posts.pop()
  assert.throws(() => parseRecordedRun(JSON.stringify(incomplete)), /Invalid recorded run/)
  const malformed = bundle()
  malformed.posts[0].content = '\ud800'
  assert.throws(() => parseRecordedRun(JSON.stringify(malformed)), /Invalid recorded run/)
})

test('preserves each post and derives its round, excluding unrelated input fields', () => {
  const input = bundle()
  input.database = '/private/machine/path'
  input.posts[0].content = '<script>text from an agent</script>'
  const run = parseRecordedRun(JSON.stringify(input))
  assert.deepEqual(run.posts.map(post => post.round), [1, 1, 1, 2, 2, 2])
  assert.deepEqual(run.posts.map(post => post.content), input.posts.map(post => post.content))
  assert.equal(run.database, undefined)
  input.posts = input.posts.slice(0, 3)
  assert.deepEqual(parseRecordedRun(JSON.stringify(input)).posts.map(post => post.round), [1, 1, 1])
})

test('rejects oversized, corrupt, or invalid metadata and content', () => {
  for (const text of ['{', 'null', ' '.repeat(MAX_RUN_BYTES + 1)]) {
    assert.throws(() => parseRecordedRun(text), /Invalid recorded run/)
  }
  for (const change of [
    data => { data.schema_version = 2 },
    data => { data.runner = null },
    data => { data.source_sha256 = 'not-a-digest' },
    data => { data.recorded_at = 'not-a-date' },
    data => { data.posts[0].content = ' ' },
    data => { data.posts[0].content = 'x'.repeat(281) },
  ]) {
    const data = bundle()
    change(data)
    assert.throws(() => parseRecordedRun(JSON.stringify(data)), /Invalid recorded run/)
  }
})
