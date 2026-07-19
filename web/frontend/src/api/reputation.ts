import client from './client'

export interface RepProvider {
  slug: string
  name: string
  needs_token: boolean
  configured: boolean
  signup_url: string
}

export interface RepResult {
  provider: string
  ip: string
  score?: number | null
  is_proxy?: boolean | null
  is_vpn?: boolean | null
  is_hosting?: boolean | null
  is_tor?: boolean | null
  recent_abuse?: boolean | null
  blocked?: boolean | null
  rkn_domain?: string | null
  blocked_subnets?: string[] | null
  country?: string | null
  asn?: string | null
  org?: string | null
  error?: string
  raw?: any
}

export const reputationApi = {
  async providers(): Promise<RepProvider[]> {
    const { data } = await client.get('/reputation/providers'); return data.items
  },
  async setCreds(slug: string, token: string): Promise<void> {
    await client.put(`/reputation/providers/${slug}/creds`, { token })
  },
  async delCreds(slug: string): Promise<void> {
    await client.delete(`/reputation/providers/${slug}/creds`)
  },
  async lookup(target: string): Promise<{ target: string; results: RepResult[] }> {
    const { data } = await client.post('/reputation/lookup', { target }); return data
  },
}
