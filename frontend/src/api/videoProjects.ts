import apiClient from './client'
import type { VideoProject } from '@/types/videoProject'

export const videoProjectsApi = {
  create(companyId: string, data: Partial<VideoProject> & {selected_asset_ids?:string[]}): Promise<{ data: VideoProject }> {
    return apiClient.post(`/companies/${companyId}/video-projects`, data)
  },

  async list(companyId: string, params?: { status?: string; page?: number; limit?: number }): Promise<{ data: VideoProject[] }> {
    const response = await apiClient.get<VideoProject[] | { items: VideoProject[] }>(`/companies/${companyId}/video-projects`, {
      params: { status: params?.status, page: params?.page, page_size: params?.limit },
    })
    return { data: (Array.isArray(response.data) ? response.data : response.data.items).map((p) => normalize({ data:p }).data) }
  },

  get(companyId: string, projectId: string): Promise<{ data: VideoProject }> {
    return apiClient.get(`/companies/${companyId}/video-projects/${projectId}`).then(normalize)
  },

  start(companyId: string, projectId: string): Promise<{ data: VideoProject }> {
    return apiClient.post(`/companies/${companyId}/video-projects/${projectId}/start`).then(normalize)
  },

  retry(companyId: string, projectId: string): Promise<{ data: VideoProject }> {
    return apiClient.post(`/companies/${companyId}/video-projects/${projectId}/retry`).then(normalize)
  },

  approve(companyId: string, projectId: string): Promise<{ data: VideoProject }> {
    return apiClient.post(`/companies/${companyId}/video-projects/${projectId}/approve`)
  },

  updateStoryboard(companyId: string, projectId: string, shots: Partial<VideoProject['shots']>): Promise<{ data: VideoProject }> {
    return apiClient.patch(`/companies/${companyId}/video-projects/${projectId}/storyboard`, { storyboard: shots })
  },

  regenerateShot(companyId: string, projectId: string, shotId: string): Promise<{ data: VideoProject }> {
    return apiClient.post(`/companies/${companyId}/video-projects/${projectId}/shots/${shotId}/regenerate`)
  },
}

function normalize(response: any) {
  const p = response.data
  p.status = p.project_status || p.status
  p.final_video_url = p.output_video_url || p.final_video_url
  p.shots = (p.storyboard || p.shots || []).map((s: any, i: number) => ({ ...s, id: s.id || String(s.shot_number || i+1), sequence_number: s.sequence_number || s.shot_number || i+1, status: s.status || (s.generation_status === 'completed' ? 'ready' : 'pending') }))
  return response
}
