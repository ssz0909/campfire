<template>
  <div>
    <AppPageHeader :title="t('Assets')" :subtitle="t('Manage your media files and documents')">
      <template #actions>
        <n-button-group>
          <n-button :type="viewMode === 'grid' ? 'primary' : 'default'" @click="viewMode = 'grid'" :aria-label="t('Grid view')">
            <template #icon><GridOutline /></template>
          </n-button>
          <n-button :type="viewMode === 'list' ? 'primary' : 'default'" @click="viewMode = 'list'" :aria-label="t('List view')">
            <template #icon><ListOutline /></template>
          </n-button>
        </n-button-group>
      </template>
    </AppPageHeader>

    <!-- Upload zone -->
    <UploadZone
      accept="image/*,video/*,.pdf,.doc,.docx"
      multiple
      :title="t('Click or drag files to upload')"
      :hint="t('Supports images, videos, PDFs, and documents')"
      @files="handleUpload"
    />
    <p class="vision-hint">上传图片后会用 .env 配置的视觉大模型识别画面、类别和主题标签，可能产生模型用量；未配置视觉能力时可手动补标签或重试。</p>

    <!-- Upload progress -->
    <div v-if="uploads.length" class="upload-progress" role="status" :aria-label="t('Upload progress')">
      <div v-for="u in uploads" :key="u.name" class="upload-item">
        <span class="upload-item__name">{{ u.name }}</span>
        <n-progress
          type="line"
          :percentage="u.progress"
          :status="u.error ? 'error' : u.progress === 100 ? 'success' : 'default'"
          class="upload-item__progress"
        />
      </div>
    </div>

    <!-- Filters -->
    <div class="asset-filters">
      <n-input v-model:value="search" clearable placeholder="按主题、标签、描述筛选" @update:value="loadAssets" />
      <n-select v-model:value="categoryFilter" clearable placeholder="全部类别" :options="categoryOptions" @update:value="loadAssets" />
      <n-radio-group v-model:value="typeFilter" @update:value="loadAssets">
        <n-radio-button value="">{{ t('All') }}</n-radio-button>
        <n-radio-button value="image">{{ t('Images') }}</n-radio-button>
        <n-radio-button value="video">{{ t('Videos') }}</n-radio-button>
        <n-radio-button value="document">{{ t('Documents') }}</n-radio-button>
      </n-radio-group>
    </div>

    <template v-if="loading">
      <div class="assets-grid">
        <AppCard v-for="i in 8" :key="i">
          <AppLoader variant="card" />
        </AppCard>
      </div>
    </template>

    <template v-else-if="assets.length === 0">
      <AppEmpty
        :icon="ImagesOutline"
        :title="t('No assets found')"
        :description="t('Upload files to use them in tasks and video projects')"
      />
    </template>

    <template v-else>
      <div v-if="viewMode === 'grid'" class="assets-grid">
        <AssetCard
          v-for="asset in assets"
          :key="asset.id"
          :asset="asset"
          @delete="handleDelete(asset)"
          @edit="editAsset(asset)"
          @analyze="analyzeAsset(asset)"
        />
      </div>
      <AppCard v-else style="margin-top: var(--space-4)">
        <n-data-table :columns="listColumns" :data="assets" :bordered="false" />
      </AppCard>
    </template>

    <n-modal v-model:show="showEdit" preset="card" title="修正素材信息" style="width:min(560px, calc(100vw - 32px))">
      <n-form v-if="editingAsset" label-placement="top">
        <n-form-item label="类别"><n-select v-model:value="editCategory" filterable tag :options="categoryOptions" /></n-form-item>
        <n-form-item label="标签（逗号分隔）"><n-input v-model:value="editTags" placeholder="客房,落地窗,城市景观" /></n-form-item>
        <n-form-item label="画面描述"><n-input v-model:value="editDescription" type="textarea" :autosize="{minRows:2,maxRows:5}" /></n-form-item>
      </n-form>
      <template #footer><n-button @click="showEdit=false">取消</n-button><n-button type="primary" :loading="editBusy" @click="saveAsset">保存</n-button></template>
    </n-modal>

    <ConfirmDialog
      v-model:show="showDeleteDialog"
      :title="t('Delete asset')"
      :message="t('Delete {name}? This cannot be undone.', { name: assetToDelete?.name })"
      type="error"
      :confirm-text="t('Delete')"
      :loading="deleteLoading"
      @confirm="confirmDelete"
      @cancel="showDeleteDialog = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NButtonGroup, NProgress, NRadioGroup, NRadioButton, NDataTable, NInput, NSelect, NModal, NForm, NFormItem, useMessage, type DataTableColumns } from 'naive-ui'
import { GridOutline, ListOutline, ImagesOutline } from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppEmpty from '@/components/common/AppEmpty.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import UploadZone from '@/components/common/UploadZone.vue'
import AssetCard from './AssetCard.vue'
import { useAuthStore } from '@/stores/auth'
import { assetsApi } from '@/api/assets'
import type { Asset } from '@/types/asset'

const { t } = useI18n()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const loading = ref(true)
const assets = ref<Asset[]>([])
const viewMode = ref<'grid' | 'list'>('grid')
const typeFilter = ref('')
  const uploads = ref<Array<{ name: string; progress: number; error: boolean }>>([])
