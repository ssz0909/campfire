<template>
  <div>
    <AppPageHeader :title="t('Settings')" :subtitle="t('Manage your workspace configuration')" />

    <n-tabs v-model:value="activeTab" type="line">
      <!-- Company Info -->
      <n-tab-pane name="company" :tab="t('Company Info')">
        <AppCard>
          <n-form
            ref="companyFormRef"
            :model="companyForm"
            :rules="companyRules"
            label-placement="top"
          >
            <n-form-item :label="t('Company Name')" path="name">
              <n-input v-model:value="companyForm.name" />
            </n-form-item>
            <n-form-item :label="t('Industry')" path="industry">
              <n-select
                v-model:value="companyForm.industry"
                :options="industryOptions"
                clearable
              />
            </n-form-item>
            <p v-if="industryError" role="alert">{{ industryError }}</p>
            <p class="industry-note">新任务默认使用所选行业的已发布模板；清空行业使用通用模板。已有任务与定时计划不受修改影响。</p>
            <n-form-item :label="t('Website')" path="website">
              <n-input v-model:value="companyForm.website" placeholder="https://..." />
            </n-form-item>
            <n-form-item :label="t('Description')" path="description">
              <n-input
                v-model:value="companyForm.description"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 6 }"
              />
            </n-form-item>
            <n-button type="primary" :loading="savingCompany" @click="saveCompany">
              {{ t('Save Company Info') }}
            </n-button>
          </n-form>
          <p v-if="companySaveMsg" class="save-msg" :class="{ 'save-msg--error': companySaveError }" role="status">
            {{ companySaveMsg }}
          </p>
        </AppCard>
      </n-tab-pane>

      <n-tab-pane name="publish-location" tab="发布定位">
        <AppCard>
          <p class="tab-desc">仅作用于当前企业工作区，其他企业独立配置。地点名称用于选择平台位置标签，坐标用于云端浏览器定位；平台仍可能参考服务器 IP。</p>
          <n-form label-placement="top">
            <n-form-item label="平台地点全名"><n-input v-model:value="publishLocation.location_name" maxlength="100" placeholder="填写酒店在平台上的完整地点名称" /></n-form-item>
            <n-form-item label="地图链接（可选）"><n-input v-model:value="publishLocation.map_url" @update:value="publishLocation.map_center_confirmed = false" placeholder="含坐标的百度/高德地图链接，短链接请改填经纬度" /></n-form-item>
            <n-form-item v-if="baiduCenterLink" label="百度地图中心确认">
              <n-checkbox v-model:checked="publishLocation.map_center_confirmed">我已打开链接，确认地图中心对准酒店位置</n-checkbox>
            </n-form-item>
            <p v-if="baiduCenterLink" class="tab-desc">此类百度链接的 /@ 数值代表地图中心，不是已核实的酒店坐标。确认后系统将投影坐标转换为浏览器经纬度；若中心偏离酒店，请清空链接并手动填坐标。</p>
            <n-form-item label="坐标来源"><n-select v-model:value="publishLocation.coordinate_system" :options="coordinateOptions" /></n-form-item>
            <n-form-item label="经度"><n-input v-model:value="longitudeText" placeholder="例如 119.xxxxxx" /></n-form-item>
            <n-form-item label="纬度"><n-input v-model:value="latitudeText" placeholder="例如 30.xxxxxx" /></n-form-item>
            <p class="tab-desc">链接含坐标时优先使用链接；手动填写时请选对坐标来源，系统会转换为浏览器使用的 WGS84。清空链接和经纬度可关闭浏览器定位，保留地点标签。</p>
            <n-button type="primary" :loading="savingLocation" @click="savePublishLocation">保存发布定位</n-button>
          </n-form>
          <p v-if="locationMessage" role="status" class="save-msg">{{ locationMessage }}</p>
        </AppCard>
      </n-tab-pane>
      <n-tab-pane name="video-music" tab="默认视频配乐">
        <AppCard>
          <p class="tab-desc">数字员工后续创建的视频自动配乐，合成后审核、发布，无需逐条替换。已创建的视频保留原设置。选择“不使用配乐（静音）”后，新视频不使用素材库音乐，并移除模型自带音轨。</p>
          <n-form-item label="配乐方式"><n-select v-model:value="defaultMusicMode" :options="[{label:'固定一首音乐',value:'fixed'},{label:'从素材库随机选取',value:'random'},{label:'不使用配乐（静音）',value:'none'}]" /></n-form-item>
          <MusicPicker v-if="auth.currentCompanyId && defaultMusicMode==='fixed'" :company-id="auth.currentCompanyId" v-model:music-asset-id="defaultMusicId" v-model:music-volume="defaultMusicVolume" />
          <template v-if="defaultMusicMode==='random'">
            <p class="tab-desc">每条新视频从本企业已处理完成的音频中随机选择一首；选定后重试不会换曲。请先在素材库上传音乐，无可用音频时会提示补充。</p>
            <n-form-item :label="'音乐音量 '+Math.round(defaultMusicVolume*100)+'%'"><n-slider :value="Math.round(defaultMusicVolume*100)" :min="0" :max="100" @update:value="defaultMusicVolume=$event/100" /></n-form-item>
          </template>
          <n-button type="primary" :loading="savingDefaultMusic" @click="saveDefaultMusic">保存默认视频配乐</n-button>
          <p v-if="defaultMusicMessage" role="status" class="save-msg">{{ defaultMusicMessage }}</p>
        </AppCard>
      </n-tab-pane>
      <n-tab-pane name="video-branding" tab="视频品牌片头">
        <AppCard>
          <p class="tab-desc">为本企业制作的视频自动叠加开场品牌字标。名称由合成程序准确绘制，无需模型生成文字；不增加成片时长，也不改动配乐。保存后在下一次成片合成时生效，已完成的视频保持原样。</p>
          <n-form label-placement="top">
            <n-form-item label="启用品牌片头"><n-checkbox v-model:checked="videoBranding.enabled">自动在视频开头展示品牌名称</n-checkbox></n-form-item>
            <n-form-item label="品牌名称"><n-input v-model:value="videoBranding.text" maxlength="32" show-count placeholder="例如：安吉雲中溪" /></n-form-item>
            <n-form-item :label="`展示时长 ${videoBranding.duration_seconds} 秒`"><n-slider v-model:value="videoBranding.duration_seconds" :min="1" :max="8" :step="1" /></n-form-item>
            <div class="brand-controls">
              <n-form-item label="字体"><n-select v-model:value="videoBranding.font" aria-label="品牌字体" :options="brandFonts" :loading="loadingBrandFonts" /></n-form-item>
              <n-form-item label="位置"><n-select v-model:value="videoBranding.position" aria-label="品牌位置" :options="brandPositions" /></n-form-item>
              <n-form-item :label="`字号：画面宽度的 ${videoBranding.font_size_percent}%`"><n-slider v-model:value="videoBranding.font_size_percent" aria-label="品牌字号" :min="2" :max="15" :step="0.1" /></n-form-item>
              <n-form-item :label="`左右边距 ${videoBranding.margin_x_percent}%`"><n-slider v-model:value="videoBranding.margin_x_percent" aria-label="品牌左右边距" :min="0" :max="30" :step="1" /></n-form-item>
              <n-form-item :label="`上下边距 ${videoBranding.margin_y_percent}%`"><n-slider v-model:value="videoBranding.margin_y_percent" aria-label="品牌上下边距" :min="0" :max="30" :step="1" /></n-form-item>
            </div>
            <p class="tab-desc">边距按画面尺寸计算，包含文字底框。居中方向保持居中；字号会按横竖画幅适配，长名称自动缩小以避免越界。</p>
            <template v-if="videoBranding.enabled && videoBranding.text.trim()">
              <n-form-item label="预览画幅"><n-select v-model:value="brandAspect" aria-label="预览画幅" :options="[{label:'竖屏 9:16',value:'9:16'},{label:'横屏 16:9',value:'16:9'},{label:'方形 1:1',value:'1:1'}]" /></n-form-item>
              <div class="brand-preview" :style="{aspectRatio: brandAspect.replace(':', '/')}" aria-label="品牌片头样式示意" :aria-busy="loadingBrandPreview">
                <img v-if="brandPreview" :src="brandPreview" alt="服务器真实字体和排版预览" />
              </div>
              <p role="status" class="tab-desc">{{ brandPreviewError || (loadingBrandPreview ? '正在更新预览…' : '使用服务器实际字体绘制；背景仅作示意，成片保留原画面。') }}</p>
            </template>
            <n-button type="primary" :loading="savingBranding" @click="saveVideoBranding">保存视频品牌片头</n-button>
          </n-form>
          <p v-if="brandingMessage" role="status" class="save-msg">{{ brandingMessage }}</p>
        </AppCard>
      </n-tab-pane>
      <!-- Brand Profile -->
      <n-tab-pane name="brand" :tab="t('Brand Profile')">
        <AppCard>
          <p class="tab-desc">{{ t('Configure your brand identity used by AI content creators.') }}</p>
          <n-form label-placement="top">
            <n-form-item :label="t('Brand Voice')">
              <n-select
                v-model:value="brand.voice"
                :options="voiceOptions"
                clearable
              />
            </n-form-item>
            <n-form-item :label="t('Brand Colors (comma separated hex values)')">
              <n-input
                v-model:value="brand.colors"
                placeholder="#1a1a2e, #16213e"
              />
            </n-form-item>
            <n-form-item :label="t('Target Audience')">
              <n-input
                v-model:value="brand.targetAudience"
                type="textarea"
                :placeholder="t('Describe your primary customer segment')"
                :autosize="{ minRows: 2, maxRows: 4 }"
              />
            </n-form-item>
            <n-form-item :label="t('Core Values / Keywords')">
              <n-input
                v-model:value="brand.keywords"
                :placeholder="t('innovation, trust, simplicity')"
              />
            </n-form-item>
            <n-button type="primary" @click="saveBrand">{{ t('Save Brand Profile') }}</n-button>
          </n-form>
        </AppCard>
      </n-tab-pane>

      <!-- Products -->
      <n-tab-pane name="products" :tab="t('Products')">
        <AppCard>
          <div class="section-header">
            <h3 class="section-title">{{ t('Products') }}</h3>
            <n-button type="primary" size="small">{{ t('Add Product') }}</n-button>
          </div>
          <template v-if="productsLoading">
            <AppLoader variant="table" :rows="4" />
          </template>
          <template v-else-if="products.length === 0">
            <AppEmpty
              :icon="CubeOutline"
              :title="t('No products configured')"
              :description="t('Add products to use them in task and content generation')"
            />
          </template>
          <template v-else>
            <n-data-table :columns="productColumns" :data="products" :bordered="false" size="small" />
          </template>
        </AppCard>
      </n-tab-pane>

      <!-- Subscription -->
      <n-tab-pane name="subscription" :tab="t('Subscription')">
        <AppCard>
          <h3 class="section-title">{{ t('Current Plan') }}</h3>
          <div class="plan-card">
            <div class="plan-card__info">
              <p class="plan-card__name">{{ t('Pro Plan') }}</p>
              <p class="plan-card__desc">{{ t('500 tasks/mo · 50 videos/mo · 100 GB storage · 10 team members') }}</p>
            </div>
            <AppBadge color="brand">{{ t('Active') }}</AppBadge>
          </div>
          <n-divider />
          <p class="section-desc">
            {{ t('To change or cancel your subscription, contact') }}
            <a href="mailto:billing@aiops.example">billing@aiops.example</a>.
          </p>
        </AppCard>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch, h } from 'vue'
