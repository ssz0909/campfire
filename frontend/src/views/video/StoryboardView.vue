<template>
  <div>
    <template v-if="loading">
      <AppPageHeader :title="t('Storyboard')" :breadcrumbs="breadcrumbs" />
      <AppCard><AppLoader variant="table" :rows="5" /></AppCard>
    </template>

    <template v-else-if="!project">
      <AppPageHeader :title="t('Not found')" :breadcrumbs="[{ label: t('Video'), to: '/video' }]" />
      <AppEmpty :icon="VideocamOutline" :title="t('Project not found')" />
    </template>

    <template v-else>
      <AppPageHeader
        :title="t('Storyboard: {title}', { title: project.title })"
        :breadcrumbs="breadcrumbs"
        :subtitle="t('{count} shots', { count: project.shots.length })"
      >
        <template #actions>
          <n-button
            v-if="project.status === 'storyboard_ready'"
            type="primary"
            :loading="actionLoading"
            @click="startGeneration"
          >
            {{ t('Start Generation') }}
          </n-button>
          <n-button
            v-if="project.status === 'generating'"
            @click="composite"
            :loading="actionLoading"
          >
            {{ t('Composite') }}
          </n-button>
        </template>
      </AppPageHeader>

      <template v-if="project.shots.length === 0">
        <AppEmpty
          :icon="VideocamOutline"
          :title="t('No shots yet')"
          :description="t('Shots are generated from the project script.')"
        />
      </template>

      <div v-else class="shots-list">
        <AppCard
          v-for="shot in project.shots"
          :key="shot.id"
          class="shot-card"
        >
          <div class="shot-card__header">
            <span class="shot-card__seq">#{{ shot.sequence_number }}</span>
            <StatusBadge :status="shot.status" />
            <span class="shot-card__duration">{{ shot.duration_seconds }}s</span>
          </div>

          <div class="shot-card__body">
            <div class="shot-card__thumb">
              <img
                v-if="shot.thumbnail_url"
                :src="shot.thumbnail_url"
                :alt="t('Shot {number} thumbnail', { number: shot.sequence_number })"
                class="shot-card__img"
              />
              <VideocamOutline v-else class="shot-card__thumb-icon" aria-hidden="true" />
            </div>

            <div class="shot-card__content">
              <div>
                <p class="shot-card__label">{{ t('Visual Description') }}</p>
                <p class="shot-card__text">{{ shot.visual_description }}</p>
              </div>
              <p v-if="shot.purpose">{{ shot.purpose }} · {{ shot.framing }} · {{ shot.camera_movement }}</p>
              <div v-if="shot.voiceover_text">
                <p class="shot-card__label">{{ t('Voiceover') }}</p>
                <p class="shot-card__text shot-card__text--muted">{{ shot.voiceover_text }}</p>
              </div>
            </div>
          </div>

          <div class="shot-card__actions">
            <n-button
              size="small"
              :loading="regeneratingId === shot.id"
              :disabled="shot.status === 'generating'"
              @click="regenerateShot(shot.id)"
            >
              <template #icon><RefreshOutline /></template>
              {{ t('Regenerate') }}
            </n-button>
          </div>
        </AppCard>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { NButton } from 'naive-ui'
import { VideocamOutline, RefreshOutline } from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppEmpty from '@/components/common/AppEmpty.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { useAuthStore } from '@/stores/auth'
import { videoProjectsApi } from '@/api/videoProjects'
import type { VideoProject } from '@/types/videoProject'

const route = useRoute()
const { t } = useI18n()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const loading = ref(true)
const actionLoading = ref(false)
const regeneratingId = ref<string | null>(null)
const project = ref<VideoProject | null>(null)

const breadcrumbs = computed(() => [
  { label: t('Video'), to: '/video' },
  { label: project.value?.title ?? t('Project'), to: `/video/${route.params.id}` },
])

onMounted(async () => {
  try {
    const res = await videoProjectsApi.get(companyId.value, route.params.id as string)
    project.value = res.data
  } finally {
    loading.value = false
  }
})

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

async function composite() {
  if (!project.value) return
  actionLoading.value = true
  try {
    const res = await videoProjectsApi.approve(companyId.value, project.value.id)
    project.value = res.data
  } finally {
    actionLoading.value = false
  }
}

async function regenerateShot(shotId: string) {
  if (!project.value) return
  regeneratingId.value = shotId
  try {
    const res = await videoProjectsApi.regenerateShot(companyId.value, project.value.id, shotId)
    project.value = res.data
  } finally {
    regeneratingId.value = null
  }
}
</script>

<style scoped>
.shots-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.shot-card__header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.shot-card__seq {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  min-width: 32px;
}

.shot-card__duration {
  font-size: var(--text-sm);
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  margin-left: auto;
}

.shot-card__body {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

@media (max-width: 600px) {
  .shot-card__body {
    grid-template-columns: 1fr;
  }
}

.shot-card__thumb {
  background: var(--surface-sunken);
  border-radius: var(--radius-md);
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.shot-card__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.shot-card__thumb-icon {
  font-size: 32px;
  color: var(--text-muted);
}

.shot-card__content {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.shot-card__label {
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--space-1);
}

.shot-card__text {
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: var(--leading-normal);
}

.shot-card__text--muted {
  color: var(--text-secondary);
  font-style: italic;
}

.shot-card__actions {
  display: flex;
  justify-content: flex-end;
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-default);
}
</style>
