import client from './client'

// Пресет создания юзера — именованный набор дефолтов формы (хранится у нас)
export interface UserPresetData {
  expire_days?: number | null
  traffic_limit_bytes?: number | null
  traffic_limit_strategy?: string | null
  hwid_device_limit?: number | null
  active_internal_squads?: string[] | null
  tag?: string | null
  description?: string | null
  status?: string | null
}

export interface UserPreset {
  id: number
  name: string
  data: UserPresetData
  created_by: string | null
  created_at: string | null
  updated_at: string | null
}

export const userPresetsApi = {
  list: async (): Promise<{ items: UserPreset[] }> =>
    (await client.get('/user-presets')).data,
  create: async (name: string, data: UserPresetData): Promise<UserPreset> =>
    (await client.post('/user-presets', { name, data })).data,
  update: async (id: number, body: { name?: string; data?: UserPresetData }): Promise<UserPreset> =>
    (await client.patch(`/user-presets/${id}`, body)).data,
  remove: async (id: number): Promise<void> => {
    await client.delete(`/user-presets/${id}`)
  },
}
