import client from './client'

export interface DnsField {
  name: string
  label: string
  type: string
  required: boolean
  help: string | null
}

export interface DnsProvider {
  slug: string
  title: string
  fields: DnsField[]
  record_types: string[]
  proxyable: string[]
  supports_ttl: boolean
  configured: boolean
}

export interface DnsZone {
  id: string
  name: string
}

export interface DnsRecord {
  id: string
  type: string
  name: string
  content: string
  ttl: number | null
  proxied: boolean | null
  priority: number | null
}

export interface RecordInput {
  type: string
  name: string
  content: string
  ttl: number
  proxied: boolean
  priority?: number | null
}

const enc = encodeURIComponent

export const dnsApi = {
  async providers(): Promise<DnsProvider[]> {
    const { data } = await client.get('/dns/providers')
    return data.items
  },
  async setCreds(slug: string, creds: Record<string, string>): Promise<{ configured: boolean }> {
    const { data } = await client.put(`/dns/providers/${slug}/creds`, { creds })
    return data
  },
  async deleteCreds(slug: string): Promise<{ configured: boolean }> {
    const { data } = await client.delete(`/dns/providers/${slug}/creds`)
    return data
  },
  async zones(slug: string): Promise<DnsZone[]> {
    const { data } = await client.get(`/dns/providers/${slug}/zones`)
    return data.items
  },
  async records(slug: string, zoneId: string): Promise<DnsRecord[]> {
    const { data } = await client.get(`/dns/providers/${slug}/zones/${enc(zoneId)}/records`)
    return data.items
  },
  async createRecord(slug: string, zoneId: string, body: RecordInput): Promise<DnsRecord> {
    const { data } = await client.post(`/dns/providers/${slug}/zones/${enc(zoneId)}/records`, body)
    return data
  },
  async updateRecord(slug: string, zoneId: string, recordId: string, body: RecordInput): Promise<DnsRecord> {
    const { data } = await client.put(
      `/dns/providers/${slug}/zones/${enc(zoneId)}/records/${enc(recordId)}`, body)
    return data
  },
  async deleteRecord(slug: string, zoneId: string, recordId: string): Promise<void> {
    await client.delete(`/dns/providers/${slug}/zones/${enc(zoneId)}/records/${enc(recordId)}`)
  },
}
