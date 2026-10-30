import apiClient from './client'
export interface PublishingPlatform { id?: string; label?: string; platform: string; name: string; status: string; account_name?: string; configured: boolean; session_saved?: boolean }
export interface PublishJob { id: string; platform_connection_id: string; title: string; description?: string; media_url?: string; status: string; provider_url?: string; error_message?: string; metrics?: Record<string, unknown>; content_snapshot?: {location_name?: string; account_label?: string; platform?: string} }
export const publishingApi = {
  async accounts(companyId: string) {
    const r = await apiClient.get<PublishingPlatform[]>(`/companies/${companyId}/publishing/accounts`)
    return r.data.map(row => ({...row, name: (row.platform === 'douyin' ? '抖音' : '视频号') + ' · ' + (row.label || row.account_name || '默认账号')}))
  },
  async addAccount(companyId: string, platform: string, label: string) { return (await apiClient.post(`/companies/${companyId}/publishing/accounts`, {platform, label})).data },
  async renameAccount(companyId: string, id: string, label: string) { return (await apiClient.patch(`/companies/${companyId}/publishing/accounts/${id}`, {label})).data },
  async platforms(companyId: string) { const r = await apiClient.get<{items: PublishingPlatform[]}>(`/companies/${companyId}/publishing/platforms`); return r.data },
  async authorize(companyId: string, platform: string) { const r = await apiClient.post<{authorization_url: string}>(`/companies/${companyId}/publishing/${platform}/authorize`); return r.data },
  async callback(companyId: string, platform: string, code: string, state: string) { const r = await apiClient.post(`/companies/${companyId}/publishing/${platform}/callback`, null, { params: { code, state } }); return r.data },
  async create(companyId: string, platform: string, data: Record<string, unknown>) { const r = await apiClient.post<PublishJob>(`/companies/${companyId}/publishing/${platform}/jobs`, data); return r.data },
  async submit(companyId: string, id: string) { const r = await apiClient.post<PublishJob>(`/companies/${companyId}/publishing/jobs/${id}/web-submit`, null, {timeout:300000}); return r.data },
  async republish(companyId: string, id: string, location_name?: string) { const r = await apiClient.post<PublishJob>(`/companies/${companyId}/publishing/jobs/${id}/republish`, {location_name}, {timeout:30000}); return r.data },
  async webStart(companyId: string, platform: string, connectionId?: string) { const r = await apiClient.post(`/companies/${companyId}/publishing/${platform}/web/start`, null, { timeout: 90000, params: {connection_id: connectionId} }); return r.data },
  async webView(companyId: string, platform: string, connectionId?: string) { return (await apiClient.get(`/companies/${companyId}/publishing/${platform}/web/view`, {timeout:45000, params: {connection_id: connectionId}})).data },
  async webAction(companyId: string, platform: string, data: Record<string, unknown>, connectionId?: string) { return (await apiClient.post(`/companies/${companyId}/publishing/${platform}/web/action`, data, {timeout:45000, params: {connection_id: connectionId}})).data },
  async webStatus(companyId: string, platform: string, connectionId?: string) { const r = await apiClient.get(`/companies/${companyId}/publishing/${platform}/web/status`, {params: {connection_id: connectionId}}); return r.data },
  async webMetrics(companyId: string, id: string) { const r = await apiClient.post<PublishJob>(`/companies/${companyId}/publishing/jobs/${id}/web-metrics`, null, {timeout:180000}); return r.data },
  async webLogout(companyId: string, platform: string, connectionId?: string) { return apiClient.post(`/companies/${companyId}/publishing/${platform}/web/logout`, null, {params: {connection_id: connectionId}}) },
  async jobs(companyId: string) { const r = await apiClient.get<{items: PublishJob[]}>(`/companies/${companyId}/publishing/jobs`); return r.data.items },
}
