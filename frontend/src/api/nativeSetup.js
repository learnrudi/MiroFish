import { createNativeTransport } from './nativeTransport.js'

export function createSetupClient({ fetchImpl = fetch } = {}) {
  let token = ''
  let pending = null
  const transport = createNativeTransport({ base:'/api/native-setup', fetchImpl, getToken:() => token })
  async function request(path, data) {
    const result = await transport(path, data)
    if (!result.success) throw new Error(result.error || 'Native setup request failed')
    return result.data
  }
  async function session() {
    if (!pending) pending = request('/session').then(value => {
      token = value.token
      return value
    }).finally(() => { pending = null })
    return pending
  }
  return {
    session,
    async token() { if (!token) await session(); return token },
    get: id => request(`/${id}`),
    review: id => request(`/${id}/review`),
    approve: (id, hash) => request(`/${id}/approve`, { review_hash:hash }),
    reconcile: (id, version) => request(`/${id}/reconcile`, { version }),
  }
}

export const setupClient = createSetupClient()
