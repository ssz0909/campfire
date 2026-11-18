<template>
  <main class="subscription">
    <AppPageHeader title="订阅" subtitle="为数字员工配置持续运营所需的AI额度" />
    <p v-if="error" class="error" role="alert">{{ error }} <n-button text @click="load">重新加载</n-button></p>
    <p v-if="loading">正在加载订阅信息…</p>
    <template v-if="info">
      <section class="balance panel">
        <div><span class="eyebrow">当前订阅</span><h2>{{ info.period?.plan_name || '尚未订阅' }}</h2>
          <p v-if="info.period">{{ date(info.period.starts_at) }} — {{ date(info.period.ends_at) }}</p>
          <p v-else>选择套餐，为当前工作区开通30天AI用量。</p>
          <p v-if="!info.enforce_billing" class="hint">当前处于用量观察期，暂不限制模型调用。</p>
        </div>
        <div v-if="info.period" class="balance-number"><strong>{{ number(info.period.remaining_points) }}</strong><span>剩余点数 / 共 {{ number(info.period.included_points) }} 点</span><small>已用 {{ number(info.period.used_points) }} · 预留 {{ number(info.period.reserved_points) }}</small></div>
      </section>
      <p v-for="p in info.upcoming_periods" :key="p.id" class="hint">已续订 {{ p.plan_name }}：{{ date(p.starts_at) }} — {{ date(p.ends_at) }}，届时生效 {{ number(p.included_points) }} 点。</p>
      <section class="plans" aria-label="订阅套餐">
        <article v-for="plan in info.plans" :key="plan.code" class="panel plan">
          <h2>{{ plan.name }}</h2><div class="price">¥{{ money(plan.price_fen) }}<small> / 30天</small></div>
          <p class="credits">{{ number(plan.included_points) }} AI点数</p>
          <p>数字员工文本与图片理解、AI视频生成共享额度。</p>
          <p class="hint">若全部用于视频，约 {{ number(plan.included_points / info.rates.video_points_per_second) }} 秒模型生成量；文本调用也会消耗点数。</p>
          <n-button type="primary" block :disabled="!canPurchase || !availableChannels.length" @click="selectPlan(plan)">{{ info.period ? '续订此套餐' : '购买此套餐' }}</n-button>
        </article>
      </section>
      <p v-if="!availableChannels.length" class="hint">在线支付暂未开放，请联系平台开通。</p>
      <p v-if="!canPurchase" class="hint">仅工作区拥有订阅管理权限的成员可购买，请联系工作区负责人。</p>
      <section class="panel rules"><h2>额度如何使用</h2>
        <p>当前新购套餐：视频 {{ info.rates.video_points_per_second }} 点 / 生成秒；文本输入 {{ info.rates.llm_input_points_per_million }} 点 / 百万Token，输出 {{ info.rates.llm_output_points_per_million }} 点 / 百万Token。已购买周期按购买时的规则结算。</p>
        <p v-if="info.period?.rates?.video_points_per_second">本期规则：视频 {{ info.period.rates.video_points_per_second }} 点 / 秒，输入 {{ info.period.rates.llm_input_points_per_million }} 点 / 百万Token，输出 {{ info.period.rates.llm_output_points_per_million }} 点 / 百万Token。</p>
        <p>按模型成功生成的片段秒数计量，不按最终成片时长。生成5秒、剪入2秒仍计5秒；直接复用已有分镜不扣生成点数。调用前预留、按实际用量结算；明确失败释放，结果不确定的请求等待核对。</p>
        <p>每期30天，到期未用额度失效。续订从最后一个已购周期结束后生效，不补充本期额度；本期额度不足可联系平台。手动购买，无自动扣款。支付成功以渠道通知或主动查单结果为准。</p>
      </section>
      <section class="panel history"><header><h2>支付订单</h2><n-button :loading="refreshing" @click="load">刷新</n-button></header>
        <div class="scroll"><table><thead><tr><th>时间 / 订单</th><th>套餐</th><th>金额</th><th>渠道</th><th>状态</th><th>操作</th></tr></thead><tbody>
          <tr v-for="o in orders.items" :key="o.id"><td>{{ date(o.created_at) }}<small>{{ o.order_no }}</small></td><td>{{ o.plan_name }}</td><td>¥{{ money(o.amount_fen) }}</td><td>{{ channelLabel(o.channel) }}</td><td>{{ labels[o.status] || o.status }}</td><td><n-button v-if="o.status !== 'paid'" size="small" @click="showOrder(o)">查看订单</n-button></td></tr>
          <tr v-if="!orders.items.length"><td colspan="6">暂无支付订单</td></tr>
        </tbody></table></div><n-pagination v-model:page="orderPage" :item-count="orders.total" :page-size="20" @update:page="load" />
      </section>
      <section class="panel history"><h2>AI用量明细</h2><div class="scroll"><table><thead><tr><th>时间</th><th>类型</th><th>实际用量</th><th>扣减 / 预留点数</th><th>状态</th></tr></thead><tbody>
        <tr v-for="u in usage.items" :key="u.id"><td>{{ date(u.created_at) }}</td><td>{{ u.kind === 'video' ? '视频生成' : '文本 / 图片理解' }}</td><td>{{ u.kind === 'video' ? u.video_seconds + '秒' : u.input_tokens + '输入 / ' + u.output_tokens + '输出Token' }}</td><td>{{ number(u.charged_points) }} / {{ number(u.reserved_points) }}</td><td>{{ usageLabels[u.status] || u.status }}<small v-if="u.note">{{ u.note }}</small></td></tr>
        <tr v-if="!usage.items.length"><td colspan="5">暂无用量记录</td></tr>
      </tbody></table></div><n-pagination v-model:page="usagePage" :item-count="usage.total" :page-size="20" @update:page="load" /></section>
    </template>
    <n-modal v-model:show="modalOpen" preset="card" :title="currentOrder ? '订阅订单' : '确认订阅'" style="width:min(94vw,480px)" @after-leave="stopPolling">
      <template v-if="currentOrder">
        <h3>{{ currentOrder.plan_name }} · ¥{{ money(currentOrder.amount_fen) }}</h3>
        <p>订单号：{{ currentOrder.order_no }}</p><p>状态：{{ labels[currentOrder.status] || currentOrder.status }}</p>
        <img v-if="currentOrder.qr_image" class="qr" :src="currentOrder.qr_image" :alt="channelLabel(currentOrder.channel) + '支付二维码'" />
        <p v-if="currentOrder.qr_image">请使用{{ channelLabel(currentOrder.channel) }}扫码支付。有效期至 {{ date(currentOrder.expires_at) }}。</p>
        <p v-else-if="currentOrder.status === 'paid'" class="success">支付成功，订阅已开通。</p>
        <p v-else>{{ currentOrder.error_message || '支付二维码已失效，请先查询支付结果，确认未付款后再购买。' }}</p>
        <p v-if="checkoutError" class="error" role="alert">{{ checkoutError }}</p>
        <n-button v-if="canPurchase && currentOrder.status !== 'paid'" type="primary" :loading="checking" @click="queryOrder">我已支付，查询结果</n-button>
      </template>
      <template v-else-if="chosenPlan">
        <h3>{{ chosenPlan.name }} · ¥{{ money(chosenPlan.price_fen) }} / 30天</h3>
        <p>包含 {{ number(chosenPlan.included_points) }} 点。{{ info?.period ? '本次续订将在最后一个已购周期到期后生效。' : '首次支付成功后立即生效。' }}不自动续费。</p>
        <n-radio-group v-model:value="selectedChannel" name="payment-channel"><n-space><n-radio v-for="channel in availableChannels" :key="channel.channel" :value="channel.channel">{{ channelLabel(channel.channel) }}</n-radio></n-space></n-radio-group>
        <p v-if="checkoutError" class="error" role="alert">{{ checkoutError }}</p>
        <n-button type="primary" block :loading="buying" :disabled="!selectedChannel" style="margin-top:24px" @click="buy">确认并获取支付二维码</n-button>
      </template>
    </n-modal>
  </main>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { NButton, NModal, NPagination, NRadio, NRadioGroup, NSpace } from 'naive-ui'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import { useAuthStore } from '@/stores/auth'
