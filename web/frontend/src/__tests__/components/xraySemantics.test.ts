import { describe, it, expect } from 'vitest'
import { lintXray } from '@/components/code/xray.semantics'

/** коды находок для компактных проверок */
const codes = (cfg: unknown) => lintXray(cfg).map((i) => i.code)

describe('lintXray', () => {
  it('не падает на не-объекте', () => {
    expect(lintXray(null)).toEqual([])
    expect(lintXray('nope')).toEqual([])
    expect(lintXray(42)).toEqual([])
    expect(lintXray([])).toEqual([])
  })

  it('здоровый конфиг — без ложных срабатываний', () => {
    const cfg = {
      inbounds: [{
        tag: 'in', port: 443, protocol: 'vless',
        streamSettings: {
          network: 'tcp', security: 'reality',
          realitySettings: {
            privateKey: 'k', serverNames: ['a.com'], shortIds: ['ab'], target: 'a.com:443',
          },
        },
      }],
      outbounds: [
        { tag: 'direct', protocol: 'freedom' },
        { tag: 'block', protocol: 'blackhole' },
      ],
      routing: { rules: [{ type: 'field', protocol: ['bittorrent'], outboundTag: 'block' }] },
    }
    expect(lintXray(cfg)).toHaveLength(0)
  })

  it('ловит дубли tag у inbounds и outbounds', () => {
    const c = codes({
      inbounds: [{ tag: 'x', port: 1 }, { tag: 'x', port: 2 }],
      outbounds: [{ tag: 'o', protocol: 'freedom' }, { tag: 'o', protocol: 'freedom' }],
    })
    expect(c).toContain('dupInboundTag')
    expect(c).toContain('dupOutboundTag')
  })

  it('ловит конфликт порта, но не при разных listen', () => {
    const conflict = {
      inbounds: [{ tag: 'a', port: 443 }, { tag: 'b', port: 443 }],
      outbounds: [{ tag: 'd', protocol: 'freedom' }],
    }
    const distinct = {
      inbounds: [
        { tag: 'a', listen: '127.0.0.1', port: 443 },
        { tag: 'b', listen: '0.0.0.0', port: 443 },
      ],
      outbounds: [{ tag: 'd', protocol: 'freedom' }],
    }
    expect(codes(conflict)).toContain('dupPort')
    expect(codes(distinct)).not.toContain('dupPort')
  })

  it('ловит битую ссылку routing → outbounds', () => {
    const c = codes({
      inbounds: [{ tag: 'in', port: 443 }],
      outbounds: [{ tag: 'direct', protocol: 'freedom' }],
      routing: { rules: [{ type: 'field', domain: ['x'], outboundTag: 'warp' }] },
    })
    expect(c).toContain('unknownOutboundTag')
  })

  it('ловит правило маршрутизации без действия', () => {
    const c = codes({
      inbounds: [{ tag: 'in', port: 443 }],
      outbounds: [{ tag: 'direct', protocol: 'freedom' }],
      routing: { rules: [{ type: 'field', domain: ['x'] }] },
    })
    expect(c).toContain('ruleNoAction')
  })

  it('неполный Reality — четыре замечания', () => {
    const c = codes({
      inbounds: [{
        tag: 'in', port: 443, protocol: 'vless',
        streamSettings: { network: 'tcp', security: 'reality', realitySettings: {} },
      }],
      outbounds: [{ tag: 'd', protocol: 'freedom' }],
    })
    expect(c).toEqual(expect.arrayContaining([
      'realityNoPrivateKey', 'realityNoServerNames', 'realityNoShortIds', 'realityNoTarget',
    ]))
  })

  it('Reality без блока realitySettings', () => {
    const c = codes({
      inbounds: [{ tag: 'in', port: 443, streamSettings: { security: 'reality' } }],
      outbounds: [{ tag: 'd', protocol: 'freedom' }],
    })
    expect(c).toContain('realityNoSettings')
  })

  it('транспорт: WS без path, gRPC без serviceName', () => {
    const ws = {
      inbounds: [{ tag: 'w', port: 80, streamSettings: { network: 'ws' } }],
      outbounds: [{ tag: 'd', protocol: 'freedom' }],
    }
    const grpc = {
      inbounds: [{ tag: 'g', port: 80, streamSettings: { network: 'grpc' } }],
      outbounds: [{ tag: 'd', protocol: 'freedom' }],
    }
    expect(codes(ws)).toContain('wsNoPath')
    expect(codes(grpc)).toContain('grpcNoService')
  })

  it('WireGuard: без secretKey и без peers', () => {
    const noKey = {
      inbounds: [{ tag: 'i', port: 1 }],
      outbounds: [{ tag: 'warp', protocol: 'wireguard', settings: {} }],
    }
    const noPeers = {
      inbounds: [{ tag: 'i', port: 1 }],
      outbounds: [{ tag: 'warp', protocol: 'wireguard', settings: { secretKey: 'k' } }],
    }
    expect(codes(noKey)).toContain('wgNoSecretKey')
    expect(codes(noPeers)).toContain('wgNoPeers')
  })

  it('пустые секции — noInbounds/noOutbounds', () => {
    expect(codes({ inbounds: [], outbounds: [] }))
      .toEqual(expect.arrayContaining(['noInbounds', 'noOutbounds']))
  })
})
