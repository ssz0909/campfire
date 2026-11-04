<template>
  <div>
    <AppPageHeader
      :title="t('New Video Project')"
      :breadcrumbs="[{ label: t('Video'), to: '/video' }]"
      :subtitle="t('Choose how you want to create your video')"
    />

    <!-- Step 1: mode selection -->
    <template v-if="step === 1">
      <div class="mode-grid">
        <button
          class="mode-card"
          :class="{ 'mode-card--selected': form.creation_mode === 'ai_creative' }"
          @click="selectMode('ai_creative')"
        >
          <BulbOutline class="mode-card__icon" aria-hidden="true" />
          <h3 class="mode-card__title">{{ t('AI Creative') }}</h3>
          <p class="mode-card__desc">
            {{ t('输入视频描述或脚本，由配置的视频模型生成整片。') }}
          </p>
          <AppBadge color="brand">{{ t('Recommended') }}</AppBadge>
        </button>

        <button
          class="mode-card"
          :class="{ 'mode-card--selected': form.creation_mode === 'reference_inspired' }"
          @click="selectMode('reference_inspired')"
        >
          <DocumentOutline class="mode-card__icon" aria-hidden="true" />
          <h3 class="mode-card__title">{{ t('素材生成短片') }}</h3>
          <p class="mode-card__desc">
            {{ t('选择多张图片素材，围绕任务主题按分镜制作15至60秒视频。') }}
          </p>
        </button>
      </div>

      <div class="step-actions">
        <n-button @click="router.push('/video')">{{ t('Cancel') }}</n-button>
        <n-button
          type="primary"
          :disabled="!form.creation_mode"
          @click="step = 2"
        >
          {{ t('Continue') }}
        </n-button>
      </div>
    </template>

    <!-- Step 2: form -->
    <template v-else-if="step === 2">
      <AppCard>
        <n-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-placement="top"
        >
          <n-form-item :label="t('Project Title')" path="title">
            <n-input v-model:value="form.title" :placeholder="t('e.g. Summer Sale Campaign')" />
          </n-form-item>

          <n-form-item label="成片时长（15至60秒）">
            <n-select v-model:value="form.target_duration_seconds" :options="[15,20,30,45,60].map(value=>({label:value+'秒',value}))" />
          </n-form-item>
          <n-form-item label="行业创作模板"><IndustryTemplatePicker v-model="industryOverride" /></n-form-item>
          <n-form-item label="视频生成策略">
            <n-select v-model:value="form.generation_mode" :options="[{label:'质量优先（现有逐镜生成）',value:'quality'},{label:'成本优先（5秒一段，段内1–2镜）',value:'cost'}]" />
          </n-form-item>
          <n-form-item label="分镜素材使用策略">
            <n-select v-model:value="form.reuse_policy" :options="[{label:'优先复用已审核分镜，不足时生成',value:'prefer_reuse'},{label:'全部重新生成',value:'fresh'},{label:'仅使用已有分镜，不调用视频模型',value:'reuse_only'}]" />
          </n-form-item>
          <p v-if="form.generation_mode === 'cost'" class="create-hint">预计 {{ Math.ceil(form.target_duration_seconds / 5) }} 次调用，每次生成5秒，成片 {{ form.target_duration_seconds }} 秒。当前接口使用单张首帧，每段设计同一场景的1–2个景别；内部切镜由模型执行，需审核效果。至少选择 {{ Math.ceil(form.target_duration_seconds / 5) }} 张不同图片。</p>
          <template v-if="form.creation_mode === 'ai_creative'">
            <n-form-item v-if="form.generation_mode === 'cost'" label="成本优先参考图片">
              <n-select v-model:value="form.selected_asset_ids" :options="videoAssetOptions" multiple filterable clearable />
            </n-form-item>
            <n-form-item :label="t('Script / Description')" path="script">
              <n-input
                v-model:value="form.script"
                type="textarea"
                :placeholder="t('Describe the video you want to create. Include topic, tone, key messages, target audience, and desired length.')"
                :autosize="{ minRows: 5, maxRows: 12 }"
              />
            </n-form-item>
          </template>

          <template v-else>
            <n-form-item label="候选视频素材（最多40张图片）" path="selected_asset_ids">
              <n-select
                v-model:value="form.selected_asset_ids"
                :placeholder="t('选择图片素材')"
                :options="videoAssetOptions"
                multiple
                filterable
                :max-tag-count="3"
                clearable
              />
            </n-form-item>
            <n-form-item :label="t('Additional Instructions (optional)')">
              <n-input
                v-model:value="form.script"
                type="textarea"
                :placeholder="t('Any additional guidance for style adaptation')"
                :autosize="{ minRows: 3, maxRows: 6 }"
              />
            </n-form-item>
          </template>
          <n-form-item label="背景音乐（可选）">
            <MusicPicker :company-id="companyId" v-model:music-asset-id="form.music_asset_id" v-model:music-volume="form.music_volume" />
          </n-form-item>
        </n-form>
        <p v-if="form.generation_mode === 'quality'" class="create-hint">每个成片镜头约1.5至3.5秒，开头不超过2秒。建议提供多个不同场景的清晰图片；模型片段生成后按分镜剪取，按生成镜头分别计费。每张图片只使用一次，素材不足时请补充。</p>

        <p v-if="errorMsg" class="create-error" role="alert">{{ errorMsg }}</p>
      </AppCard>

      <div class="step-actions">
        <n-button @click="step = 1">{{ t('Back') }}</n-button>
        <n-button type="primary" :loading="creating" @click="handleCreate">
          {{ t('Create Project') }}
        </n-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NButton, NForm, NFormItem, NInput, NSelect, type FormInst, type FormRules } from 'naive-ui'
