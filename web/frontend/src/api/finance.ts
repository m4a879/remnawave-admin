import client from './client'

export interface FinanceCategory {
  id: number
  name: string
  kind: 'expense' | 'income'
  color: string | null
  icon: string | null
  is_system: boolean
  sort_order: number
}

export interface FinanceProvider {
  id: number
  name: string
  url: string | null
  favicon_url: string | null
  notes: string | null
  items_count?: number
}

export interface FinanceItem {
  id: number
  kind: 'expense' | 'income'
  name: string
  category_id: number | null
  category_name: string | null
  category_color: string | null
  category_icon: string | null
  provider_id: number | null
  provider_name: string | null
  node_uuid: string | null
  node_name: string | null
  currency: string
  amount: number
  billing_cycle: 'monthly' | 'yearly' | 'once' | 'days'
  cycle_days: number | null
  next_due_at: string | null
  url: string | null
  notes: string | null
  status: 'active' | 'archived'
  monthly_equivalent: number
  days_left?: number
  is_overdue?: boolean
}

export interface FinancePayment {
  id: number
  item_id: number | null
  item_name: string
  kind: 'expense' | 'income'
  paid_at: string
  amount: number
  currency: string
  rate_rub: number | null
  amount_rub: number
  comment: string | null
  source: string
}

export interface FinanceRate {
  currency: string
  rate_rub: number
  is_manual: boolean
  updated_at: string
}

export interface FinanceSummary {
  base_currency: string
  monthly: { month: string; expense: number; income: number; net: number }[]
  by_category: { category: string; color: string; monthly: number }[]
  by_currency: { currency: string; expense_monthly: number; income_monthly: number }[]
  recurring: { expense: number; income: number; net: number }
}

export interface ItemPayload {
  name: string
  kind: string
  category_id?: number | null
  provider_id?: number | null
  currency: string
  amount: number
  billing_cycle: string
  cycle_days?: number | null
  next_due_at?: string | null
  url?: string | null
  notes?: string | null
  status?: string
}

export const financeApi = {
  getSummary: async (months = 6): Promise<FinanceSummary> =>
    (await client.get('/finance/summary', { params: { months } })).data,

  getUpcoming: async (days = 30): Promise<{ items: FinanceItem[] }> =>
    (await client.get('/finance/upcoming', { params: { days } })).data,

  listItems: async (params: Record<string, string | number | undefined> = {}): Promise<{ items: FinanceItem[] }> =>
    (await client.get('/finance/items', { params })).data,

  createItem: async (data: ItemPayload): Promise<FinanceItem> =>
    (await client.post('/finance/items', data)).data,

  updateItem: async (id: number, data: Partial<ItemPayload>): Promise<FinanceItem> =>
    (await client.patch(`/finance/items/${id}`, data)).data,

  deleteItem: async (id: number): Promise<void> => {
    await client.delete(`/finance/items/${id}`)
  },

  markPaid: async (id: number, data: { amount?: number; paid_at?: string; comment?: string } = {}): Promise<FinanceItem> =>
    (await client.post(`/finance/items/${id}/paid`, data)).data,

  skipCycle: async (id: number): Promise<FinanceItem> =>
    (await client.post(`/finance/items/${id}/skip`)).data,

  listPayments: async (params: Record<string, string | number | undefined> = {}): Promise<{ items: FinancePayment[] }> =>
    (await client.get('/finance/payments', { params })).data,

  createPayment: async (data: {
    item_id?: number | null; item_name?: string; kind: string
    paid_at: string; amount: number; currency: string; comment?: string
  }): Promise<{ id: number }> =>
    (await client.post('/finance/payments', data)).data,

  deletePayment: async (id: number): Promise<void> => {
    await client.delete(`/finance/payments/${id}`)
  },

  listCategories: async (): Promise<{ items: FinanceCategory[] }> =>
    (await client.get('/finance/categories')).data,

  createCategory: async (data: { name: string; kind: string; color?: string; icon?: string }): Promise<FinanceCategory> =>
    (await client.post('/finance/categories', data)).data,

  deleteCategory: async (id: number): Promise<void> => {
    await client.delete(`/finance/categories/${id}`)
  },

  listProviders: async (): Promise<{ items: FinanceProvider[] }> =>
    (await client.get('/finance/providers')).data,

  createProvider: async (data: { name: string; url?: string; notes?: string }): Promise<FinanceProvider> =>
    (await client.post('/finance/providers', data)).data,

  deleteProvider: async (id: number): Promise<void> => {
    await client.delete(`/finance/providers/${id}`)
  },

  listRates: async (): Promise<{ items: FinanceRate[]; base_currency: string }> =>
    (await client.get('/finance/rates')).data,

  setRate: async (currency: string, rate_rub: number): Promise<void> => {
    await client.put(`/finance/rates/${currency}`, { rate_rub, is_manual: true })
  },

  refreshRates: async (): Promise<{ updated: number; items: FinanceRate[] }> =>
    (await client.post('/finance/rates/refresh')).data,

  importFromPanel: async (): Promise<{ providers: number; items: number; payments: number; skipped: number; errors: string[] }> =>
    (await client.post('/finance/import-panel')).data,

  getBedolagaIncome: async (): Promise<BedolagaIncome> =>
    (await client.get('/finance/bedolaga-income')).data,

  importBedolagaMonth: async (year: number, month: number): Promise<{ month: string; amount: number; count: number; saved: boolean }> =>
    (await client.post('/finance/import-bedolaga', null, { params: { year, month } })).data,
}

export interface BedolagaIncome {
  currency: string
  total: { deposit_income: number; subscription_income: number; profit: number }
  today: { deposit_income: number; transactions_count: number }
  by_payment_method: Record<string, number>
}