import {
  NForm, NFormItem, NInput, NSelect, NButton, NTabs, NTabPane,
  NDivider, NDataTable, NCheckbox, NSlider, type FormInst, type FormRules, type DataTableColumns,
} from 'naive-ui'
import { CubeOutline } from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppEmpty from '@/components/common/AppEmpty.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import AppBadge from '@/components/common/AppBadge.vue'
import { useCompanyStore } from '@/stores/company'
import { useAuthStore } from '@/stores/auth'
import { companiesApi, type VideoBrandingSettings } from '@/api/companies'
import type { CompanyProduct } from '@/types/company'
import MusicPicker from '@/components/video/MusicPicker.vue'
import {useIndustryCatalog} from '@/composables/useIndustryCatalog'

const companyStore = useCompanyStore()
const auth = useAuthStore()
const videoBranding = reactive<VideoBrandingSettings>({enabled: false, text: '', duration_seconds: 3,
  font: 'default', font_size_percent: 6.2, position: 'top_center', margin_x_percent: 8, margin_y_percent: 14})
const brandFonts = ref<{label: string; value: string}[]>([])
const loadingBrandFonts = ref(false)
const brandPositions = [
  {label:'左上',value:'top_left'},{label:'上方居中',value:'top_center'},{label:'右上',value:'top_right'},
  {label:'左侧居中',value:'middle_left'},{label:'正中央',value:'middle_center'},{label:'右侧居中',value:'middle_right'},
  {label:'左下',value:'bottom_left'},{label:'下方居中',value:'bottom_center'},{label:'右下',value:'bottom_right'},
]
const brandAspect = ref('9:16'), brandPreview = ref(''), brandPreviewError = ref(''), loadingBrandPreview = ref(false)
let brandPreviewTimer: ReturnType<typeof setTimeout> | undefined
let brandPreviewRequest = 0
async function updateBrandPreview(request: number) {
  if (!auth.currentCompanyId || !videoBranding.enabled || !videoBranding.text.trim()) return
  loadingBrandPreview.value = true
  try {
    const {data} = await companiesApi.previewVideoBranding(auth.currentCompanyId, {...videoBranding}, brandAspect.value)
    if (request !== brandPreviewRequest) return
    brandPreview.value = `data:image/png;base64,${data.image_base64}`
    brandPreviewError.value = ''
  } catch (e: any) {
    if (request !== brandPreviewRequest) return
    brandPreview.value = ''
    brandPreviewError.value = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : '预览暂不可用，请稍后重试'
  } finally { if (request === brandPreviewRequest) loadingBrandPreview.value = false }
}
watch([videoBranding, brandAspect], () => {
  clearTimeout(brandPreviewTimer)
  const request = ++brandPreviewRequest
  brandPreview.value = ''; loadingBrandPreview.value = false
  brandPreviewTimer = setTimeout(() => updateBrandPreview(request), 350)
})
onBeforeUnmount(() => { clearTimeout(brandPreviewTimer); brandPreviewRequest++ })
const savingBranding = ref(false), brandingMessage = ref('')
async function saveVideoBranding() {
  if (!auth.currentCompanyId) return
  savingBranding.value = true; brandingMessage.value = ''
  try {
    if (videoBranding.enabled && !videoBranding.text.trim()) throw new Error('请填写品牌名称')
    await companiesApi.setVideoBranding(auth.currentCompanyId, {...videoBranding, text: videoBranding.text.trim()})
    await companyStore.fetchCompany()
    brandingMessage.value = videoBranding.enabled ? '已保存，后续成片将自动添加品牌片头。' : '已关闭品牌片头。'
  } catch (e: any) {
    const detail = e.response?.data?.detail
    brandingMessage.value = typeof detail === 'string' ? detail : e.message || '配置无效，请检查名称与展示时长'
  } finally { savingBranding.value = false }
}
const publishLocation = reactive({location_name:'', map_url:'', coordinate_system:'gcj02', map_center_confirmed:false})
const baiduCenterLink=computed(()=>publishLocation.map_url.includes('map.baidu.com')&&publishLocation.map_url.includes('/@'))
const latitudeText=ref(''), longitudeText=ref(''), savingLocation=ref(false), locationMessage=ref('')
const coordinateOptions=[{label:'高德 / GCJ-02',value:'gcj02'},{label:'百度 / BD-09',value:'bd09'},{label:'GPS / WGS84',value:'wgs84'}]
async function savePublishLocation(){
  if(!auth.currentCompanyId)return;
  savingLocation.value=true;locationMessage.value='';
  try{
    const latitude=latitudeText.value.trim()?Number(latitudeText.value):null;
    const longitude=longitudeText.value.trim()?Number(longitudeText.value):null;
    if((latitude!==null&&!Number.isFinite(latitude))||(longitude!==null&&!Number.isFinite(longitude)))throw new Error('请填写有效经纬度');
    await companiesApi.setPublishLocation(auth.currentCompanyId,{...publishLocation,latitude,longitude});
    await Promise.all([companyStore.fetchCompany(),auth.fetchCompanies()]);
    locationMessage.value='已保存到当前企业；下次打开平台窗口或提交发布时生效。';
  }catch(e:any){locationMessage.value=e.response?.data?.detail ? (typeof e.response.data.detail==='string'?e.response.data.detail:'位置配置格式无效，请检查经纬度') : e.message||'保存失败';}
  finally{savingLocation.value=false}
}

