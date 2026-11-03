import test from 'node:test'
import assert from 'node:assert/strict'
import { createSetupClient } from '../src/api/nativeSetup.js'
import { resolveConfig } from 'vite'
import { mkdtemp, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'

test('setup session refresh and approval retain the exact reviewed hash without retrying admission', async () => {
  const submissions = []
  let sessions = 0
  const client = createSetupClient({ fetchImpl: async (url, options) => {
    if (url.endsWith('/session')) {
      sessions++
      return Response.json({ success:true, data:{ token:'current-token', workflows:[], zep_configured:false } })
    }
    submissions.push(options)
    assert.equal(options.headers['X-Native-Token'], 'current-token')
    throw new Error('Reply lost')
  } })
  await Promise.all([client.token(),client.token()])
  assert.equal(sessions,1)
  await assert.rejects(client.approve('a'.repeat(32), 'b'.repeat(64)), /Reply lost/)
  assert.equal(submissions.length,1)
  assert.equal(JSON.parse(submissions[0].body).review_hash,'b'.repeat(64))
})

test('the native bind guard also applies when native mode comes from a Vite env file', async () => {
  const directory=await mkdtemp(path.join(tmpdir(),'mirofish-native-env-'))
  try {
    await writeFile(path.join(directory,'.env'),'VITE_NATIVE_SETUP=1\n')
    await assert.rejects(resolveConfig({ envDir:directory, server:{host:true} },'serve'),/loopback/)
  } finally { await rm(directory,{recursive:true,force:true}) }
})

test('native setup rejects a frontend bind that could expose operator tokens through the proxy', async () => {
  process.env.VITE_NATIVE_SETUP = '1'
  try {
    await assert.rejects(resolveConfig({ server:{host:'0.0.0.0'} }, 'serve'), /loopback/)
    const config = await resolveConfig({ server:{host:'127.0.0.1'}, preview:{host:'127.0.0.1'} }, 'serve')
    assert.equal(config.server.host,'127.0.0.1')
  } finally { delete process.env.VITE_NATIVE_SETUP }
})
