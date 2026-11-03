import test from 'node:test'
import assert from 'node:assert/strict'
import { createNativeClient } from '../src/api/nativeRuns.js'

const id = 'a'.repeat(32)
const run = { id, version: 1, round: 1, status: 'preparing', agents: [{}, {}, {}], events: [], display: null }

test('a lost Start response and repeated Start reuse the same durable request ID', async () => {
  const stored = new Map()
  const submitted = []
  const client = createNativeClient({ storage: { getItem: key => stored.get(key), setItem: (key, value) => stored.set(key, value) },
    uuid: () => id, fetchImpl: async (url, options) => {
      if (url.endsWith('/session')) return Response.json({ token: 'token', run: null })
      submitted.push(JSON.parse(options.body).request_id)
      assert.equal(options.headers['X-Native-Token'], 'token')
      if (submitted.length === 1) throw new Error('lost connection')
      return Response.json(run)
    } })
  await client.session()
  await assert.rejects(client.start(), /lost connection/)
  await client.start()
  await client.start()
  assert.deepEqual(submitted, [id, id, id])
})
