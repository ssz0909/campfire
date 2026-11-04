<template>
  <AppCard>
    <div class="work-header"><h2>任务视频 · 平台播放数据</h2><div class="work-actions">
      <n-select v-model:value="platform" clearable placeholder="全部平台" :options="platformOptions" style="width:150px" @update:value="changeFilter" />
      <n-button v-if="data?.can_sync" :loading="syncing" @click="sync">同步平台数据</n-button><span v-else>播放数据同步需平台发布权限</span>
      <n-button :loading="loading" @click="load">刷新结果</n-button>
    </div></div>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
    <template v-if="data">
      <p>已发布 {{ data.published_works }} 条作品 · 已获取播放量 {{ data.synced_works }} 条 · 待获取 {{ data.published_works-data.synced_works }} 条</p>
      <div class="work-totals"><span v-for="key in keys" :key="key">{{ metricNames[key] }}：<strong>{{ number(data.totals[key]) }}</strong></span></div>
      <p v-for="row in data.platforms" :key="row.platform" class="work-note">{{ row.platform === 'douyin' ? '抖音' : '视频号' }}：已发布 {{ row.published }} 条 · 已获取 {{ row.synced }} 条 · 播放量 {{ number(row.views) }}</p>
      <p class="work-note">{{ data.note }} 通过平台 Web 接口采集，后台不会为数据同步自动启动浏览器。</p>
      <div class="work-accounts"><p v-for="account in data.accounts.filter(a => a.status)" :key="account.account_id">{{ account.label }}：{{ labels[account.status!] || account.status }} {{ account.message || '' }} <span v-if="account.completed_at">· {{ new Date(account.completed_at).toLocaleString() }}</span></p></div>
      <n-data-table :columns="columns" :data="data.items" :bordered="false" :scroll-x="1100" size="small" />
      <n-pagination v-if="data.total>20" v-model:page="page" :page-size="20" :item-count="data.total" @update:page="load" style="margin-top:16px" />
      <p v-if="!data.total" class="work-note">暂无已确认发布的视频；生成完成但未发布的项目不计入播放数据。</p>
    </template>
    <AppLoader v-else-if="loading" variant="table" :rows="3" />
  </AppCard>
</template>
<script setup lang="ts">
import {ref, h, onMounted, onBeforeUnmount, watch} from 'vue'
import {useRouter} from 'vue-router'
import {NButton, NSelect, NDataTable, NPagination, type DataTableColumns} from 'naive-ui'
import AppCard from '@/components/common/AppCard.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import {analyticsApi} from '@/api/analytics'
import type {WorkMetricsSummary, WorkMetricRow} from '@/types/analytics'
const props=defineProps<{companyId:string}>(), router=useRouter()
const data=ref<WorkMetricsSummary|null>(null),loading=ref(false),syncing=ref(false),error=ref(''),message=ref(''),page=ref(1),platform=ref<string|null>(null)
const platformOptions=[{label:'抖音',value:'douyin'},{label:'视频号',value:'wechat_channels'}]
const keys=['views','likes','comments','shares'] as const
const metricNames={views:'已采集播放量',likes:'点赞',comments:'评论',shares:'分享'}
const labels:Record<string,string>={synced:'已采集',partial:'部分作品已采集',metrics_unavailable:'平台暂未提供作品数据',identity_unavailable:'账号身份读取暂不可用',identity_mismatch:'账号身份不匹配',api_setup_required:'需准备接口会话',api_unavailable:'平台接口暂不可用',rate_limited:'平台请求频率受限',not_synced:'待采集',unmatched:'待匹配作品',queued:'等待采集',running:'采集中',failed:'采集失败',login_required:'需重新登录'}
const number=(value:number|null|undefined)=>value==null?'—':value.toLocaleString()
const columns:DataTableColumns<WorkMetricRow>=[
 {title:'作品 / 任务',key:'title',width:260,render:row=>h('div',[h('div',row.title),row.task_id?h(NButton,{text:true,onClick:()=>router.push(`/tasks/${row.task_id}`)},()=>row.task_title||'查看任务'):null])},
 {title:'平台 / 账号',key:'platform',width:170,render:row=>`${row.platform==='douyin'?'抖音':'视频号'} · ${row.account_label}`},
 ...keys.map(key=>({title:key==='views'?'播放量':metricNames[key],key,width:100,render:(row:WorkMetricRow)=>number(row[key])})),
 {title:'采集状态',key:'sync_status',width:230,render:row=>h('div',[h('span',`${labels[row.sync_status]||row.sync_status}${row.duplicate?'（已去重）':''}`),h('p',{class:'work-note'},row.sync_message||(row.captured_at?new Date(row.captured_at).toLocaleString():'等待平台返回作品数据'))])}]
let timer:ReturnType<typeof setTimeout>|undefined,disposed=false,version=0
async function load(){
 clearTimeout(timer);const request=++version;loading.value=true;error.value=''
 try{const res=await analyticsApi.works(props.companyId,{page:page.value,platform:platform.value||undefined});if(!disposed&&request===version){data.value=res.data;if(res.data.accounts.some(a=>['queued','running'].includes(a.status||'')))timer=setTimeout(load,5000)}}
 catch{if(!disposed&&request===version)error.value='播放数据加载失败，请稍后重试。'}finally{if(request===version)loading.value=false}
}
async function sync(){syncing.value=true;error.value='';try{const res=await analyticsApi.syncWorks(props.companyId);message.value=res.data.message;await load()}catch(e:any){error.value=e.response?.data?.detail||'同步失败，请确认有平台数据采集权限。'}finally{syncing.value=false}}
function changeFilter(){page.value=1;load()}
watch(()=>props.companyId,()=>{data.value=null;page.value=1;load()})
onMounted(load);onBeforeUnmount(()=>{disposed=true;++version;clearTimeout(timer)})
</script>
<style scoped>
.work-header,.work-actions,.work-totals{display:flex;align-items:center;gap:16px;flex-wrap:wrap}.work-header{justify-content:space-between}.work-header h2{font-size:18px}.work-note,.work-accounts{font-size:12px;color:var(--text-secondary);line-height:1.6}.work-totals{margin:16px 0}.work-accounts p{margin:4px 0}
</style>
