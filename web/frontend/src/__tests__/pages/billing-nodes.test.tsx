/**
 * Regression: биллинг-ноды 2.8.0 с пользовательским названием (node=null)
 * должны рендериться без краша ("can't access property countryCode, i.node is null").
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TooltipProvider } from '@/components/ui/tooltip'
import { usePermissionStore } from '@/store/permissionStore'
import { useAuthStore } from '@/store/authStore'

vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn((url: string) => {
      if (url === '/billing/nodes') {
        return Promise.resolve({
          data: {
            billingNodes: [
              {
                uuid: 'bn-real',
                nodeUuid: 'node-1',
                name: null,
                provider: { uuid: 'prov-1', name: 'Hetzner' },
                node: { uuid: 'node-1', name: 'Germany W', countryCode: 'DE' },
                nextBillingAt: '2099-01-01T00:00:00.000Z',
                createdAt: '2026-01-01T00:00:00.000Z',
              },
              {
                uuid: 'bn-custom',
                nodeUuid: null,
                name: 'Management Server',
                provider: { uuid: 'prov-1', name: 'Hetzner' },
                node: null,
                nextBillingAt: '2099-02-01T00:00:00.000Z',
                createdAt: '2026-01-01T00:00:00.000Z',
              },
            ],
            totalBillingNodes: 2,
            stats: { upcomingNodesCount: 0, currentMonthPayments: 0, totalSpent: 0 },
          },
        })
      }
      return Promise.resolve({ data: { items: [], total: 0 } })
    }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    patch: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
    defaults: { baseURL: '/api/v2' },
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}))

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  }),
  Toaster: () => null,
}))

function renderPage(ui: React.ReactElement, { route = '/' } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({
    user: { username: 'admin', firstName: 'Admin', authMethod: 'password' },
    accessToken: 'test-token',
    refreshToken: 'test-refresh',
    isAuthenticated: true,
    isLoading: false,
    error: null,
  })
  usePermissionStore.setState({
    permissions: [],
    role: 'superadmin',
    roleId: 1,
    isLoaded: true,
  })
})

describe('Billing nodes tab', () => {
  it('renders custom-named billing node (node=null) without crashing', async () => {
    const Billing = (await import('@/pages/Billing')).default
    renderPage(<Billing />, { route: '/?tab=nodes' })

    expect(await screen.findByText('Management Server')).toBeTruthy()
    expect(screen.getByText('Germany W')).toBeTruthy()
    expect(screen.getByText('DE')).toBeTruthy()
  })
})
