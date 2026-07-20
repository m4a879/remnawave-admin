/**
 * Семантическая валидация xray-конфига поверх JSON-схемы.
 *
 * Схема (ajv) ловит структуру и типы; здесь — смысловые проблемы, которые
 * схема увидеть не может: ссылочная целостность (routing → outbounds),
 * дубли tag/port, полнота Reality/TLS/транспорта, неполный WireGuard.
 *
 * Все находки — advisory: они НЕ блокируют сохранение, финальный арбитр —
 * панель. Функция чистая и без i18n: возвращает code + params, текст
 * резолвит вызывающая сторона (resources.editor.lint.<code>).
 */

export interface XrayIssue {
  /** ключ i18n: resources.editor.lint.<code> */
  code: string
  /** параметры интерполяции сообщения */
  params?: Record<string, string | number>
  /** подстрока для позиционирования подсветки (ищется через indexOf) */
  anchor?: string
  /** сколько вхождений anchor пропустить (для второго дубля и т.п.) */
  anchorSkip?: number
}

type AnyObj = Record<string, unknown>

const isObj = (v: unknown): v is AnyObj =>
  typeof v === 'object' && v !== null && !Array.isArray(v)
const asArr = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null)

/** Проверяет xray-конфиг на смысловые проблемы. Ошибки не бросает. */
export function lintXray(cfg: unknown): XrayIssue[] {
  if (!isObj(cfg)) return []
  const issues: XrayIssue[] = []
  const inbounds = asArr(cfg.inbounds)
  const outbounds = asArr(cfg.outbounds)
  const routing = isObj(cfg.routing) ? cfg.routing : {}
  const rules = asArr(routing.rules)
  const balancers = asArr(routing.balancers)

  // ── теги outbounds (+ дубли) ─────────────────────────────────────
  const outTags = new Set<string>()
  const outDup = new Set<string>()
  for (const o of outbounds) {
    const tag = isObj(o) ? str(o.tag) : null
    if (tag === null) continue
    if (outTags.has(tag)) outDup.add(tag)
    outTags.add(tag)
  }
  for (const tag of outDup) {
    issues.push({ code: 'dupOutboundTag', params: { tag }, anchor: `"${tag}"`, anchorSkip: 1 })
  }

  // ── inbounds: дубли tag и port ───────────────────────────────────
  const inTags = new Set<string>()
  const inDup = new Set<string>()
  const portCount = new Map<string, number>()
  for (const i of inbounds) {
    if (!isObj(i)) continue
    const tag = str(i.tag)
    if (tag !== null) {
      if (inTags.has(tag)) inDup.add(tag)
      inTags.add(tag)
    }
    // port может быть числом или строкой ("443"/"1000-2000") — object (диапазоны) пропускаем
    if (i.port !== undefined && i.port !== null && typeof i.port !== 'object') {
      const key = `${i.listen ?? '*'}:${i.port}`
      portCount.set(key, (portCount.get(key) ?? 0) + 1)
    }
  }
  for (const tag of inDup) {
    issues.push({ code: 'dupInboundTag', params: { tag }, anchor: `"${tag}"`, anchorSkip: 1 })
  }
  for (const [key, count] of portCount) {
    if (count > 1) {
      const port = key.slice(key.indexOf(':') + 1)
      issues.push({ code: 'dupPort', params: { port } })
    }
  }

  // ── routing: ссылочная целостность + действие ────────────────────
  const balancerTags = new Set<string>()
  for (const b of balancers) {
    const tag = isObj(b) ? str(b.tag) : null
    if (tag !== null) balancerTags.add(tag)
  }
  for (const r of rules) {
    if (!isObj(r)) continue
    const ot = str(r.outboundTag)
    const bt = str(r.balancerTag)
    if (ot !== null && !outTags.has(ot)) {
      issues.push({ code: 'unknownOutboundTag', params: { tag: ot }, anchor: `"${ot}"` })
    }
    if (bt !== null && !balancerTags.has(bt)) {
      issues.push({ code: 'unknownBalancerTag', params: { tag: bt }, anchor: `"${bt}"` })
    }
    if (r.outboundTag === undefined && r.balancerTag === undefined) {
      issues.push({ code: 'ruleNoAction' })
    }
  }
  if (rules.length && !outbounds.length) {
    issues.push({ code: 'routingNoOutbounds' })
  }

  // ── наличие базовых секций ───────────────────────────────────────
  if (!inbounds.length) issues.push({ code: 'noInbounds' })
  if (!outbounds.length) issues.push({ code: 'noOutbounds' })

  // ── per-inbound: stream / security / транспорт ───────────────────
  for (const i of inbounds) {
    if (!isObj(i)) continue
    const tag = str(i.tag) ?? str(i.protocol) ?? 'inbound'
    const ss = isObj(i.streamSettings) ? i.streamSettings : null
    if (!ss) continue
    const security = str(ss.security)
    const network = str(ss.network) ?? str(ss.type)

    if (security === 'reality') {
      const rs = isObj(ss.realitySettings) ? ss.realitySettings : null
      if (!rs) {
        issues.push({ code: 'realityNoSettings', params: { tag }, anchor: '"reality"' })
      } else {
        if (!rs.privateKey) {
          issues.push({ code: 'realityNoPrivateKey', params: { tag }, anchor: '"realitySettings"' })
        }
        if (!asArr(rs.serverNames).length) {
          issues.push({ code: 'realityNoServerNames', params: { tag }, anchor: '"realitySettings"' })
        }
        if (!asArr(rs.shortIds).length) {
          issues.push({ code: 'realityNoShortIds', params: { tag }, anchor: '"realitySettings"' })
        }
        if (!rs.dest && !rs.target) {
          issues.push({ code: 'realityNoTarget', params: { tag }, anchor: '"realitySettings"' })
        }
      }
    } else if (security === 'tls') {
      const ts = isObj(ss.tlsSettings) ? ss.tlsSettings : null
      const certs = ts ? asArr(ts.certificates) : []
      const hasCert = certs.some(
        (c) => isObj(c) && (c.certificateFile || c.keyFile || c.certificate || c.key),
      )
      if (!hasCert) {
        issues.push({ code: 'tlsNoCert', params: { tag }, anchor: '"tls"' })
      }
    }

    if (network === 'ws') {
      const w = isObj(ss.wsSettings) ? ss.wsSettings : null
      if (!w || !w.path) issues.push({ code: 'wsNoPath', params: { tag }, anchor: '"ws"' })
    } else if (network === 'grpc') {
      const g = isObj(ss.grpcSettings) ? ss.grpcSettings : null
      if (!g || !g.serviceName) issues.push({ code: 'grpcNoService', params: { tag }, anchor: '"grpc"' })
    } else if (network === 'httpupgrade') {
      const h = isObj(ss.httpupgradeSettings) ? ss.httpupgradeSettings : null
      if (!h || !h.path) issues.push({ code: 'httpupgradeNoPath', params: { tag }, anchor: '"httpupgrade"' })
    }
  }

  // ── WireGuard outbounds (WARP): неполная настройка ───────────────
  for (const o of outbounds) {
    if (!isObj(o) || o.protocol !== 'wireguard') continue
    const tag = str(o.tag) ?? 'wireguard'
    const s = isObj(o.settings) ? o.settings : null
    if (!s || !s.secretKey) {
      issues.push({ code: 'wgNoSecretKey', params: { tag }, anchor: '"wireguard"' })
    } else if (!asArr(s.peers).length) {
      issues.push({ code: 'wgNoPeers', params: { tag }, anchor: '"peers"' })
    }
  }

  return issues
}
