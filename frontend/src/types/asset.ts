export type AssetType = 'image' | 'video' | 'document' | 'audio' | 'other'

export type AssetProcessingStatus =
  | 'pending'
  | 'processing'
  | 'ready'
  | 'failed'

export interface Asset {
  id: string
  company_id: string
  name: string
  original_filename: string
  asset_type: AssetType
  mime_type: string
  file_size_bytes: number
  file_key: string
  file_url?: string
  thumbnail_url?: string
  processing_status: AssetProcessingStatus
  tags: string[] | null
  category?: string
  source_description?: string
  metadata?: Record<string, any> & { vision_analysis?: { status?: string; caption?: string; visual_description?: string; error?: string; detail?: string } }
  width?: number
  height?: number
  resolution?: string
  uploaded_by: string
  is_available: boolean
  created_at: string
  updated_at: string
}

export interface UploadAssetRequest {
  file: File
  name?: string
  tags?: string[]
  onProgress?: (percent: number) => void
}
