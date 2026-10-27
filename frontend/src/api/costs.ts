import apiClient from './client'
import type { CostRecord, UsageSummary } from '@/types/cost'

export const costsApi = {
  async list(companyId: string, params?: { page?: number; limit?: number }): Promise<{ data: CostRecord[] }> {
    const response = await apiClient.get<CostRecord[] | { items: CostRecord[] }>(`/companies/${companyId}/costs`, {
      params: { page: params?.page, page_size: params?.limit },
    })
    return { data: Array.isArray(response.data) ? response.data : response.data.items }
  },

  summary(companyId: string): Promise<{ data: UsageSummary }> {
    return apiClient.get(`/companies/${companyId}/costs/summary`)
  },

  usage(companyId: string): Promise<{ data: UsageSummary }> {
    return apiClient.get(`/companies/${companyId}/costs/usage`)
  },
}
