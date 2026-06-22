/**
 * TEMPORARY preview of the list view modes (public route `/viewdemo`).
 * Mock data so table / compact / large views can be reviewed without a backend.
 * Switch entity (fleet/nodes/hosts) and mode via the toolbar or ?entity=&?mode=.
 * Remove this file and its route before release.
 */
import { useState } from 'react'
import { ViewToggle } from '@/components/ViewToggle'
import type { ViewMode } from '@/lib/useViewMode'
import { FleetTable } from '@/components/fleet/FleetTable'
import { CompactNodeCard } from '@/components/fleet/CompactNodeCard'
import NodeCard, { type FleetNode } from '@/components/fleet/NodeCard'
import { NodesTable, type NodeRow } from '@/components/nodes/NodesTable'
import { NodeCompactCard } from '@/components/nodes/NodeCompactCard'
import { HostsTable, type HostRow } from '@/components/hosts/HostsTable'
import { HostCompactCard } from '@/components/hosts/HostCompactCard'
import { cn } from '@/lib/utils'

type Entity = 'fleet' | 'nodes' | 'hosts'

const F = (over: Partial<FleetNode>): FleetNode => ({
  uuid: Math.random().toString(36).slice(2), name: 'node', address: '10.0.0.1', port: 2222,
  is_connected: true, is_disabled: false, is_xray_running: true, xray_version: '25.3.6',
  users_online: 0, traffic_today_bytes: 0, traffic_total_bytes: 0, uptime_seconds: 0,
  cpu_usage: null, cpu_cores: 4, memory_usage: null, memory_total_bytes: 8e9, memory_used_bytes: 0,
  disk_usage: null, disk_total_bytes: 1e11, disk_used_bytes: 0, disk_read_speed_bps: 0, disk_write_speed_bps: 0,
  last_seen_at: '2026-06-22T08:00:00Z', download_speed_bps: 0, upload_speed_bps: 0, metrics_updated_at: '2026-06-22T08:00:00Z',
  ...over,
})
const MOCK_FLEET: FleetNode[] = [
  F({ name: 'de-frankfurt-1', address: '49.12.5.10', users_online: 128, cpu_usage: 42, memory_usage: 61, disk_usage: 38, uptime_seconds: 1_900_000, download_speed_bps: 84e6, upload_speed_bps: 22e6, traffic_today_bytes: 412e9, traffic_total_bytes: 18e12 }),
  F({ name: 'nl-amsterdam-2', address: '5.255.103.4', users_online: 96, cpu_usage: 88, memory_usage: 94, disk_usage: 70, uptime_seconds: 720_000, download_speed_bps: 51e6, upload_speed_bps: 13e6, traffic_today_bytes: 280e9, traffic_total_bytes: 9e12 }),
  F({ name: 'sg-singapore-1', address: '103.27.8.9', users_online: 210, cpu_usage: 97, memory_usage: 80, disk_usage: 91, uptime_seconds: 5_400_000, download_speed_bps: 120e6, upload_speed_bps: 38e6, traffic_today_bytes: 640e9, traffic_total_bytes: 41e12 }),
  F({ name: 'us-newyork-1', address: '23.105.7.7', is_connected: false, users_online: 0, xray_version: null }),
  F({ name: 'ru-moscow-1', address: '45.67.230.5', is_disabled: true, is_connected: false, users_online: 0 }),
]

const ND = (over: Partial<NodeRow>): NodeRow => ({
  uuid: Math.random().toString(36).slice(2), name: 'node', address: '10.0.0.1', port: 2222,
  is_connected: true, is_disabled: false, users_online: 0, xray_version: '25.3.6',
  traffic_total_bytes: 0, traffic_today_bytes: 0, last_seen_at: '2026-06-22T08:00:00Z',
  has_agent_token: true, agent_v2_connected: true, ...over,
})
const MOCK_NODES: NodeRow[] = [
  ND({ name: 'de-frankfurt-1', address: '49.12.5.10', users_online: 128, traffic_today_bytes: 412e9, traffic_total_bytes: 18e12 }),
  ND({ name: 'nl-amsterdam-2', address: '5.255.103.4', users_online: 96, traffic_today_bytes: 280e9, traffic_total_bytes: 9e12, agent_v2_connected: false }),
  ND({ name: 'sg-singapore-1', address: '103.27.8.9', users_online: 210, traffic_today_bytes: 640e9, traffic_total_bytes: 41e12 }),
  ND({ name: 'us-newyork-1', address: '23.105.7.7', is_connected: false, users_online: 0, xray_version: null, has_agent_token: false, agent_v2_connected: false, last_seen_at: '2026-06-21T20:00:00Z' }),
  ND({ name: 'ru-moscow-1', address: '45.67.230.5', is_disabled: true, is_connected: false, users_online: 0, agent_v2_connected: false }),
]

