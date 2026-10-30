<template>
  <div class="video-detail">
    <template v-if="loading">
      <AppPageHeader :title="t('Loading...')" :breadcrumbs="[{ label: t('Video'), to: '/video' }]" />
      <AppCard><AppLoader variant="card" /></AppCard>
    </template>

    <template v-else-if="!project">
      <AppPageHeader :title="t('Not found')" :breadcrumbs="[{ label: t('Video'), to: '/video' }]" />
      <AppEmpty :icon="VideocamOutline" :title="t('Project not found')" />
    </template>

    <template v-else>
      <p v-if="actionError" class="action-error" role="alert">{{ actionError }}</p>
      <AppPageHeader
        :title="project.title"
        :breadcrumbs="[{ label: t('Video'), to: '/video' }]"
        :subtitle="t('{mode} · Created {date}', { mode: t(project.creation_mode.replace('_', ' ')), date: new Date(project.created_at).toLocaleDateString() })"
      >
        <template #actions>
          <StatusBadge :status="project.status" />
          <n-button
            v-if="project.status === 'completed'"
            type="primary"
            @click="router.push({ path: '/publishing', query: { video_project_id: project.id, title: project.publish_title || project.title, description: project.publish_description, media_url: project.final_video_url } })"
          >
            {{ t('发布到平台') }}
          </n-button>
          <n-button
            v-if="project.status === 'storyboard_ready'"
            type="primary"
            :loading="actionLoading"
            @click="startGeneration"
          >
            {{ t('Start Generation') }}
          </n-button>
          <n-button
            v-if="['draft', 'script_ready', 'failed'].includes(project.status)"
            type="primary"
            :loading="actionLoading"
            @click="startProject"
          >
            {{ project.status === 'failed' ? '重新执行' : t('生成视频') }}
          </n-button>
          <n-button
            v-if="project.status === 'storyboard_ready' || project.shots.length > 0"
            @click="router.push(`/video/${project.id}/storyboard`)"
          >
            {{ t('View Storyboard') }}
          </n-button>
        </template>
      </AppPageHeader>

      <AppCard v-if="previewUrl">
        <h2 class="section-title">成片预览</h2>
        <div class="video-preview"><video :src="previewUrl" :poster="project.output_thumbnail_url" controls /></div>
      </AppCard>
      <AppCard v-if="project.quality_check_result?.note">{{ project.quality_check_result.note }}</AppCard>
      <AppCard v-if="['draft','pending_review'].includes(project.status)">
        <h2 class="section-title">自选背景音乐</h2>
        <MusicPicker :company-id="companyId" v-model:music-asset-id="musicAssetId" v-model:music-volume="musicVolume" />
        <n-button type="primary" :loading="musicLoading" :disabled="project.status==='pending_review' && !musicAssetId" @click="saveMusic">
          {{ project.status==='draft'?'保存配乐设置':'替换成片配乐（不重新生成视频）' }}
        </n-button>
      </AppCard>
      <AppCard v-if="project.status === 'failed'">重新执行会复用已成功的镜头，重新生成失败镜头，可能产生新的模型费用。提交结果不确定时会阻止重试并提示核对中转任务。</AppCard>
      <AppCard v-if="project.shots?.some(s=>s.purpose)">
        <h2 class="section-title">分镜与节奏 · {{ project.target_duration_seconds }}秒</h2>
        <p v-for="shot in project.shots" :key="shot.id">{{ shot.sequence_number }} · {{ shot.duration_seconds }}秒 · {{ shot.purpose }} · {{ shot.framing }} · {{ shot.camera_movement }}<br>{{ shot.visual_description }}<br><span v-if="shot.transition_out">转场：{{ shot.transition_out }} {{ shot.transition_duration_seconds || 0 }}秒 · {{ shot.transition_notes }}</span></p>
      </AppCard>
      <AppCard v-if="sourceAssets.length" class="source-assets"><h2 class="section-title">本片使用素材</h2><div v-for="asset in sourceAssets" :key="asset.id">{{ asset.name }} · {{ asset.category || '未分类' }} · {{ (asset.tags||[]).join('、') }}</div></AppCard>
      <AppCard v-if="project.publish_title" class="publish-copy">
        <h2 class="section-title">发布文案</h2>
        <h3 class="publish-copy__title">{{ project.publish_title }}</h3>
        <p class="publish-copy__description">{{ project.publish_description }}</p>
        <p v-if="project.publish_platforms?.length" class="publish-copy__targets">审核通过后自动发布至：{{ project.publish_platforms.map(p => p === 'douyin' ? '抖音' : '微信视频号').join('、') }}</p>
        <p v-else class="publish-copy__targets">尚未选择发布平台，审核后可在平台发布页选择。</p>
      </AppCard>
      <AppCard v-if="project.status === 'pending_review'" class="review-card">
        <div class="review-layout">
          <div class="review-copy">
            <h2 class="section-title">成片审核</h2>
            <p>{{ project.publish_platforms?.length ? '请确认成片与发布文案，审核通过后将自动提交至所选平台。' : '请确认成片内容，审核通过后可选择平台发布。' }}</p>
          </div>
          <n-button type="primary" size="large" class="review-button" :loading="approvalLoading" :disabled="approvalLoading" @click="approveVideo">{{ project.publish_platforms?.length ? '审核通过并自动发布' : '审核通过' }}</n-button>
        </div>
      </AppCard>
      <!-- Status pipeline -->
      <AppCard class="pipeline-card">
        <h2 class="section-title">{{ t('Production Pipeline') }}</h2>
        <div class="pipeline" role="list" :aria-label="t('Production stages')">
          <div
            v-for="(stage, i) in pipeline"
            :key="stage.key"
            class="pipeline__stage"
            :class="{
              'pipeline__stage--done': stageIndex > i,
              'pipeline__stage--active': stageIndex === i,
            }"
            role="listitem"
          >
            <div class="pipeline__dot" :aria-label="`${t(stage.label)}: ${t(stageIndex > i ? 'done' : stageIndex === i ? 'active' : 'pending')}`">
              <CheckmarkOutline v-if="stageIndex > i" aria-hidden="true" />
              <span v-else aria-hidden="true">{{ i + 1 }}</span>
            </div>
            <span class="pipeline__label">{{ t(stage.label) }}</span>
            <div v-if="i < pipeline.length - 1" class="pipeline__connector" aria-hidden="true" />
          </div>
        </div>
      </AppCard>

      <div class="detail-grid">
        <!-- Script / storyboard preview -->
        <AppCard>
          <h2 class="section-title">{{ t('Script') }}</h2>
          <template v-if="project.script">
            <pre class="script-preview">{{ project.script }}</pre>
          </template>
          <template v-else>
            <AppEmpty :icon="DocumentTextOutline" :title="t('No script yet')" :description="t('Start generation to produce a script.')" />
          </template>
        </AppCard>

        <!-- Side: metadata -->
        <div>
          <AppCard>
            <h2 class="section-title">{{ t('Details') }}</h2>
            <dl class="detail-list">
              <div class="detail-list__item">
                <dt>{{ t('Mode') }}</dt>
                <dd>{{ t(project.creation_mode.replace('_', ' ')) }}</dd>
              </div>
              <div class="detail-list__item">
                <dt>{{ t('Shots') }}</dt>
                <dd>{{ project.shots.length }}</dd>
              </div>
              <div v-if="project.estimated_duration_seconds" class="detail-list__item">
                <dt>{{ t('Est. Duration') }}</dt>
                <dd>{{ Math.round(project.estimated_duration_seconds) }}s</dd>
              </div>
              <div v-if="project.estimated_cost_usd != null" class="detail-list__item">
                <dt>{{ t('Est. Cost') }}</dt>
                <dd class="font-mono">${{ project.estimated_cost_usd.toFixed(4) }}</dd>
              </div>
            </dl>
          </AppCard>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { NButton } from 'naive-ui'
