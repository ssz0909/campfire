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
          <h3 class="mode-card__title">{{ t('酒店图片素材短片') }}</h3>
          <p class="mode-card__desc">
            {{ t('选择 1 张图片作为模型首帧；选择 2 至 5 张时，本机自动合成为多图竖屏短片。') }}
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

          <template v-if="form.creation_mode === 'ai_creative'">
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
            <n-form-item label="选择视频素材（最多 5 张图片）" path="selected_asset_ids">
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
        </n-form>
        <p class="create-hint">最多选择 5 张，每张图片调用视频模型生成至少 5 秒动态镜头，再统一画幅合成。例如 3 张图片约生成 15 秒视频，按镜头分别计费。横竖图会适配为项目比例并保留主体。请确认素材授权与排列顺序。</p>

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

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const step = ref(1)
const creating = ref(false)
const errorMsg = ref('')
const formRef = ref<FormInst | null>(null)
const videoAssets = ref<{ id: string; name: string; tags:string[]; category?:string }[]>([])

const form = reactive({
  creation_mode: null as CreationMode | null,
  title: '',
  script: '',
  reference_asset_id: null as string | null,
  selected_asset_ids: [] as string[],
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
  if(form.selected_asset_ids.length>5){errorMsg.value='最多选择 5 张图片素材';return}
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  creating.value = true
  try {
    const res = await videoProjectsApi.create(companyId.value, {
      title: form.title,
      creation_mode: form.creation_mode!,
      script: form.script || undefined,
      reference_asset_id: form.reference_asset_id ?? undefined,
      selected_asset_ids: form.selected_asset_ids,
      aspect_ratio: '9:16',
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
