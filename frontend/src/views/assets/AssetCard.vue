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
      <button v-if="asset.asset_type === 'image' && asset.file_url" class="asset-card__preview" type="button" :aria-label="`预览${asset.name}`" @click.stop="showPreview=true">
        <EyeOutline />
      </button>
      <StatusBadge
        v-if="asset.processing_status !== 'ready'"
        :status="asset.processing_status"
        class="asset-card__status"
      />
    </div>
    <div class="asset-card__body">
      <p class="asset-card__name" :title="asset.name">{{ asset.name }}</p>
      <p v-if="asset.metadata?.production_mode === 'raw_model_clip'" class="asset-card__description">AI原始分镜 · {{ asset.metadata.clip_library?.review_status === 'approved' ? '已审核可复用' : '待成片审核' }} · 已复用 {{ asset.metadata.clip_library?.usage_count || 0 }} 次</p>
      <div class="asset-card__meta">
        <AppBadge>{{ asset.asset_type === 'audio' ? '音频' : asset.asset_type }}</AppBadge>
        <span class="asset-card__size">{{ formatBytes(asset.file_size_bytes) }}</span>
      </div>
      <audio v-if="asset.asset_type === 'audio' && asset.processing_status === 'ready' && asset.file_url"
        :src="asset.file_url" controls preload="none" class="asset-card__audio" @click.stop />
      <video v-if="asset.asset_type === 'video' && asset.file_url"
        :src="asset.file_url" :poster="asset.thumbnail_url" controls preload="none" class="asset-card__audio" @click.stop />
      <section v-if="asset.asset_type === 'image'" class="asset-card__related">
        <button class="asset-card__related-toggle" type="button" :disabled="relatedLoading" @click.stop="openRelated">
          <VideocamOutline aria-hidden="true" />
          <span>查看分镜视频</span>
          <span v-if="relatedLoaded" class="asset-card__related-count">{{ relatedTotal }} 条</span>
          <ChevronForwardOutline class="asset-card__related-chevron" aria-hidden="true" />
        </button>
      </section>
      <div v-if="asset.tags?.length" class="asset-card__tags">
        <AppBadge v-for="tag in asset.tags.slice(0, 3)" :key="tag">{{ tag }}</AppBadge>
      </div>
      <p v-if="asset.category" class="asset-card__description">{{ categoryName(asset.category) }} · {{ asset.source_description }}</p>
      <p v-if="['pending','running'].includes(asset.metadata?.vision_analysis?.status || '')" class="asset-card__description">图片内容识别中…</p>
      <p v-if="asset.metadata?.vision_analysis?.detail" class="asset-card__description">{{ asset.metadata.vision_analysis.detail }}</p>
      <p v-else-if="asset.metadata?.vision_analysis?.error" class="asset-card__description">{{ asset.metadata.vision_analysis.error }}</p>
    </div>
    <div class="asset-card__actions">
      <n-button v-if="asset.asset_type === 'image'" size="tiny" quaternary @click.stop="openRegenerate()">生成分镜</n-button>
      <n-button size="tiny" quaternary @click.stop="emit('edit')">编辑标签</n-button>
      <n-button v-if="asset.asset_type === 'image'" size="tiny" quaternary @click.stop="emit('analyze')">重新识别</n-button>
      <n-button size="tiny" ghost @click.stop="emit('delete')">{{ t('Delete') }}</n-button>
    </div>
  </AppCard>
  <n-modal v-model:show="showRelated" preset="card" :title="`${asset.name} · 分镜视频`" class="clips-modal" style="width:min(880px, calc(100vw - 24px))" @update:show="onRelatedVisibility">
    <div class="clips-modal__body">
      <p v-if="relatedJobs.some(job => ['analyzing','generating_shots','compositing','waiting_retry'].includes(job.status))">分镜生成中，完成后会显示在这里。</p>
      <p v-for="job in relatedJobs.filter(job => job.status === 'failed')" :key="job.id" class="asset-card__error">分镜生成失败：{{ job.error || '请重新填写提示词后再试' }}</p>
      <template v-if="selectedClip">
        <video :key="selectedClip.id" class="clips-modal__video" :src="selectedClip.file_url" :poster="selectedClip.thumbnail_url" controls preload="metadata" />
        <div class="clips-modal__details">
          <div><strong>{{ selectedClip.name }}</strong><p>{{ selectedClip.source_description }}</p><p v-if="selectedClip.metadata?.clip_library?.manual_variant && selectedClip.metadata?.clip_library?.prompt">修改要求：{{ selectedClip.metadata.clip_library.prompt }}</p><p>{{ selectedClip.metadata?.clip_library?.review_status === 'approved' ? '已审核可复用' : '待审核' }} · 已复用 {{ selectedClip.metadata?.clip_library?.usage_count || 0 }} 次</p></div>
          <span>{{ (relatedPage - 1) * 10 + selectedIndex + 1 }} / {{ relatedTotal }}</span>
        </div>
        <div class="clips-modal__actions">
          <n-button type="primary" size="small" @click="openRegenerate(selectedClip)">重新生成分镜</n-button>
          <n-button v-if="selectedClip.metadata?.clip_library?.manual_variant && selectedClip.metadata?.clip_library?.review_status !== 'approved'" size="small" :loading="approvingId===selectedClip.id" @click="approveClip(selectedClip)">加入可复用素材</n-button>
          <n-button size="small" type="error" secondary @click="clipToDelete=selectedClip;showDeleteClip=true">删除分镜</n-button>
        </div>
        <div class="clips-modal__navigation">
          <n-button circle size="small" :disabled="relatedLoading || (relatedPage === 1 && selectedIndex === 0)" title="上一个分镜" aria-label="上一个分镜" @click="moveClip(-1)"><template #icon><ChevronBackOutline /></template></n-button>
          <div class="clips-modal__strip" aria-label="分镜列表">
            <button v-for="(clip, index) in relatedClips" :key="clip.id" class="clips-modal__thumbnail" :class="{'is-selected':selectedClip.id===clip.id}" type="button" :aria-label="`选择分镜 ${((relatedPage-1)*10)+index+1}`" :aria-pressed="selectedClip.id===clip.id" @click="selectedIndex=index">
              <img v-if="clip.thumbnail_url" :src="clip.thumbnail_url" :alt="clip.name" /><VideocamOutline v-else aria-hidden="true" /><span>{{ (relatedPage-1)*10+index+1 }}</span>
            </button>
          </div>
          <n-button circle size="small" :disabled="relatedLoading || (relatedPage-1)*10+selectedIndex+1 >= relatedTotal" title="下一个分镜" aria-label="下一个分镜" @click="moveClip(1)"><template #icon><ChevronForwardOutline /></template></n-button>
        </div>
      </template>
      <p v-else-if="!relatedLoading">暂无基于此图片生成的分镜。</p>
      <div class="clips-modal__footer"><n-button size="small" :loading="relatedLoading" @click="loadRelated">刷新</n-button><n-pagination v-if="relatedTotal > 10" v-model:page="relatedPage" :page-size="10" :item-count="relatedTotal" simple @update:page="changeRelatedPage" /></div>
    </div>
  </n-modal>
  <ConfirmDialog v-model:show="showDeleteClip" title="删除分镜" message="删除后该分镜将不能再用于新视频，原图片和已生成的成片会保留。确认删除吗？" type="error" confirm-text="删除" :loading="deleteClipBusy" @confirm="deleteClip" />
  <n-modal v-model:show="showPreview" preset="card" :title="asset.name" style="width:min(900px, calc(100vw - 32px))">
    <img v-if="asset.asset_type === 'image'" :src="asset.file_url" :alt="asset.name" class="asset-preview-full" />
    <video v-else :src="asset.file_url" :poster="asset.thumbnail_url" controls autoplay class="asset-preview-full" />
    <p v-if="asset.source_description">{{ asset.source_description }}</p>
  </n-modal>
  <n-modal v-model:show="showRegenerate" preset="card" title="重新生成分镜" style="width:min(560px, calc(100vw - 32px))">
    <p class="asset-card__description">会使用原图片和画幅生成新的独立5秒分镜；不会修改原片或自动加入复用库。</p>
    <n-select v-if="regenerationTarget?.asset_type === 'image'" v-model:value="regenerationAspect" :options="aspectOptions" style="margin-bottom:12px" />
    <p>提交后将调用视频模型，可能产生费用。生成后可预览并确认加入可复用素材。</p>
    <n-input v-model:value="regenerationPrompt" type="textarea" :autosize="{minRows:4,maxRows:8}" maxlength="2000" placeholder="描述希望改进的动作、镜头、节奏或画面细节" />
    <p v-if="regenerationError" class="asset-card__error" role="alert">{{ regenerationError }}</p>
    <template #footer><n-button @click="showRegenerate=false">取消</n-button><n-button type="primary" :loading="regenerationBusy" :disabled="regenerationPrompt.trim().length < 4" @click="regenerateClip">提交生成</n-button></template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NModal, NPagination, NSelect, useMessage } from 'naive-ui'