import { VideocamOutline, CheckmarkOutline, DocumentTextOutline } from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppEmpty from '@/components/common/AppEmpty.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { useAuthStore } from '@/stores/auth'
import { videoProjectsApi } from '@/api/videoProjects'
import { assetsApi } from '@/api/assets'
import type { VideoProject } from '@/types/videoProject'
import MusicPicker from '@/components/video/MusicPicker.vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const loading = ref(true)
const actionLoading = ref(false)
const approvalLoading = ref(false)
const musicLoading=ref(false),musicAssetId=ref<string|null>(null),musicVolume=ref(0.25)
const actionError = ref('')
const project = ref<VideoProject | null>(null)
const previewUrl = ref('')
let previewAssetId: string | undefined
const sourceAssets = ref<{id:string;name:string;category?:string;tags?:string[]}[]>([])
let pollTimer: ReturnType<typeof setTimeout> | undefined
let disposed = false
async function refreshProject() {
  try {
    const res = await videoProjectsApi.get(companyId.value, route.params.id as string)
    if (disposed) return
    project.value = res.data
    // Signed URLs change on every poll. Keep the loaded source for the same
    // asset so refreshing project status does not restart video playback.
    if (res.data.output_video_url && (!previewUrl.value || res.data.output_asset_id !== previewAssetId)) {
      previewUrl.value = res.data.output_video_url
      previewAssetId = res.data.output_asset_id
    }
    if (res.data.selected_asset_ids?.length && sourceAssets.value.length===0) {
      sourceAssets.value=(await Promise.all(res.data.selected_asset_ids.map(id=>assetsApi.get(companyId.value,id).then(r=>r.data).catch(()=>null)))).filter(Boolean) as typeof sourceAssets.value
    }
    if (res.data.output_asset_id && !previewUrl.value) {
      const media = await assetsApi.getDownloadUrl(companyId.value, res.data.output_asset_id)
      if (!disposed) {
        previewUrl.value = media.data.url
        previewAssetId = res.data.output_asset_id
      }
    }
  } finally {
    if (!disposed) pollTimer = setTimeout(() => { refreshProject().catch(() => {}) }, 5000)
  }
}
onUnmounted(() => { disposed = true; clearTimeout(pollTimer) })
async function approveVideo() {
  if (!project.value || approvalLoading.value) return
  approvalLoading.value = true
  actionError.value = ''
  try {
    await videoProjectsApi.approve(companyId.value, project.value.id)
    const res = await videoProjectsApi.get(companyId.value, project.value.id)
    project.value = res.data
  } catch(e: any) { actionError.value = e.response?.data?.detail || '审批失败，请重试'
  } finally { approvalLoading.value = false }
}