const H = (over: Partial<HostRow>): HostRow => ({
  uuid: Math.random().toString(36).slice(2), remark: 'host', address: 'example.com', port: 443,
  is_disabled: false, is_hidden: false, tag: null, inbound: { uuid: '1', tag: 'VLESS-TCP', type: 'vless' },
  security_layer: 'reality', security: null, nodes: null, ...over,
})
const MOCK_HOSTS: HostRow[] = [
  H({ remark: 'Германия Reality', address: 'de.example.com', tag: 'DE', security_layer: 'reality', nodes: [{ uuid: '1', name: 'de-frankfurt-1' }] }),
  H({ remark: 'Нидерланды TLS', address: 'nl.example.com', tag: 'NL', security_layer: 'tls', inbound: { uuid: '2', tag: 'VLESS-WS', type: 'vless' }, nodes: [{ uuid: '2', name: 'nl-amsterdam-2' }, { uuid: '3', name: 'nl-amsterdam-3' }] }),
  H({ remark: 'Сингапур', address: 'sg.example.com', tag: 'SG', security_layer: 'tls', is_hidden: true, nodes: [{ uuid: '4', name: 'sg-singapore-1' }] }),
  H({ remark: 'Тест (no security)', address: 'test.example.com', security_layer: 'none', is_disabled: true }),
]

export default function ViewDemo() {
  const params = new URLSearchParams(window.location.search)
  const [entity, setEntity] = useState<Entity>((params.get('entity') as Entity) || 'fleet')
  const [mode, setMode] = useState<ViewMode>(() => {
    const m = params.get('mode')
    return m === 'compact' || m === 'large' || m === 'table' ? m : 'table'
  })
  const noop = () => {}
  const gridCls = cn('grid gap-4', mode === 'compact' ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4' : 'grid-cols-1 lg:grid-cols-2 xl:grid-cols-3')

  return (
    <div className="min-h-screen bg-[#070b13] text-white p-6 sm:p-10">
      <div className="max-w-6xl mx-auto space-y-5">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-xl font-bold">Режимы отображения <span style={{ color: 'var(--accent-from)' }}>(preview)</span></h1>
            <p className="text-sm text-dark-300 mt-1">Моковые данные. Сортировка/фильтры в таблице — по заголовкам.</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="inline-flex rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] p-0.5">
              {(['fleet', 'nodes', 'hosts'] as Entity[]).map((e) => (
                <button key={e} onClick={() => setEntity(e)} className={cn('px-3 py-1.5 rounded-md text-xs capitalize', entity === e ? 'bg-[var(--glass-bg-hover)] text-primary-400' : 'text-dark-300 hover:text-white')}>{e}</button>
              ))}
            </div>
            <ViewToggle mode={mode} onChange={setMode} />
          </div>
        </div>

        {entity === 'fleet' && (mode === 'table'
          ? <FleetTable nodes={MOCK_FLEET} canEdit canTerminal onRestart={noop} onEnable={noop} onDisable={noop} onTerminal={noop} isPending={false} />
          : <div className={gridCls}>{MOCK_FLEET.map((n) => mode === 'compact'
              ? <CompactNodeCard key={n.uuid} node={n} canEdit canTerminal onRestart={noop} onEnable={noop} onDisable={noop} onTerminal={noop} isPending={false} />
              : <NodeCard key={n.uuid} node={n} isExpanded={false} onToggle={noop}><div className="p-2 text-xs text-dark-300">детали…</div></NodeCard>)}</div>)}

        {entity === 'nodes' && (mode === 'table'
          ? <NodesTable nodes={MOCK_NODES} canEdit canDelete onRestart={noop} onEdit={noop} onEnable={noop} onDisable={noop} onDelete={noop} onTokenManage={noop} onFetchIps={noop} />
          : <div className={gridCls}>{MOCK_NODES.map((n) => mode === 'compact'
              ? <NodeCompactCard key={n.uuid} node={n} canEdit canDelete onRestart={noop} onEdit={noop} onEnable={noop} onDisable={noop} onDelete={noop} onTokenManage={noop} onFetchIps={noop} />
              : <div key={n.uuid} className="p-4 rounded-xl bg-white/[0.025] border border-white/[0.07] text-sm text-dark-200">крупная карточка ноды (текущая) — {n.name}</div>)}</div>)}

        {entity === 'hosts' && (mode === 'table'
          ? <HostsTable hosts={MOCK_HOSTS} canEdit canDelete onEdit={noop} onEnable={noop} onDisable={noop} onDelete={noop} />
          : <div className={gridCls}>{MOCK_HOSTS.map((h) => mode === 'compact'
              ? <HostCompactCard key={h.uuid} host={h} canEdit canDelete onEdit={noop} onEnable={noop} onDisable={noop} onDelete={noop} />
              : <div key={h.uuid} className="p-4 rounded-xl bg-white/[0.025] border border-white/[0.07] text-sm text-dark-200">крупная карточка хоста (текущая) — {h.remark}</div>)}</div>)}
      </div>
    </div>
  )
}
