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

  async list(companyId: string, params?: { type?: string; page?: number; limit?: number; category?: string; q?: string; tag?: string }): Promise<{ data: Asset[]; total: number }> {
    const response = await apiClient.get<Asset[] | { items: Asset[]; total: number }>(`/companies/${companyId}/assets`, {
      params: { asset_type: params?.type, page: params?.page, page_size: params?.limit, category: params?.category, q: params?.q, tag: params?.tag },
    })
    return Array.isArray(response.data) ? { data: response.data, total: response.data.length } : { data: response.data.items, total: response.data.total }
  },
  analyze(companyId: string, assetId: string): Promise<{ data: Asset }> {
    return apiClient.post(`/companies/${companyId}/assets/${assetId}/analyze`, null, {timeout:150000})
  },

  regenerateClip(companyId: string, assetId: string, prompt: string, aspectRatio='9:16', requestId: string=crypto.randomUUID()): Promise<{data: {id:string;status:string;prompt:string}}> {
    return apiClient.post(`/companies/${companyId}/assets/${assetId}/regenerate-clip`, {prompt,aspect_ratio:aspectRatio,request_id:requestId}, {timeout:30000})
  },

  async relatedClips(companyId:string, assetId:string, page=1):Promise<{data:Asset;items:Asset[];total:number;jobs:Array<{id:string;status:string;error?:string|null}>}> {
    const response=await apiClient.get(`/companies/${companyId}/assets/${assetId}/clips`, {params:{page,page_size:10}})
    return {data:response.data.source,items:response.data.items,total:response.data.total,jobs:response.data.jobs||[]}
  },

  approveClip(companyId: string, assetId: string): Promise<{data: Asset}> {
    return apiClient.post(`/companies/${companyId}/assets/${assetId}/approve-clip`)
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