const pipeline = [
  { key: 'draft', label: 'Draft' },
  { key: 'analyzing', label: '准备生成' },
  { key: 'generating_shots', label: 'Generating' },
  { key: 'compositing', label: 'Compositing' },
  { key: 'pending_review', label: '待审核' },
  { key: 'completed', label: 'Complete' },
]

const stageIndex = computed(() => {
  if (!project.value) return 0
  const idx = pipeline.findIndex((s) => s.key === project.value!.status)
  return idx === -1 ? 0 : idx
})

onMounted(async () => {
  try {
    const res = await videoProjectsApi.get(companyId.value, route.params.id as string)
    project.value = res.data
    musicAssetId.value=res.data.music_asset_id||null
    musicVolume.value=res.data.music_volume??0.25
    await refreshProject()
  } finally {
    loading.value = false
  }
})

async function saveMusic() {
  if(!project.value || musicLoading.value)return
  musicLoading.value=true;actionError.value=''
  try {
    const res=await videoProjectsApi.updateMusic(companyId.value,project.value.id,
      {music_asset_id:musicAssetId.value,music_volume:musicVolume.value},project.value.status==='draft')
    project.value=res.data
    if(res.data.output_video_url){previewUrl.value=res.data.output_video_url;previewAssetId=res.data.output_asset_id}
  } catch(e:any){actionError.value=e.response?.data?.detail||'配乐保存失败，请重试'}
  finally {musicLoading.value=false}
}