const defaultMusicId=ref<string|null>(null),defaultMusicVolume=ref(0.25),savingDefaultMusic=ref(false),defaultMusicMessage=ref('')
const defaultMusicMode=ref<'fixed'|'random'|'none'>('fixed')
async function saveDefaultMusic() {
  if(!auth.currentCompanyId)return
  savingDefaultMusic.value=true;defaultMusicMessage.value=''
  try {
    if(!Number.isFinite(defaultMusicVolume.value)||defaultMusicVolume.value<0||defaultMusicVolume.value>1)throw new Error('音量需在0至1之间')
    await companiesApi.setDefaultVideoMusic(auth.currentCompanyId,{music_asset_id:defaultMusicMode.value==='fixed'?defaultMusicId.value:null,music_volume:defaultMusicVolume.value,selection_mode:defaultMusicMode.value})
    await companyStore.fetchCompany()
    defaultMusicMessage.value=defaultMusicMode.value==='none'?'已保存，后续新视频不添加配乐，模型音轨也会移除。':defaultMusicMode.value==='random'?'已保存，后续数字员工视频将随机选取素材库中的音乐。':defaultMusicId.value?'已保存，后续数字员工自动制作的视频将使用此配乐。':'已关闭默认配乐。'
  } catch(e:any){defaultMusicMessage.value=e.response?.data?.detail||e.message||'保存失败，请重试'}
  finally {savingDefaultMusic.value=false}
}

