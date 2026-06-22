/**
 * TEMPORARY preview of the list view modes (public route `/viewdemo`).
 * Mock fleet data so the table / compact / large views can be reviewed without
 * a backend. Remove this file and its route before release.
 */
import { useState } from 'react'
import { ViewToggle } from '@/components/ViewToggle'
import type { ViewMode } from '@/lib/useViewMode'
import { FleetTable } from '@/components/fleet/FleetTable'
import { CompactNodeCard } from '@/components/fleet/CompactNodeCard'
import NodeCard, { type FleetNode } from '@/components/fleet/NodeCard'
import { cn } from '@/lib/utils'

const N = (over: Partial<FleetNode>): FleetNode => ({
  uuid: Math.random().toString(36).slice(2),
  name: 'node',
  address: '10.0.0.1',
  port: 2222,
  is_connected: true,
  is_disabled: false,
  is_xray_running: true,
  xray_version: '25.3.6',
  users_online: 0,
  traffic_today_bytes: 0,
  traffic_total_bytes: 0,
  uptime_seconds: 0,
  cpu_usage: null,
  cpu_cores: 4,
  memory_usage: null,
  memory_total_bytes: 8 * 1e9,
  memory_used_bytes: 0,
  disk_usage: null,
  disk_total_bytes: 100 * 1e9,
  disk_used_bytes: 0,
  disk_read_speed_bps: 0,
  disk_write_speed_bps: 0,
  last_seen_at: '2026-06-22T08:00:00Z',
  download_speed_bps: 0,
  upload_speed_bps: 0,
  metrics_updated_at: '2026-06-22T08:00:00Z',
  ...over,
})

const MOCK: FleetNode[] = [
  N({ name: 'de-frankfurt-1', address: '49.12.5.10', users_online: 128, cpu_usage: 42, memory_usage: 61, disk_usage: 38, uptime_seconds: 1_900_000, download_speed_bps: 84_000_000, upload_speed_bps: 22_000_000, traffic_today_bytes: 412e9, traffic_total_bytes: 18e12 }),
  N({ name: 'nl-amsterdam-2', address: '5.255.103.4', users_online: 96, cpu_usage: 88, memory_usage: 94, disk_usage: 70, uptime_seconds: 720_000, download_speed_bps: 51_000_000, upload_speed_bps: 13_000_000, traffic_today_bytes: 280e9, traffic_total_bytes: 9e12 }),
  N({ name: 'sg-singapore-1', address: '103.27.8.9', users_online: 210, cpu_usage: 97, memory_usage: 80, disk_usage: 91, uptime_seconds: 5_400_000, download_speed_bps: 120_000_000, upload_speed_bps: 38_000_000, traffic_today_bytes: 640e9, traffic_total_bytes: 41e12 }),
  N({ name: 'fi-helsinki-3', address: '95.216.1.2', users_online: 54, cpu_usage: 12, memory_usage: 30, disk_usage: 22, uptime_seconds: 260_000, download_speed_bps: 18_000_000, upload_speed_bps: 6_000_000, traffic_today_bytes: 96e9, traffic_total_bytes: 3e12 }),
  N({ name: 'us-newyork-1', address: '23.105.7.7', is_connected: false, users_online: 0, xray_version: null }),
  N({ name: 'ru-moscow-1', address: '45.67.230.5', is_disabled: true, is_connected: false, users_online: 0, cpu_usage: null, memory_usage: null }),
]

export default function ViewDemo() {
  const [mode, setMode] = useState<ViewMode>(() => {
    const m = new URLSearchParams(window.location.search).get('mode')
    return m === 'compact' || m === 'large' || m === 'table' ? m : 'table'
  })
  const noop = () => {}

  return (
    <div className="min-h-screen bg-[#070b13] text-white p-6 sm:p-10">
      <div className="max-w-6xl mx-auto space-y-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold">Fleet — режимы отображения <span style={{ color: 'var(--accent-from)' }}>(preview)</span></h1>
            <p className="text-sm text-dark-300 mt-1">Моковые ноды. Переключай вид справа. Сортировка/фильтры в таблице — по заголовкам.</p>
          </div>
          <ViewToggle mode={mode} onChange={setMode} />
        </div>

        {mode === 'table' ? (
          <FleetTable nodes={MOCK} canEdit canTerminal onRestart={noop} onEnable={noop} onDisable={noop} onTerminal={noop} isPending={false} />
        ) : (
          <div
            className={cn(
              'grid gap-4',
              mode === 'compact'
                ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'
                : 'grid-cols-1 lg:grid-cols-2 xl:grid-cols-3',
            )}
          >
            {MOCK.map((node) =>
              mode === 'compact' ? (
                <CompactNodeCard key={node.uuid} node={node} canEdit canTerminal onRestart={noop} onEnable={noop} onDisable={noop} onTerminal={noop} isPending={false} />
              ) : (
                <NodeCard key={node.uuid} node={node} isExpanded={false} onToggle={noop}>
                  <div className="p-2 text-xs text-dark-300">детали…</div>
                </NodeCard>
              ),
            )}
          </div>
        )}
      </div>
    </div>
  )
}
