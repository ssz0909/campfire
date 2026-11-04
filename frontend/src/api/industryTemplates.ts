import apiClient from './client'

export interface IndustryOption { code: string; name: string; version: number; description: string }
export interface TemplateContent {
  name: string; description: string; positioning: string
  themes: string[]; material_hints: string[]; terminology: string[]
  forbidden_expressions: string[]; selection_keywords: string[]
  publish_tone: string; copy_guidance: string
}
export interface IndustryTemplate {
  code: string; enabled: boolean; draft: TemplateContent; draft_revision: number; published_version: number
  versions: {version: number; content: TemplateContent; created_at: string}[]; preview: string
}
export interface TemplateSnapshot {industry_code: string; name: string; version: number; resolved_from: string; content_hash: string}
export const industryTemplatesApi = {
  catalog: () => apiClient.get<IndustryOption[]>('/industries'),
  list: () => apiClient.get<IndustryTemplate[]>('/admin/industry-templates'),
  create: (code: string, content: TemplateContent) => apiClient.post<IndustryTemplate>('/admin/industry-templates', {code, content}),
  save: (row: IndustryTemplate, content: TemplateContent) => apiClient.put<IndustryTemplate>(`/admin/industry-templates/${row.code}/draft`, {expected_revision: row.draft_revision, content}),
  publish: (row: IndustryTemplate) => apiClient.post<IndustryTemplate>(`/admin/industry-templates/${row.code}/publish`, {expected_revision: row.draft_revision}),
  status: (row: IndustryTemplate, enabled: boolean) => apiClient.patch<IndustryTemplate>(`/admin/industry-templates/${row.code}/status`, {expected_revision: row.draft_revision, enabled}),
  restore: (row: IndustryTemplate, version: number) => apiClient.post<IndustryTemplate>(`/admin/industry-templates/${row.code}/versions/${version}/restore`, {expected_revision: row.draft_revision}),
}
