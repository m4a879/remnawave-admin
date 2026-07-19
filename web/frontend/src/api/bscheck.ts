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

export interface BsTargetSummary extends BsSummary {
  target: string
}

export interface BsNode {
  uuid: string
  name: string
  ip: string | null
  address: string | null
  agent_ip: string | null
}

export interface NodeBsSummary {
  passed: number
  total: number
  checked_at: string | null
}

export interface BsCheckRecord {
  id: number
  node_uuid: string
  checked_at: string
  passed: number
  total: number
  cost_credits: number | null
  result: { summary?: BsSummary; raw?: unknown }
  created_by: string | null
}

export interface BsHistoryRow {
  id: number
  node_uuid: string | null
  kind: string
  target: string | null
  passed: number
  total: number
  cost_credits: number | null
  result: any
  created_by: string | null
  checked_at: string
}

export interface HistorySave {
  kind: string
  target?: string
  passed: number
  total: number
  cost_credits?: number | null
  result: any
}

export interface BsSchedule {
  enabled: boolean
  interval_hours: number
  dpi: string
  operators: string[]
  nodes: string[]
  budget_daily: number
  alert: boolean
  last_run: string | null
  spent_today: number
}

export interface ProbeBody {
  target?: string
  targets?: string[]
  operators: string[]
  probes: Record<string, boolean>
  sni_hosts: string[]
  dpi: string
}

export interface ScanBody {
  cidr: string
  operators: string[]
  probes: Record<string, boolean>
  sni_hosts: string[]
  dpi: string
}

export interface VlessBody {
  raw_input: string
  selected_modems: string[]
  dpi: string
  core: string
}

export const bscheckApi = {
  async status(): Promise<BsStatus> {
    const { data } = await client.get('/bscheck/status'); return data
  },
  async setToken(token: string): Promise<{ configured: boolean }> {
    const { data } = await client.put('/bscheck/token', { token }); return data
  },
  async deleteToken(): Promise<{ configured: boolean }> {
    const { data } = await client.delete('/bscheck/token'); return data
  },
  async operators(): Promise<BsOperator[]> {
    const { data } = await client.get('/bscheck/operators'); return data.items
  },
  async nodes(): Promise<BsNode[]> {
    const { data } = await client.get('/bscheck/nodes'); return data.items
  },
  async summary(): Promise<Record<string, NodeBsSummary>> {
    const { data } = await client.get('/bscheck/summary'); return data.items
  },
  async nodeHistory(uuid: string): Promise<{ last: BsCheckRecord | null; history: BsCheckRecord[] }> {
    const { data } = await client.get(`/bscheck/nodes/${uuid}`); return data
  },
  async preview(body: ProbeBody): Promise<{ cost_credits: number }> {
    const { data } = await client.post('/bscheck/probe/preview', body); return data
  },
  async checkNode(uuid: string, body: ProbeBody): Promise<{ summary: BsSummary; checked_at: string | null }> {
    const { data } = await client.post(`/bscheck/nodes/${uuid}/check`, body); return data
  },
  async probeMulti(body: ProbeBody): Promise<{ targets: BsTargetSummary[]; cost_credits: number | null }> {
    const { data } = await client.post('/bscheck/probe', body); return data
  },
  async scanPreview(body: ScanBody): Promise<{ cost_credits: number; total_ips?: number }> {
    const { data } = await client.post('/bscheck/scans/preview', body); return data
  },
  async scanSubmit(body: ScanBody): Promise<{ scan_id: number; state: string }> {
    const { data } = await client.post('/bscheck/scans', body); return data
  },
  async scanStatus(id: number | string): Promise<any> {
    const { data } = await client.get(`/bscheck/scans/${id}`); return data
  },
  async vlessSubmit(body: VlessBody): Promise<{ test_id: number; cost_credits: number; n_servers?: number }> {
    const { data } = await client.post('/bscheck/vless', body); return data
  },
  async vlessStatus(id: number | string): Promise<any> {
    const { data } = await client.get(`/bscheck/vless/${id}`); return data
  },
  async saveHistory(payload: HistorySave): Promise<BsHistoryRow> {
    const { data } = await client.post('/bscheck/history', payload); return data
  },
  async history(kind?: string, limit = 50): Promise<BsHistoryRow[]> {
    const { data } = await client.get('/bscheck/history', { params: { kind, limit } }); return data.items
  },
  async getSchedule(): Promise<BsSchedule> {
    const { data } = await client.get('/bscheck/schedule'); return data
  },
  async setSchedule(payload: Partial<BsSchedule>): Promise<BsSchedule> {
    const { data } = await client.put('/bscheck/schedule', payload); return data
  },
}