const activeTab = ref('company')
const companyFormRef = ref<FormInst | null>(null)
const savingCompany = ref(false)
const companySaveMsg = ref('')
const companySaveError = ref(false)
const productsLoading = ref(false)
const products = ref<CompanyProduct[]>([])

const companyForm = reactive({
  name: companyStore.currentCompany?.name ?? '',
  industry: companyStore.currentCompany?.industry ?? null as string | null,
  website: companyStore.currentCompany?.website ?? '',
  description: companyStore.currentCompany?.description ?? '',
})

const companyRules: FormRules = {
  name: [{ required: true, message: t('Name is required'), trigger: 'blur' }],
}

const brand = reactive({
  voice: null as string | null,
  colors: '',
  targetAudience: '',
  keywords: '',
})

const {industryOptions, industryError} = useIndustryCatalog()

const voiceOptions = computed(() => [
  { label: t('Professional'), value: 'professional' },
  { label: t('Friendly'), value: 'friendly' },
  { label: t('Authoritative'), value: 'authoritative' },
  { label: t('Conversational'), value: 'conversational' },
  { label: t('Inspirational'), value: 'inspirational' },
])

const productColumns = computed<DataTableColumns<CompanyProduct>>(() => [
  { title: t('Name'), key: 'name', ellipsis: true },
  { title: 'SKU', key: 'sku', render: (r) => r.sku ?? '—' },
  {
    title: t('Price'),
    key: 'price',
    render: (r) => (r.price != null ? `${r.currency ?? 'USD'} ${r.price.toFixed(2)}` : '—'),
  },
])