import {
  ImageOutline,
  VideocamOutline,
  DocumentOutline,
  MusicalNotesOutline,
  AttachOutline,
  EyeOutline,
  ChevronBackOutline,
  ChevronForwardOutline,
} from '@vicons/ionicons5'
import AppCard from '@/components/common/AppCard.vue'
import AppBadge from '@/components/common/AppBadge.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import type { Asset } from '@/types/asset'

import type { AssetType } from '@/types/asset'
import { useAuthStore } from '@/stores/auth'
import { assetsApi } from '@/api/assets'

const props = defineProps<{ asset: Asset }>()
const emit = defineEmits<{ delete: []; edit: []; analyze: [] }>()
const { t } = useI18n()
const auth = useAuthStore(), message = useMessage()
const relatedPage=ref(1),regenerationAspect=ref('9:16'),regenerationRequestId=ref('')
const selectedIndex=ref(0),showDeleteClip=ref(false),deleteClipBusy=ref(false),clipToDelete=ref<Asset|null>(null)
const aspectOptions=[{label:'竖屏 9:16',value:'9:16'},{label:'横屏 16:9',value:'16:9'},{label:'方形 1:1',value:'1:1'}]
const showPreview=ref(false),showRegenerate=ref(false),regenerationPrompt=ref(''),regenerationBusy=ref(false),regenerationError=ref(''),approvingId=ref(''),relatedLoading=ref(false),relatedLoaded=ref(false),showRelated=ref(false),relatedClips=ref<Asset[]>([]),relatedJobs=ref<Array<{id:string;status:string;error?:string|null}>>([]),relatedTotal=ref(0),regenerationTarget=ref<Asset|null>(null)
let relatedTimer:ReturnType<typeof setInterval>|undefined
const selectedClip=computed(()=>relatedClips.value[selectedIndex.value] || null)
onUnmounted(()=>{if(relatedTimer)clearInterval(relatedTimer)})
async function loadRelated(){
  if(!auth.currentCompanyId || relatedLoading.value)return
  relatedLoading.value=true
  try{const selectedId=selectedClip.value?.id;const result=await assetsApi.relatedClips(auth.currentCompanyId,props.asset.id,relatedPage.value);relatedClips.value=result.items;relatedJobs.value=result.jobs;relatedTotal.value=result.total;relatedLoaded.value=true
    const previousIndex=result.items.findIndex(clip=>clip.id===selectedId);selectedIndex.value=previousIndex>=0?previousIndex:Math.min(selectedIndex.value,Math.max(0,result.items.length-1))
    const active=result.jobs.some(job=>['analyzing','generating_shots','compositing','waiting_retry'].includes(job.status))
    if(active&&!relatedTimer)relatedTimer=setInterval(()=>{if(showRelated.value)loadRelated()},4000)
    if(!active&&relatedTimer){clearInterval(relatedTimer);relatedTimer=undefined}
  }
  catch(e:any){message.error(e.response?.data?.detail||'分镜素材加载失败')}
  finally{relatedLoading.value=false}
}
async function openRelated(){showRelated.value=true;await loadRelated()}
function onRelatedVisibility(show:boolean){if(!show && relatedTimer){clearInterval(relatedTimer);relatedTimer=undefined}}
async function changeRelatedPage(){selectedIndex.value=0;await loadRelated()}
async function moveClip(direction:number){const next=selectedIndex.value+direction;if(next>=0 && next<relatedClips.value.length){selectedIndex.value=next;return}relatedPage.value+=direction;selectedIndex.value=direction>0?0:9;await loadRelated()}
async function deleteClip(){if(!auth.currentCompanyId || !clipToDelete.value)return;deleteClipBusy.value=true;try{await assetsApi.delete(auth.currentCompanyId,clipToDelete.value.id);showDeleteClip.value=false;message.success('分镜已删除');if(relatedClips.value.length===1 && relatedPage.value>1){relatedPage.value--;selectedIndex.value=9}await loadRelated()}catch(e:any){message.error(e.response?.data?.detail||'删除分镜失败')}finally{deleteClipBusy.value=false}}
function openRegenerate(clip?:Asset){regenerationTarget.value=clip||props.asset;regenerationPrompt.value=(clip?.metadata?.clip_library?.prompt||'').slice(0,2000);regenerationAspect.value='9:16';regenerationRequestId.value=crypto.randomUUID();regenerationError.value='';showRegenerate.value=true}
async function regenerateClip(){
  if(!auth.currentCompanyId)return
  regenerationBusy.value=true;regenerationError.value=''
  try{await assetsApi.regenerateClip(auth.currentCompanyId,regenerationTarget.value?.id||props.asset.id,regenerationPrompt.value.trim(),regenerationAspect.value,regenerationRequestId.value);relatedPage.value=1;showRegenerate.value=false;message.success('已提交分镜生成，完成后会显示在原图片下方');showRelated.value=true;await loadRelated()}
  catch(e:any){regenerationError.value=e.response?.data?.detail||'提交失败，请重试'}
  finally{regenerationBusy.value=false}
}
async function approveClip(target=regenerationTarget.value||props.asset){
  if(!auth.currentCompanyId)return
  approvingId.value=target.id
  try{await assetsApi.approveClip(auth.currentCompanyId,target.id);message.success('已加入可复用素材');await loadRelated()}
  catch(e:any){message.error(e.response?.data?.detail||'加入复用库失败')}
  finally{approvingId.value=''}
}

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
.asset-card__audio { display:block;width:100%;max-width:100%;margin-top:12px; }

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
.asset-card__preview { position:absolute;inset:0;border:0;background:transparent;color:transparent;cursor:zoom-in;display:grid;place-items:center; }
.asset-card__preview :deep(svg) { width:24px;height:24px; }
.asset-card__preview:hover,.asset-card__preview:focus-visible { background:rgba(0,0,0,.28);color:white; }
.asset-card__related { padding:0; }
.asset-card__related-toggle { display:flex;align-items:center;gap:8px;width:100%;min-height:42px;padding:8px 12px;border:1px solid #b9d5cc;border-radius:6px;background:#eff8f4;color:#17634f;font-size:14px;font-weight:600;text-align:left;cursor:pointer; }
.asset-card__related-toggle:hover { background:#dcefe7;border-color:#77b4a0; }
.asset-card__related-toggle:focus-visible { outline:2px solid #17634f;outline-offset:2px; }
.asset-card__related-toggle:disabled { cursor:wait;opacity:.7; }
.asset-card__related-toggle svg { width:18px;height:18px;flex:none; }
.asset-card__related-count { margin-left:auto;font-size:12px;font-weight:500;white-space:nowrap; }
.asset-card__related-chevron { margin-left:auto;transition:transform .15s; }
.asset-card__related-count + .asset-card__related-chevron { margin-left:0; }
.asset-card__related-chevron.is-open { transform:rotate(180deg); }
.clips-modal__body { display:grid;gap:12px;max-height:calc(100dvh - 150px);overflow-y:auto; }
.clips-modal__video { display:block;width:100%;height:min(42vh,360px);background:#171a19;object-fit:contain;border-radius:4px; }
.clips-modal__details { display:flex;justify-content:space-between;gap:12px;font-size:13px;overflow-wrap:anywhere; }
.clips-modal__details p { margin:4px 0;color:var(--text-secondary); }
.clips-modal__details > span { white-space:nowrap;font-variant-numeric:tabular-nums; }
.clips-modal__actions,.clips-modal__footer { display:flex;align-items:center;gap:8px;flex-wrap:wrap; }
.clips-modal__footer { justify-content:space-between; }
.clips-modal__navigation { display:flex;align-items:center;gap:8px;min-width:0; }
.clips-modal__strip { display:flex;gap:8px;min-width:0;overflow-x:auto;overscroll-behavior-x:contain;scroll-snap-type:x proximity;padding:3px;flex:1; }
.clips-modal__thumbnail { position:relative;display:grid;place-items:center;flex:0 0 82px;height:58px;overflow:hidden;scroll-snap-align:start;border:2px solid transparent;border-radius:4px;background:#e7edeb;color:#4c625c;cursor:pointer; }
.clips-modal__thumbnail.is-selected { border-color:#17634f; }
.clips-modal__thumbnail:focus-visible { outline:2px solid #17634f;outline-offset:1px; }
.clips-modal__thumbnail img { width:100%;height:100%;object-fit:cover; }
.clips-modal__thumbnail svg { width:22px;height:22px; }
.clips-modal__thumbnail span { position:absolute;right:3px;bottom:3px;padding:1px 4px;border-radius:2px;background:#17201dcc;color:white;font-size:11px; }
.asset-preview-full { display:block;max-width:100%;max-height:72vh;margin:0 auto;object-fit:contain; }
.asset-card__error { color:var(--color-danger);font-size:13px; }

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
  flex-wrap:wrap;gap:4px;
}
</style>
