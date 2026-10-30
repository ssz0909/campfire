<template>
  <section class="model-settings">
    <h1>大模型配置</h1>
    <p>保存后，后续调用使用新配置，无需重启。正在执行的调用继续使用原配置。</p>
    <div class="model-settings__grid">
      <section v-for="panel in panels" :key="panel.endpoint" class="model-settings__panel">
        <h2>{{ panel.title }}</h2>
        <p>{{ panel.description }}</p>
        <p v-if="panel.loaded">当前来源：{{ panel.source === 'database' ? '后台配置' : '.env 环境配置' }}</p>
        <n-form v-if="panel.loaded" label-placement="top" @submit.prevent="save(panel)">
          <n-form-item label="接口地址（Base URL）">
            <n-input v-model:value="panel.form.base_url" :placeholder="panel.placeholder" />
          </n-form-item>
          <p class="model-settings__hint">{{ panel.hint }}</p>
          <n-form-item label="模型名称">
            <n-input v-model:value="panel.form.model" placeholder="填写服务商提供的模型名称" />
          </n-form-item>
          <n-form-item label="API Key">
            <n-input v-model:value="panel.form.api_key" type="password" autocomplete="new-password"
              :placeholder="panel.keyConfigured ? '已配置，留空保留原值' : '请输入 API Key'" />
          </n-form-item>
          <n-button type="primary" :loading="panel.saving" @click="save(panel)">保存{{ panel.title }}</n-button>
        </n-form>
        <p v-if="panel.error" role="alert">{{ panel.error }}</p>
        <n-button v-if="!panel.loaded" :loading="panel.loading" @click="load(panel)">重新加载</n-button>
        <p v-if="panel.success" role="status">配置已保存，后续调用将使用新配置。</p>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { NButton, NForm, NFormItem, NInput } from 'naive-ui'
import apiClient from '@/api/client'
const panels = reactive([
  { endpoint: '/admin/model-settings', title: '文本与视觉模型',
    description: '用于数字员工任务规划、脚本生成和素材图片识别。',
    placeholder: 'https://api.openai.com/v1', hint: '填写兼容 OpenAI 的接口基础地址。' },
  { endpoint: '/admin/video-model-settings', title: '视频生成模型',
    description: '用于视频制作员的分镜视频生成，独立于文本模型配置。',
    placeholder: 'https://tokenspace.io/v1/video/generations',
    hint: '填写视频中转接口，支持完整 /video/generations 地址或 /v1 基础地址。' },
].map(panel => ({ ...panel, form: { base_url: '', model: '', api_key: '' },
  loaded: false, loading: false, saving: false, keyConfigured: false,
  source: 'env', error: '', success: false })))
type Panel = typeof panels[number]
function apply(panel: Panel, data: { base_url: string; model: string; api_key_configured: boolean; source: string }) {
  panel.form.base_url = data.base_url
  panel.form.model = data.model
  panel.form.api_key = ''
  panel.keyConfigured = data.api_key_configured
  panel.source = data.source
  panel.loaded = true
}
async function load(panel: Panel) {
  panel.loading = true
  panel.error = ''
  try { apply(panel, (await apiClient.get(panel.endpoint)).data) }
  catch { panel.error = '配置加载失败，请重试。' }
  finally { panel.loading = false }
}
async function save(panel: Panel) {
  panel.saving = true
  panel.error = ''
  panel.success = false
  try {
    apply(panel, (await apiClient.put(panel.endpoint, panel.form)).data)
    panel.success = true
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    panel.error = typeof detail === 'string' ? detail : '保存失败，请检查配置后重试。'
  } finally { panel.saving = false }
}
onMounted(() => { panels.forEach(panel => { void load(panel) }) })
</script>

<style scoped>
.model-settings { max-width: 1120px; }
.model-settings__grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 24px; margin-top: 24px; }
.model-settings__panel { min-width: 0; padding: 24px; border: 1px solid var(--border-color, #e5e7eb); border-radius: 12px; background: var(--surface-raised, #fff); }
.model-settings__panel h2 { margin-top: 0; font-size: 18px; }
.model-settings__panel p { color: var(--text-secondary); }
.model-settings__hint { margin-top: -12px; font-size: 12px; }
</style>