import api from '@/api/client'
const auth = useAuthStore()
const info = ref<any>(null), error = ref(''), loading = ref(false), refreshing = ref(false)
const orders = ref<any>({items:[],total:0}), usage = ref<any>({items:[],total:0}), orderPage = ref(1), usagePage = ref(1)
const modalOpen = ref(false), chosenPlan = ref<any>(null), currentOrder = ref<any>(null), selectedChannel = ref(''), buying = ref(false), checking = ref(false), checkoutError = ref('')
let checkoutKey = '', timer: ReturnType<typeof setInterval> | undefined
let generation = 0
const canPurchase = computed(() => info.value?.can_manage === true)
const availableChannels = computed(() => info.value?.channels.filter((c:any) => c.available) || [])
const base = () => '/companies/' + auth.currentCompanyId + '/subscription'
const labels: Record<string,string> = {creating:'创建中',pending:'待支付',paid:'已支付',unknown:'待核对',expired:'已过期',failed:'失败'}
const usageLabels: Record<string,string> = {reserved:'预留中',unknown:'待核对',settled:'已结算',released:'已释放'}
const number = (v:number) => new Intl.NumberFormat('zh-CN',{maximumFractionDigits:4}).format(v)
const money = (v:number) => (v / 100).toFixed(2)
const date = (v:string) => new Date(v).toLocaleString('zh-CN')
const channelLabel = (c:string) => c === 'wechat' ? '微信支付' : '支付宝'
function detail(e:any, fallback:string) { return typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : fallback }
async function load() {
  if (!auth.currentCompanyId) return
  const token = generation, path = base()
  loading.value = !info.value; refreshing.value = true; error.value = ''
  try {
    const results = await Promise.all([api.get(path),api.get(path+'/orders',{params:{page:orderPage.value}}),api.get(path+'/usage',{params:{page:usagePage.value}})])
    if(token !== generation) return
    info.value=results[0].data; orders.value=results[1].data; usage.value=results[2].data
  } catch(e) { if(token === generation) error.value=detail(e,'订阅信息读取失败，请重试。') }
  finally { if(token === generation) { loading.value=false;refreshing.value=false } }
}
function stopPolling() { if(timer) clearInterval(timer);timer=undefined }
function startPolling() {
  stopPolling()
  timer=setInterval(async()=>{
    if(!modalOpen.value || !currentOrder.value || currentOrder.value.status==='paid') return stopPolling()
    const token=generation, id=currentOrder.value.id
    try { const {data}=await api.get(base()+'/orders/'+id);if(token!==generation || currentOrder.value?.id!==id || !modalOpen.value)return;currentOrder.value=data;if(data.status==='paid'){stopPolling();void load()} }
    catch { /* Manual query remains available when a status refresh fails. */ }
  },5000)
}
function selectPlan(plan:any) {stopPolling();chosenPlan.value=plan;currentOrder.value=null;selectedChannel.value=availableChannels.value[0]?.channel || '';checkoutKey=crypto.randomUUID();checkoutError.value='';modalOpen.value=true}
function showOrder(order:any) {currentOrder.value=order;checkoutError.value='';modalOpen.value=true;startPolling()}
async function buy() {
  if(buying.value)return
  const token=generation
  buying.value=true;checkoutError.value=''
  try {const {data}=await api.post(base()+'/orders',{plan_code:chosenPlan.value.code,channel:selectedChannel.value,idempotency_key:checkoutKey});if(token!==generation)return;currentOrder.value=data;startPolling();void load()}
  catch(e){if(token===generation)checkoutError.value=detail(e,'下单响应未确认，请先刷新订单记录，避免重复付款。')}
  finally{if(token===generation)buying.value=false}
}
async function queryOrder() {
  if(checking.value)return
  const token=generation,id=currentOrder.value.id
  checking.value=true;checkoutError.value=''
  try{const {data}=await api.post(base()+'/orders/'+id+'/query');if(token!==generation || currentOrder.value?.id!==id)return;currentOrder.value=data;if(data.status==='paid'){stopPolling();await load()}else checkoutError.value='尚未确认到账，请稍后重试，勿重复付款。'}
  catch(e){if(token===generation)checkoutError.value=detail(e,'暂无法确认支付结果，请稍后重试。')}
  finally{if(token===generation)checking.value=false}
}
watch(()=>auth.currentCompanyId,()=>{generation++;stopPolling();modalOpen.value=false;info.value=null;buying.value=false;checking.value=false;orders.value={items:[],total:0};usage.value={items:[],total:0};orderPage.value=1;usagePage.value=1;void load()},{immediate:true})
watch(selectedChannel,()=>{checkoutKey=crypto.randomUUID()})
watch(modalOpen,value=>{if(!value)stopPolling()})
onBeforeUnmount(()=>{generation++;stopPolling()})
</script>
<style scoped>
.subscription{max-width:1280px;margin:auto}.panel{padding:24px;border:1px solid var(--border-default,#e5e7eb);border-radius:16px;background:var(--surface-raised,#fff)}.balance{display:flex;align-items:center;justify-content:space-between;gap:24px}.eyebrow,.hint,small{color:var(--text-secondary,#64748b)}h2{margin:4px 0 12px;font-size:21px}.balance-number{text-align:right;display:grid;gap:6px}.balance-number strong{font-size:36px;color:var(--primary,#e77d38)}.plans{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin:24px 0}.plan{display:flex;flex-direction:column;gap:8px}.plan .n-button{margin-top:auto}.price{font-size:36px;font-weight:700}.price small{font-size:14px;font-weight:400}.credits{font-weight:600}.plan p{margin:4px 0 12px;line-height:1.7}.hint,.rules p{font-size:13px;line-height:1.8}.rules,.history{margin-top:24px}.history header{display:flex;justify-content:space-between;align-items:center}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;vertical-align:top;padding:14px 10px;border-bottom:1px solid var(--border-default,#e5e7eb)}td small{display:block;font-size:11px;max-width:260px;overflow-wrap:anywhere}.n-pagination{margin-top:18px}.qr{width:240px;max-width:100%;display:block;margin:16px auto}.error{color:#c00000}.success{color:#16803c}@media(max-width:850px){.plans{grid-template-columns:1fr}.balance{align-items:flex-start;flex-direction:column}.balance-number{text-align:left}.panel{padding:18px}}
</style>