onMounted(async () => {
  await companyStore.fetchCompany()
  if (companyStore.currentCompany) {
    companyForm.name = companyStore.currentCompany.name
    companyForm.industry = companyStore.currentCompany.industry ?? null
    if (['hotel','tourism','酒店','酒店与民宿','景区','酒旅'].includes(companyForm.industry || '')) companyForm.industry = 'travel'
    companyForm.website = companyStore.currentCompany.website ?? ''
    companyForm.description = companyStore.currentCompany.description ?? ''
    const goals=companyStore.currentCompany.business_goals??{};
    const opening=(goals.video_branding??{}) as Partial<VideoBrandingSettings>;
    videoBranding.enabled=opening.enabled===true;
    videoBranding.text=opening.text??companyStore.currentCompany.name;
    videoBranding.duration_seconds=opening.duration_seconds??3;
    videoBranding.font=opening.font??'default';
    videoBranding.font_size_percent=opening.font_size_percent??6.2;
    videoBranding.position=opening.position??'top_center';
    videoBranding.margin_x_percent=opening.margin_x_percent??8;
    videoBranding.margin_y_percent=opening.margin_y_percent??14;
    if (auth.currentCompanyId) {
      loadingBrandFonts.value=true;
      try { brandFonts.value=(await companiesApi.videoBrandingFonts(auth.currentCompanyId)).data }
      catch { brandPreviewError.value='字体列表读取失败，请刷新后重试' }
      finally { loadingBrandFonts.value=false }
    }
    const music=(goals.default_video_music??{}) as {music_asset_id?:string|null;music_volume?:number;selection_mode?:'fixed'|'random'|'none'};
    defaultMusicId.value=music.music_asset_id||null;
    defaultMusicVolume.value=music.music_volume??0.25;
    defaultMusicMode.value=music.selection_mode??'fixed';
    const input=(goals.publish_location_input??{}) as Record<string,unknown>;
    publishLocation.location_name=String(input.location_name??goals.publish_location_name??'');
    publishLocation.map_url=String(input.map_url??'');
    publishLocation.coordinate_system=String(input.coordinate_system??'gcj02');
    publishLocation.map_center_confirmed=input.map_center_confirmed===true;
    latitudeText.value=input.latitude==null?'':String(input.latitude);
    longitudeText.value=input.longitude==null?'':String(input.longitude);
  }
  productsLoading.value = true
  try {
    await companyStore.fetchProducts()
    products.value = companyStore.products
  } finally {
    productsLoading.value = false
  }
})

