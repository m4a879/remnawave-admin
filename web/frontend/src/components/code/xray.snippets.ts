/**
 * Библиотека готовых блоков xray-конфига для встроенного редактора.
 *
 * Каждый блок — валидный фрагмент со «здоровыми» дефолтами (плейсхолдеры
 * ключей/паролей подписаны КАПСОМ, чтобы их нельзя было проглядеть).
 * `category` — группа в меню; `target` — куда блок добавляется при вставке.
 * Тексты (label/desc) резолвятся по i18n: resources.editor.blocks.items.<id>.
 */

export type SnippetCategory = 'outbounds' | 'inbounds' | 'routing' | 'dns'
export type SnippetTarget = 'outbounds' | 'inbounds' | 'routingRules' | 'dns'

export interface XraySnippet {
  id: string
  category: SnippetCategory
  target: SnippetTarget
  /** строит свежий объект блока (каждый вызов — новый, без общих ссылок) */
  build: () => Record<string, unknown>
}

// Публичный ключ Cloudflare WARP (общеизвестный, не секрет) —
// secretKey/address пользователь подставляет из своей WARP-регистрации.
const WARP_PUBLIC_KEY = 'bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo='

export const XRAY_SNIPPETS: XraySnippet[] = [
  // ── Outbounds ──────────────────────────────────────────────────
  {
    id: 'freedomDirect',
    category: 'outbounds',
    target: 'outbounds',
    build: () => ({ tag: 'direct', protocol: 'freedom', settings: {} }),
  },
  {
    id: 'blackhole',
    category: 'outbounds',
    target: 'outbounds',
    build: () => ({ tag: 'block', protocol: 'blackhole', settings: {} }),
  },
  {
    id: 'dnsOut',
    category: 'outbounds',
    target: 'outbounds',
    build: () => ({ tag: 'dns-out', protocol: 'dns', settings: {} }),
  },
  {
    id: 'warp',
    category: 'outbounds',
    target: 'outbounds',
    build: () => ({
      tag: 'warp',
      protocol: 'wireguard',
      settings: {
        secretKey: 'REPLACE_WITH_WG_SECRET_KEY',
        address: ['172.16.0.2/32', '2606:4700:110:8949::/128'],
        peers: [
          {
            publicKey: WARP_PUBLIC_KEY,
            endpoint: 'engage.cloudflarewarp.com:2408',
            allowedIPs: ['0.0.0.0/0', '::/0'],
          },
        ],
        mtu: 1280,
      },
    }),
  },
  {
    id: 'fragment',
    category: 'outbounds',
    target: 'outbounds',
    build: () => ({
      tag: 'fragment',
      protocol: 'freedom',
      settings: {
        domainStrategy: 'UseIP',
        fragment: { packets: 'tlshello', length: '100-200', interval: '10-20' },
      },
      streamSettings: { sockopt: { tcpNoDelay: true } },
    }),
  },

  // ── Inbounds ───────────────────────────────────────────────────
  {
    id: 'vlessReality',
    category: 'inbounds',
    target: 'inbounds',
    build: () => ({
      tag: 'vless-reality',
      listen: '0.0.0.0',
      port: 443,
      protocol: 'vless',
      settings: { clients: [], decryption: 'none' },
      streamSettings: {
        network: 'tcp',
        security: 'reality',
        realitySettings: {
          show: false,
          target: 'www.microsoft.com:443',
          xver: 0,
          serverNames: ['www.microsoft.com'],
          privateKey: 'REPLACE_WITH_REALITY_PRIVATE_KEY',
          shortIds: [''],
        },
      },
      sniffing: { enabled: true, destOverride: ['http', 'tls', 'quic'] },
    }),
  },
  {
    id: 'ss2022',
    category: 'inbounds',
    target: 'inbounds',
    build: () => ({
      tag: 'shadowsocks',
      listen: '0.0.0.0',
      port: 8388,
      protocol: 'shadowsocks',
      settings: {
        method: '2022-blake3-aes-256-gcm',
        password: 'REPLACE_WITH_SERVER_PSK',
        network: 'tcp,udp',
      },
    }),
  },
  {
    id: 'dokodemoDns',
    category: 'inbounds',
    target: 'inbounds',
    build: () => ({
      tag: 'dns-in',
      listen: '0.0.0.0',
      port: 5353,
      protocol: 'dokodemo-door',
      settings: { address: '1.1.1.1', port: 53, network: 'tcp,udp' },
    }),
  },

  // ── Routing rules ──────────────────────────────────────────────
  {
    id: 'blockTorrent',
    category: 'routing',
    target: 'routingRules',
    build: () => ({ type: 'field', protocol: ['bittorrent'], outboundTag: 'block' }),
  },
  {
    id: 'blockAds',
    category: 'routing',
    target: 'routingRules',
    build: () => ({ type: 'field', domain: ['geosite:category-ads-all'], outboundTag: 'block' }),
  },
  {
    id: 'blockPrivate',
    category: 'routing',
    target: 'routingRules',
    build: () => ({ type: 'field', ip: ['geoip:private'], outboundTag: 'block' }),
  },
  {
    id: 'openaiWarp',
    category: 'routing',
    target: 'routingRules',
    build: () => ({ type: 'field', domain: ['geosite:openai'], outboundTag: 'warp' }),
  },
  {
    id: 'googleWarp',
    category: 'routing',
    target: 'routingRules',
    build: () => ({ type: 'field', domain: ['geosite:google'], outboundTag: 'warp' }),
  },

  // ── DNS ────────────────────────────────────────────────────────
  {
    id: 'dnsBasic',
    category: 'dns',
    target: 'dns',
    build: () => ({ servers: ['1.1.1.1', '8.8.8.8', 'localhost'], queryStrategy: 'UseIP' }),
  },
]

/** Порядок и подписи групп в меню. */
export const SNIPPET_CATEGORIES: SnippetCategory[] = ['inbounds', 'outbounds', 'routing', 'dns']
