import client from './client'

export interface DnsStatus {
  configured: boolean
  record_types: string[]
  proxyable: string[]
}

export interface DnsZone {
  id: string
  name: string
  status: string
  paused: boolean
}

export interface DnsRecord {
  id: string
  type: string
  name: string
  content: string
  ttl: number
  proxied: boolean | null
  priority: number | null
  comment: string | null
}

export interface RecordInput {
  type: string
  name: string
  content: string
  ttl: number
  proxied: boolean
  priority?: number | null
  comment?: string | null
}

export const dnsApi = {
  async status(): Promise<DnsStatus> {
    const { data } = await client.get('/dns/status')
    return data
  },
  async setToken(token: string): Promise<{ configured: boolean }> {
    const { data } = await client.put('/dns/token', { token })
    return data
  },
  async deleteToken(): Promise<{ configured: boolean }> {
    const { data } = await client.delete('/dns/token')
    return data
  },
  async zones(): Promise<DnsZone[]> {
    const { data } = await client.get('/dns/zones')
    return data.items
  },
  async records(zoneId: string): Promise<DnsRecord[]> {
    const { data } = await client.get(`/dns/zones/${zoneId}/records`)
    return data.items
  },
  async createRecord(zoneId: string, body: RecordInput): Promise<DnsRecord> {
    const { data } = await client.post(`/dns/zones/${zoneId}/records`, body)
    return data
  },
  async updateRecord(zoneId: string, recordId: string, body: RecordInput): Promise<DnsRecord> {
    const { data } = await client.put(`/dns/zones/${zoneId}/records/${recordId}`, body)
    return data
  },
  async deleteRecord(zoneId: string, recordId: string): Promise<void> {
    await client.delete(`/dns/zones/${zoneId}/records/${recordId}`)
  },
}