async function saveCompany() {
  companySaveMsg.value = ''
  companySaveError.value = false
  try {
    await companyFormRef.value?.validate()
  } catch {
    return
  }
  savingCompany.value = true
  try {
    await companyStore.updateCompany({
      name: companyForm.name,
      industry: companyForm.industry,
      website: companyForm.website || undefined,
      description: companyForm.description || undefined,
    })
    await auth.fetchCompanies()
    companySaveMsg.value = t('Company info saved.')
  } catch {
    companySaveError.value = true
    companySaveMsg.value = t('Failed to save. Please try again.')
  } finally {
    savingCompany.value = false
  }
}

function saveBrand() {
  // Brand profile persistence would call a backend endpoint
  // Shown as local-only in this implementation
}
</script>

<style scoped>
.brand-controls { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 24px; }
.brand-preview {
  position: relative;
  width: 100%;
  max-width: 360px;
  max-height: 640px;
  overflow: hidden;
  margin: 0 auto var(--space-4);
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, #315e63, #182f31);
}
.brand-preview img { display: block; width: 100%; height: 100%; object-fit: contain; }
@media (max-width: 600px) { .brand-controls { grid-template-columns: minmax(0, 1fr); } }
.tab-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--space-4);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}

.section-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.section-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
}

.plan-card {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4);
  background: var(--color-brand-50);
  border: 1px solid var(--color-brand-200);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
}

.plan-card__name {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
}

.plan-card__desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: 2px;
}

.save-msg {
  font-size: var(--text-sm);
  color: var(--color-success);
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: oklch(93% 0.08 145);
  border-radius: var(--radius-md);
}

.save-msg--error {
  color: var(--color-danger);
  background: oklch(93% 0.08 25);
}
</style>