async function startProject() {
  if (!project.value) return
  actionLoading.value = true
  actionError.value = ''
  try {
    const res = await (project.value.status === 'failed' ? videoProjectsApi.retry : videoProjectsApi.start)(companyId.value, project.value.id)
    project.value = res.data
  } catch(e: any) { actionError.value = e.response?.data?.detail || '启动失败，请检查模型配置'
  } finally {
    actionLoading.value = false
  }
}

async function startGeneration() {
  if (!project.value) return
  actionLoading.value = true
  try {
    const res = await videoProjectsApi.start(companyId.value, project.value.id)
    project.value = res.data
  } finally {
    actionLoading.value = false
  }
}
</script>

<style scoped>
.video-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  min-width: 0;
}

.video-detail :deep(.page-header) { margin-bottom: 0; }
.video-detail :deep(.page-header__left) { flex: 1 1 280px; min-width: 0; }
.video-detail :deep(.page-header__title) { overflow-wrap: anywhere; }
.video-detail :deep(.page-header__actions) { flex-wrap: wrap; max-width: 100%; }
.video-detail > *, .detail-grid > * { min-width: 0; }
.video-preview { display: flex; justify-content: center; background: #101827; border-radius: var(--radius-md); overflow: hidden; }
.video-preview video { display: block; max-width: 100%; max-height: 520px; }
.publish-copy__title { font-size: var(--text-base); font-weight: 600; overflow-wrap: anywhere; }
.publish-copy__description { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.8; margin-top: var(--space-3); }
.publish-copy__targets { color: var(--text-secondary); margin-top: var(--space-4); line-height: 1.6; }
.review-card { border-color: var(--color-brand-500); }
.review-layout { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: var(--space-5); }
.review-copy { flex: 1 1 280px; min-width: 0; }
.review-copy .section-title { margin-bottom: var(--space-2); }
.review-copy p { color: var(--text-secondary); line-height: 1.7; }
.review-button { min-height: 44px; font-weight: 600; flex-shrink: 0; }
.source-assets > div { line-height: 1.8; overflow-wrap: anywhere; }
.action-error { padding: var(--space-4); color: var(--color-danger); border: 1px solid currentColor; border-radius: var(--radius-md); }
@media (max-width: 600px) {
  .review-button { width: 100%; }
}

.section-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-4);
}

.pipeline {
  display: flex;
  align-items: center;
  gap: 0;
  overflow-x: auto;
  padding-bottom: var(--space-2);
}

.pipeline__stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  position: relative;
  flex: 1;
  min-width: 76px;
}

.pipeline__dot svg { width: 18px; height: 18px; flex-shrink: 0; }

.pipeline__dot {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-neutral-200);
  color: var(--text-muted);
  font-size: var(--text-sm);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  z-index: 1;
  transition: background var(--duration-normal), color var(--duration-normal);
}

.pipeline__stage--done .pipeline__dot {
  background: var(--color-success);
  color: white;
}

.pipeline__stage--active .pipeline__dot {
  background: var(--color-brand-500);
  color: white;
  box-shadow: 0 0 0 4px var(--color-brand-100);
}

.pipeline__label {
  font-size: var(--text-xs);
  color: var(--text-muted);
  white-space: nowrap;
}

.pipeline__stage--done .pipeline__label,
.pipeline__stage--active .pipeline__label {
  color: var(--text-primary);
  font-weight: 600;
}

.pipeline__connector {
  position: absolute;
  top: 16px;
  left: 50%;
  width: 100%;
  height: 2px;
  background: var(--border-default);
  z-index: 0;
}

.pipeline__stage--done .pipeline__connector {
  background: var(--color-success);
}

.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: var(--space-6);
}

@media (max-width: 900px) {
  .detail-grid { grid-template-columns: 1fr; }
}

.script-preview {
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  line-height: var(--leading-loose);
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.detail-list__item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.detail-list__item dt {
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.detail-list__item dd {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  text-transform: capitalize;
}
</style>
