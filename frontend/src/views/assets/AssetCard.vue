<template>
  <AppCard hoverable class="asset-card">
    <div class="asset-card__thumb" :aria-label="t('{name} thumbnail', { name: asset.name })">
      <img
        v-if="asset.thumbnail_url || (asset.asset_type === 'image' && asset.file_url)"
        :src="asset.thumbnail_url || asset.file_url"
        :alt="asset.name"
        class="asset-card__img"
      />
      <component
        :is="typeIcon"
        v-else
        class="asset-card__icon"
        aria-hidden="true"
      />
      <StatusBadge
        v-if="asset.processing_status !== 'ready'"
        :status="asset.processing_status"
        class="asset-card__status"
      />
    </div>
    <div class="asset-card__body">
      <p class="asset-card__name" :title="asset.name">{{ asset.name }}</p>
      <div class="asset-card__meta">
        <AppBadge>{{ asset.asset_type }}</AppBadge>
        <span class="asset-card__size">{{ formatBytes(asset.file_size_bytes) }}</span>
      </div>
      <div v-if="asset.tags?.length" class="asset-card__tags">
        <AppBadge v-for="tag in asset.tags.slice(0, 3)" :key="tag">{{ tag }}</AppBadge>
      </div>
      <p v-if="asset.category" class="asset-card__description">{{ categoryName(asset.category) }} · {{ asset.source_description }}</p>
      <p v-if="['pending','running'].includes(asset.metadata?.vision_analysis?.status || '')" class="asset-card__description">图片内容识别中…</p>
      <p v-if="asset.metadata?.vision_analysis?.detail" class="asset-card__description">{{ asset.metadata.vision_analysis.detail }}</p>
      <p v-else-if="asset.metadata?.vision_analysis?.error" class="asset-card__description">{{ asset.metadata.vision_analysis.error }}</p>
    </div>
    <div class="asset-card__actions">
      <n-button size="tiny" quaternary @click.stop="emit('edit')">编辑标签</n-button>
      <n-button v-if="asset.asset_type === 'image'" size="tiny" quaternary @click.stop="emit('analyze')">重新识别</n-button>
      <n-button size="tiny" ghost @click.stop="emit('delete')">{{ t('Delete') }}</n-button>
    </div>
  </AppCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'
import {
  ImageOutline,
  VideocamOutline,
  DocumentOutline,
  MusicalNotesOutline,
  AttachOutline,
} from '@vicons/ionicons5'
import AppCard from '@/components/common/AppCard.vue'
import AppBadge from '@/components/common/AppBadge.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import type { Asset } from '@/types/asset'

import type { AssetType } from '@/types/asset'

const props = defineProps<{ asset: Asset }>()
const emit = defineEmits<{ delete: []; edit: []; analyze: [] }>()
const { t } = useI18n()

const typeIcon = computed(() => {
  const map: Record<AssetType, unknown> = {
    image: ImageOutline,
    video: VideocamOutline,
    document: DocumentOutline,
    audio: MusicalNotesOutline,
    other: AttachOutline,
  }
  return map[props.asset.asset_type as AssetType] ?? AttachOutline
})

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
function categoryName(value: string) { return ({exterior:'酒店外观',lobby:'大堂前台',guest_room:'客房',bathroom:'卫浴',restaurant:'餐厅',breakfast:'早餐',amenities:'配套设施',pool:'泳池',meeting_room:'会议空间',staff:'员工服务',landscape:'景观周边',other:'其他'} as Record<string,string>)[value] || value }
</script>

<style scoped>
.asset-card {
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.asset-card__thumb {
  background: var(--surface-sunken);
  height: 140px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.asset-card__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.asset-card__icon {
  font-size: 40px;
  color: var(--text-muted);
}

.asset-card__status {
  position: absolute;
  top: var(--space-2);
  right: var(--space-2);
}

.asset-card__body {
  padding: var(--space-3);
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.asset-card__name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-card__meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.asset-card__size {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.asset-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.asset-card__actions {
  padding: var(--space-2) var(--space-3);
  border-top: 1px solid var(--border-default);
  display: flex;
  justify-content: flex-end;
}
</style>