import { BulbOutline, DocumentOutline } from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppBadge from '@/components/common/AppBadge.vue'
import { useAuthStore } from '@/stores/auth'
import { videoProjectsApi } from '@/api/videoProjects'
import { assetsApi } from '@/api/assets'
import type { CreationMode } from '@/types/videoProject'
import MusicPicker from '@/components/video/MusicPicker.vue'
import IndustryTemplatePicker from '@/components/video/IndustryTemplatePicker.vue'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const step = ref(1)
const industryOverride = ref<string|null>(null)
const creating = ref(false)
const errorMsg = ref('')
const formRef = ref<FormInst | null>(null)
const videoAssets = ref<{ id: string; name: string; tags:string[]; category?:string }[]>([])

const form = reactive({
  creation_mode: null as CreationMode | null,
  generation_mode: 'quality' as 'quality' | 'cost',
  reuse_policy: 'prefer_reuse' as 'fresh' | 'prefer_reuse' | 'reuse_only',
  title: '',
  script: '',
  reference_asset_id: null as string | null,
  selected_asset_ids: [] as string[],
  target_duration_seconds: 30,
  music_asset_id: null as string|null,
  music_volume: 0.25,
})

const rules: FormRules = {
   title: [{ required: true, message: t('Title is required'), trigger: 'blur' }],
   script: [{ required: form.creation_mode === 'ai_creative', message: t('Script is required'), trigger: 'blur' }],
}

const videoAssetOptions = computed(() =>
  videoAssets.value.map((a) => ({ label: a.name, value: a.id })),
)

onMounted(async () => {
  try {
    const res = await assetsApi.list(companyId.value, { type: 'image', limit: 100 })
    videoAssets.value = res.data.filter(a=>a.processing_status==='ready').map((a) => ({ id: a.id, name: `${a.name}${a.tags?.length ? ` · ${a.tags.slice(0,3).join('、')}`:''}`, tags:a.tags||[],category:a.category }))
  } catch {
    videoAssets.value = []
  }
})

function selectMode(mode: CreationMode) {
  form.creation_mode = mode
}

async function handleCreate() {
  errorMsg.value = ''
  if(form.selected_asset_ids.length>40){errorMsg.value='最多选择40张候选图片素材';return}
  if(form.generation_mode === 'cost' && form.selected_asset_ids.length < Math.ceil(form.target_duration_seconds / 5)){errorMsg.value='成本优先需要至少'+Math.ceil(form.target_duration_seconds / 5)+'张不同参考图片';return}
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  creating.value = true
  try {
    const res = await videoProjectsApi.create(companyId.value, {
      title: form.title,
      industry_override: industryOverride.value,
      creation_mode: form.creation_mode!,
      generation_mode: form.generation_mode,
      reuse_policy: form.reuse_policy,
      script: form.script || undefined,
      reference_asset_id: form.reference_asset_id ?? undefined,
      selected_asset_ids: form.selected_asset_ids,
      aspect_ratio: '9:16',
      target_duration_seconds: form.target_duration_seconds,
      music_asset_id: form.music_asset_id,
      music_volume: form.music_volume,
    })
    router.push(`/video/${res.data.id}`)
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    errorMsg.value = e?.response?.data?.detail ?? t('Failed to create project')
  } finally {
    creating.value = false
  }
}
</script>

<style scoped>
.mode-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.mode-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-6);
  background: var(--surface-card);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-lg);
  text-align: left;
  cursor: pointer;
  transition:
    border-color var(--duration-fast),
    box-shadow var(--duration-fast);
}

.mode-card:hover {
  border-color: var(--color-brand-300);
  box-shadow: var(--shadow-md);
}

.mode-card--selected {
  border-color: var(--color-brand-500);
  background: var(--color-brand-50);
}

.mode-card__icon {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  display: block;
  font-size: 32px;
  color: var(--color-brand-500);
}

.mode-card__title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.mode-card__desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
}

.step-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-6);
}

.create-error {
  font-size: var(--text-sm);
  color: var(--color-danger);
  background: oklch(93% 0.08 25);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  margin-top: var(--space-3);
}
</style>
