<template>
  <div>
    <AppPageHeader :title="t('Video Projects')" :subtitle="t('AI-generated video campaigns and content')">
      <template #actions>
        <n-button type="primary" @click="router.push('/video/new')">
          <template #icon><AddOutline /></template>
          {{ t('New Video') }}
        </n-button>
      </template>
    </AppPageHeader>

    <!-- Status filter -->
    <div class="video-filters">
      <n-radio-group v-model:value="statusFilter" @update:value="loadProjects">
        <n-radio-button value="">{{ t('All') }}</n-radio-button>
        <n-radio-button value="draft">{{ t('Draft') }}</n-radio-button>
        <n-radio-button value="generating">{{ t('Generating') }}</n-radio-button>
        <n-radio-button value="completed">{{ t('Completed') }}</n-radio-button>
      </n-radio-group>
    </div>

    <template v-if="loading">
      <div class="video-grid">
        <AppCard v-for="i in 6" :key="i">
          <AppLoader variant="card" />
        </AppCard>
      </div>
    </template>

    <template v-else-if="projects.length === 0">
      <AppEmpty
        :icon="VideocamOutline"
        :title="t('No video projects')"
        :description="t('Create AI-generated videos for marketing and content')"
      >
        <template #action>
          <n-button type="primary" @click="router.push('/video/new')">
            {{ t('Create video project') }}
          </n-button>
        </template>
      </AppEmpty>
    </template>

    <template v-else>
      <div class="video-grid">
        <AppCard
          v-for="project in projects"
          :key="project.id"
          hoverable
          @click="router.push(`/video/${project.id}`)"
        >
          <div class="video-card">
            <div class="video-card__thumb">
              <img v-if="project.output_thumbnail_url" :src="project.output_thumbnail_url" class="video-card__thumb-image" :alt="project.title" />
              <VideocamOutline v-else class="video-card__thumb-icon" aria-hidden="true" />
              <StatusBadge :status="project.status" class="video-card__status" />
            </div>
            <div class="video-card__body">
              <h3 class="video-card__title">{{ project.title }}</h3>
              <p class="video-card__mode">{{ t(project.creation_mode.replace('_', ' ')) }}</p>
              <div class="video-card__meta">
                <span v-if="project.estimated_duration_seconds">
                  ~{{ Math.round(project.estimated_duration_seconds) }}s
                </span>
                <span v-if="project.estimated_cost_usd">
                  ${{ project.estimated_cost_usd.toFixed(2) }}
                </span>
                <span>{{ t('{count} shots', { count: project.shots.length }) }}</span>
              </div>
            </div>
          </div>
        </AppCard>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NButton, NRadioGroup, NRadioButton } from 'naive-ui'
import { AddOutline, VideocamOutline } from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppEmpty from '@/components/common/AppEmpty.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { useAuthStore } from '@/stores/auth'
import { videoProjectsApi } from '@/api/videoProjects'
import type { VideoProject } from '@/types/videoProject'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const loading = ref(true)
const projects = ref<VideoProject[]>([])
const statusFilter = ref('')

onMounted(() => loadProjects())

async function loadProjects() {
  loading.value = true
  try {
    const params = statusFilter.value ? { status: statusFilter.value } : {}
    const res = await videoProjectsApi.list(companyId.value, params)
    projects.value = Array.isArray(res.data) ? res.data : (res.data as { items: VideoProject[] }).items
  } catch {
    projects.value = []
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.video-filters {
  margin-bottom: var(--space-4);
}

.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
}

.video-card__thumb {
  background: var(--color-neutral-900);
  height: 140px;
  border-radius: var(--radius-md) var(--radius-md) 0 0;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  margin: calc(var(--space-6) * -1) calc(var(--space-6) * -1) var(--space-4);
  overflow: hidden;
}

.video-card__thumb-icon {
  font-size: 40px;
  color: var(--color-neutral-500);
}
.video-card__thumb-image { width:100%; height:100%; object-fit:cover; }

.video-card__status {
  position: absolute;
  top: var(--space-2);
  right: var(--space-2);
}

.video-card__title {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
}

.video-card__mode {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  text-transform: capitalize;
  margin-top: 2px;
}

.video-card__meta {
  display: flex;
  gap: var(--space-4);
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}
</style>
