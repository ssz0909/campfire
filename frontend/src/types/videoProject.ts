export type VideoProjectStatus =
  | 'draft'
  | 'script_ready'
  | 'storyboard_ready'
  | 'generating'
  | 'compositing'
  | 'completed'
  | 'failed'
  | 'analyzing'
  | 'generating_shots'
  | 'pending_review'

export type ShotStatus =
  | 'pending'
  | 'generating'
  | 'ready'
  | 'failed'
  | 'approved'

export type CreationMode = 'ai_creative' | 'reference_inspired'

export interface ReferenceAnalysis {
  style_description: string
  color_palette: string[]
  tone: string
  pacing: string
  key_elements: string[]
}

export interface Shot {
  id: string
  project_id: string
  sequence_number: number
  visual_description: string
  voiceover_text?: string
  purpose?: string
  framing?: string
  camera_movement?: string
  source_asset_id?: string
  generation_prompt?: string
  opening_frame?: string
  closing_frame?: string
  transition_out?: 'cut' | 'match_cut' | 'dissolve' | 'fade'
  transition_duration_seconds?: number
  transition_notes?: string
  duration_seconds: number
  status: ShotStatus
  asset_url?: string
  thumbnail_url?: string
  generation_params?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface VideoProject {
  music_asset_id?: string|null
  music_volume?: number
  id: string
  company_id: string
  title: string
  creation_mode: CreationMode
  status: VideoProjectStatus
  script?: string
  aspect_ratio?: string
  reference_asset_id?: string
  selected_asset_ids?: string[] | null
  reference_analysis?: ReferenceAnalysis
  shots: Shot[]
  target_duration_seconds?: number
  estimated_duration_seconds?: number
  estimated_cost_usd?: number
  final_video_url?: string
  output_asset_id?: string
  output_thumbnail_url?: string
  output_video_url?: string
  publish_title?: string
  publish_description?: string
  publish_platforms?: string[]
  publish_accounts?: {id: string; platform: string; label: string}[]
  quality_check_result?: { status?: string; note?: string }
  created_by: string
  created_at: string
  updated_at: string
}