const search=ref(''),categoryFilter=ref<string|null>(null),showEdit=ref(false),editBusy=ref(false),editingAsset=ref<Asset|null>(null),editCategory=ref<string|null>(null),editTags=ref(''),editDescription=ref('')
const message=useMessage()
const categoryOptions=[{label:'酒店外观',value:'exterior'},{label:'大堂前台',value:'lobby'},{label:'客房',value:'guest_room'},{label:'卫浴',value:'bathroom'},{label:'餐厅',value:'restaurant'},{label:'早餐',value:'breakfast'},{label:'配套设施',value:'amenities'},{label:'泳池',value:'pool'},{label:'会议空间',value:'meeting_room'},{label:'员工服务',value:'staff'},{label:'景观周边',value:'landscape'},{label:'其他',value:'other'}]

const showDeleteDialog = ref(false)
const deleteLoading = ref(false)
const assetToDelete = ref<Asset | null>(null)

const listColumns = computed<DataTableColumns<Asset>>(() => [
  { title: t('Name'), key: 'name', ellipsis: true },
  {
    title: t('Type'),
    key: 'asset_type',
    render: (row) => row.asset_type,
  },
  {
    title: t('Size'),
    key: 'file_size_bytes',
    render: (row) => formatBytes(row.file_size_bytes),
  },
  {
    title: t('Status'),
    key: 'processing_status',
    render: (row) => h(StatusBadge, { status: row.processing_status }),
  },
  {
    title: t('Uploaded'),
    key: 'created_at',
    render: (row) => new Date(row.created_at).toLocaleDateString(),
  },
])

let visionTimer:ReturnType<typeof setInterval>|undefined
onMounted(() => { loadAssets(); visionTimer=setInterval(()=>{if(assets.value.some(a=>['pending','running'].includes(a.metadata?.vision_analysis?.status||'')))loadAssets()},3000) })
onUnmounted(()=>{if(visionTimer)clearInterval(visionTimer)})

async function loadAssets() {
  loading.value = true
  try {
    const params = { ...(typeFilter.value ? { type: typeFilter.value } : {}), ...(categoryFilter.value ? {category:categoryFilter.value}:{}), ...(search.value.trim()?{q:search.value.trim()}:{}) }
    const res = await assetsApi.list(companyId.value, params)
    assets.value = res.data
  } catch {
    assets.value = []
  } finally {
    loading.value = false
  }
}
function editAsset(asset:Asset){editingAsset.value=asset;editCategory.value=asset.category||null;editTags.value=(asset.tags||[]).join(',');editDescription.value=asset.source_description||asset.metadata?.vision_analysis?.visual_description||'';showEdit.value=true}
async function saveAsset(){if(!editingAsset.value)return;editBusy.value=true;try{const result=await assetsApi.update(companyId.value,editingAsset.value.id,{category:editCategory.value||undefined,tags:editTags.value.split(/[,，]/).map(x=>x.trim()).filter(Boolean),source_description:editDescription.value});Object.assign(editingAsset.value,result.data);showEdit.value=false;message.success('素材信息已保存')}catch{message.error('保存素材信息失败')}finally{editBusy.value=false}}
async function analyzeAsset(asset:Asset){try{const result=await assetsApi.analyze(companyId.value,asset.id);Object.assign(asset,result.data);message.success('图片识别完成')}catch(e:any){message.error(e.response?.data?.detail||'图片识别失败，请检查视觉模型配置')}}

async function handleUpload(files: File[]) {
  for (const file of files) {
    const upload = { name: file.name, progress: 0, error: false }
    uploads.value.push(upload)
    try {
      await assetsApi.upload(companyId.value, {
        file,
        onProgress: (p) => { upload.progress = p },
      })
      upload.progress = 100
    } catch {
      upload.error = true
    }  }
  await loadAssets()
  setTimeout(() => { uploads.value = [] }, 2000)
}

function handleDelete(asset: Asset) {
  assetToDelete.value = asset
  showDeleteDialog.value = true
}

async function confirmDelete() {
  if (!assetToDelete.value) return
  deleteLoading.value = true
  try {
    await assetsApi.delete(companyId.value, assetToDelete.value.id)
    assets.value = assets.value.filter((a) => a.id !== assetToDelete.value!.id)
    showDeleteDialog.value = false
  } finally {
    deleteLoading.value = false
    assetToDelete.value = null
  }
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<style scoped>
.asset-filters {
  margin: var(--space-4) 0;
}
.asset-filters { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
.asset-filters > :first-child { min-width:min(280px,100%); flex:1; }
.asset-filters > :nth-child(2) { width:220px; }
.vision-hint { color:var(--text-secondary); font-size:13px; margin-top:12px; }

.assets-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--space-4);
  margin-top: var(--space-4);
}

.upload-progress {
  margin: var(--space-4) 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.upload-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: var(--surface-sunken);
  border-radius: var(--radius-md);
}

.upload-item__name {
  font-size: var(--text-sm);
  color: var(--text-primary);
  flex-shrink: 0;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-item__progress {
  flex: 1;
}
</style>
