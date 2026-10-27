import apiClient from './client'
import type { OverviewStats, OrderMetrics, OrderMetricsParams, ContentMetrics } from '@/types/analytics'

export const analyticsApi = {
  overview(companyId: string): Promise<{ data: OverviewStats }> {
    return apiClient.get(`/companies/${companyId}/analytics/overview`)
  },

  orders(companyId: string, params?: OrderMetricsParams): Promise<{ data: OrderMetrics }> {
    return apiClient.get(`/companies/${companyId}/analytics/orders`, { params })
  },

  content(companyId: string, period?: string): Promise<{ data: ContentMetrics }> {
    return apiClient.get(`/companies/${companyId}/analytics/content`, { params: { period } })
  },

  tasks(companyId: string, period?: string): Promise<{ data: Record<string, unknown> }> {
    return apiClient.get(`/companies/${companyId}/analytics/tasks`, { params: { period } })
  },
}
