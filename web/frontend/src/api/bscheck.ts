import client from './client'

export interface BsOperator {
  id: string
  name: string
  op_key: string
  channel_state: string
  alive: boolean
  region_label?: string | null
}

export interface BsAccount {
  balance_credits?: number
  balance_total?: number
  bonus_credits?: number
  tier?: string
}

export interface BsStatus {
  configured: boolean
  account: BsAccount | null
}

export interface BsOpResult {
  op: string
  ok: boolean
  channel_state: string | null
  latency_ms: number | null
  tcp_is_tls: boolean | null
  error: string | null
}

export interface BsSummary {
  passed: number
  total: number
  operators: BsOpResult[]
  cost_credits: number | null
  skipped_dpi_off: string[]
}

export interface ProbeBody {
  target: string
  operators: string[]
  probes: Record<string, boolean>
  sni_hosts: string[]
  dpi: string
}

export interface NodeBsSummary {
  passed: number
  total: number
  checked_at: string | null
}

export const bscheckApi = {
  async status(): Promise<BsStatus> {
    const { data } = await client.get('/bscheck/status')
    return data
  },
  async setToken(token: string): Promise<{ configured: boolean }> {
    const { data } = await client.put('/bscheck/token', { token })
    return data
  },
  async deleteToken(): Promise<{ configured: boolean }> {
    const { data } = await client.delete('/bscheck/token')
    return data
  },
  async operators(): Promise<BsOperator[]> {
    const { data } = await client.get('/bscheck/operators')
    return data.items
  },
  async preview(body: ProbeBody): Promise<{ cost_credits: number }> {
    const { data } = await client.post('/bscheck/probe/preview', body)
    return data
  },
  async checkNode(uuid: string, body: ProbeBody): Promise<{ summary: BsSummary; checked_at: string | null }> {
    const { data } = await client.post(`/bscheck/nodes/${uuid}/check`, body)
    return data
  },
  async summary(): Promise<Record<string, NodeBsSummary>> {
    const { data } = await client.get('/bscheck/summary')
    return data.items
  },
}
