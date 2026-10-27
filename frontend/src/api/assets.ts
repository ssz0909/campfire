import apiClient from './client'
import type { Asset, UploadAssetRequest } from '@/types/asset'

export const assetsApi = {
  upload(companyId: string, req: UploadAssetRequest): Promise<{ data: Asset }> {
    const formData = new FormData()
    formData.append('file', req.file)
    if (req.name) formData.append('name', req.name)
    if (req.tags) formData.append('tags', JSON.stringify(req.tags))

    return apiClient.post(`/companies/${companyId}/assets/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (req.onProgress && e.total) {
          req.onProgress(Math.round((e.loaded * 100) / e.total))
        }
      },
    })
  },

  async list(companyId: string, params?: { type?: string; page?: number; limit?: number; category?: string; q?: string; tag?: string }): Promise<{ data: Asset[] }> {
    const response = await apiClient.get<Asset[] | { items: Asset[] }>(`/companies/${companyId}/assets`, {
      params: { asset_type: params?.type, page: params?.page, page_size: params?.limit, category: params?.category, q: params?.q, tag: params?.tag },
    })
    return { data: Array.isArray(response.data) ? response.data : response.data.items }
  },
  analyze(companyId: string, assetId: string): Promise<{ data: Asset }> {
    return apiClient.post(`/companies/${companyId}/assets/${assetId}/analyze`, null, {timeout:150000})
  },

  get(companyId: string, assetId: string): Promise<{ data: Asset }> {
    return apiClient.get(`/companies/${companyId}/assets/${assetId}`)
  },

  getDownloadUrl(companyId: string, assetId: string): Promise<{ data: { url: string } }> {
    return apiClient.get<{download_url:string}>(`/companies/${companyId}/assets/${assetId}/download-url`).then(r=>({data:{url:r.data.download_url}}))
  },

  update(companyId: string, assetId: string, data: { name?: string; tags?: string[]; category?: string; source_description?: string }): Promise<{ data: Asset }> {
    return apiClient.patch(`/companies/${companyId}/assets/${assetId}`, data)
  },

  delete(companyId: string, assetId: string): Promise<void> {
    return apiClient.delete(`/companies/${companyId}/assets/${assetId}`)
  },
}
