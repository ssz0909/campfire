<template>
  <section class="payments">
    <h1>支付与订阅</h1>
    <p class="intro">管理平台收款商户、订阅套餐和AI用量。微信使用 Native 扫码支付，支付宝使用当面付扫码支付。按30天购买，手动续费，不自动扣款。</p>
    <p v-if="loadError" role="alert" class="error">{{ loadError }} <n-button @click="load">重新加载</n-button></p>
    <div class="channels">
      <section v-for="panel in panels" :key="panel.channel" class="panel">
        <header><h2>{{ panel.title }}</h2><n-tag :type="panel.enabled ? 'success' : 'default'">{{ panel.enabled ? '已启用' : '未启用' }}</n-tag></header>
        <p>{{ panel.description }}</p>
        <n-form v-if="panel.loaded" label-placement="top" @submit.prevent="saveChannel(panel)">
          <n-form-item label="允许用户选择此支付渠道"><n-switch v-model:value="panel.enabled" /></n-form-item>
          <template v-for="field in panel.fields" :key="field.key">
            <n-form-item :label="field.label">
              <n-input v-model:value="panel.values[field.key]" :type="field.secret ? (field.multiline ? 'textarea' : 'password') : 'text'"
                :autosize="field.multiline ? { minRows: 3, maxRows: 5 } : undefined" autocomplete="off"
                :placeholder="field.secret ? (panel.configured[field.key] ? '已配置，留空保留；输入新值替换' : '尚未配置') : field.placeholder"
                :input-props="{ spellcheck: false }" :maxlength="field.secret ? 16384 : 2048" />
            </n-form-item>
            <div v-if="field.secret" class="secret-actions">
              <span>{{ panel.configured[field.key] ? '密钥已加密保存，不回显原文' : '未配置密钥' }}</span>
              <n-checkbox :checked="panel.clear.includes(field.key)" @update:checked="toggleClear(panel, field.key, $event)">本次清除</n-checkbox>
            </div>
          </template>
          <p class="hint">{{ panel.channel === 'wechat' ? '配置模式：微信支付 API v3＋微信支付公钥。请填商户API私钥，不是证书文件；微信支付公钥不是商户公钥。' : '配置模式：RSA2 公钥模式。应用私钥与支付宝公钥不能互换；商户UID用于校验收款方。' }}</p>
          <p class="hint">通知地址：<code>{{ notifyUrl(panel.channel) }}</code><n-button text size="small" @click="panel.values.notify_url = notifyUrl(panel.channel)">填入</n-button></p>
          <p v-if="panel.missing.length" class="hint">待补齐：{{ panel.missing.join('、') }}</p>
          <p v-if="panel.error" role="alert" class="error">{{ panel.error }}</p>
          <p v-if="panel.success" role="status" class="success">配置已保存。格式校验通过，实际收款仍需商户权限和真实交易验证。</p>
          <n-button type="primary" attr-type="submit" :loading="panel.saving">保存{{ panel.title }}</n-button>
        </n-form>
      </section>
    </div>
    <section v-if="catalog" class="panel catalog">
      <h2>订阅套餐与计量规则</h2>
      <p>默认套餐是建议售价，可按实际服务成本调整。1点为用量计量单位，不可提现。每期30天，额度到期失效；续费从当前最后一期结束后开始，不叠加到本期。</p>
      <n-form label-placement="top" @submit.prevent="saveCatalog">
        <n-form-item label="付费额度拦截"><n-switch v-model:value="catalog.enforce_billing" /><span class="switch-label">{{ catalog.enforce_billing ? '已开启：无有效订阅或额度不足时不提交模型请求' : '观察模式：记录用量，但不拦截现有用户；确认接入完成后再开启' }}</span></n-form-item>
        <h3>模型成本（仅管理员可见）</h3>
        <div class="rates-grid">
          <n-form-item v-for="field in costFields" :key="field.key" :label="field.label"><n-input-number v-model:value="catalog[field.key]" :min="1" :max="10000000" :precision="0" /></n-form-item>
        </div>
        <h3>用户额度扣减</h3>
        <div class="rates-grid">
          <n-form-item v-for="field in pointFields" :key="field.key" :label="field.label"><n-input-number v-model:value="catalog[field.key]" :min="1" :max="10000000" :precision="0" /></n-form-item>
        </div>
        <p class="hint">视频按实际向模型提交并成功生成的片段秒数计量，不按成片长度。每镜生成5秒但只用2秒，仍计5秒；直接复用分镜不重复扣生成额度。Token按上游返回的实际用量结算。调用前预留额度，明确失败释放；结果不确定暂留待核对。</p>
        <div v-for="(plan, index) in catalog.plans" :key="index" class="plan-row">
          <n-form-item label="标识"><n-input v-model:value="plan.code" placeholder="starter" /></n-form-item>
          <n-form-item label="套餐名称"><n-input v-model:value="plan.name" /></n-form-item>
          <n-form-item label="30天售价（分）"><n-input-number v-model:value="plan.price_fen" :min="1" :max="10000000" :precision="0" /></n-form-item>
          <n-form-item label="包含点数"><n-input-number v-model:value="plan.included_points" :min="1" :max="100000000" :precision="0" /></n-form-item>
          <n-form-item label="上架"><n-switch v-model:value="plan.enabled" /></n-form-item>
        </div>
        <n-button @click="catalog.plans.push({code: 'plan_' + (catalog.plans.length + 1), name: '新套餐', price_fen: 19900, included_points: 6000, enabled: false})" :disabled="catalog.plans.length >= 12">新增套餐</n-button>
        <p class="hint">价格、额度与扣减规则会快照到订单和订阅周期，已购买周期不随配置变更。套餐下架不影响已购买周期。成本参数用于内部估算，不含服务器、支付手续费、售后和税费。</p>
        <p v-if="catalogError" role="alert" class="error">{{ catalogError }}</p><p v-if="catalogSaved" role="status" class="success">套餐配置已保存。</p>
        <n-button type="primary" attr-type="submit" :loading="catalogSaving">保存订阅方案</n-button>
      </n-form>
    </section>
    <section class="panel records"><header><h2>平台订单与用量</h2><n-button :loading="recordsLoading" @click="loadRecords">刷新</n-button></header>
      <p v-if="recordsError" role="alert" class="error">{{ recordsError }}</p>
      <h3>支付订单</h3><div class="table-scroll"><table><thead><tr><th>订单号 / 企业</th><th>套餐</th><th>金额</th><th>渠道</th><th>状态</th></tr></thead><tbody><tr v-for="o in orders" :key="o.id"><td>{{ o.order_no }}<small>{{ o.company_id }}</small></td><td>{{ o.plan_name }}</td><td>¥{{ (o.amount_fen / 100).toFixed(2) }}</td><td>{{ o.channel === 'wechat' ? '微信' : '支付宝' }}</td><td>{{ orderLabels[o.status] || o.status }}</td></tr></tbody></table></div>
      <n-pagination v-model:page="orderPage" :item-count="orderTotal" :page-size="20" @update:page="loadRecords" />
      <h3>AI用量与成本</h3><div class="table-scroll"><table><thead><tr><th>企业</th><th>类型</th><th>状态</th><th>扣减 / 冻结点数</th><th>估算成本</th><th>操作</th></tr></thead><tbody><tr v-for="u in usage" :key="u.id"><td>{{ u.company_id }}</td><td>{{ u.kind === 'video' ? '视频' : '文本/视觉' }}</td><td>{{ usageLabels[u.status] || u.status }}</td><td>{{ u.points }} / {{ u.reserved_points }}</td><td>¥{{ u.cost_yuan.toFixed(4) }}</td><td><n-button v-if="['unknown','reserved'].includes(u.status)" size="small" @click="resolveUsage(u.id)">核对用量</n-button></td></tr></tbody></table></div>
      <n-pagination v-model:page="usagePage" :item-count="usageTotal" :page-size="20" @update:page="loadRecords" />
    </section>
    <section class="panel guide"><h2>接入指引</h2><ol><li>在微信支付商户平台开通Native支付，在支付宝开放平台开通当面付，准备对应应用和商户密钥。</li><li>将通知地址设置为本平台 /api/v1/payments/对应渠道/notify；此地址必须可被支付平台通过HTTPS访问。</li><li>填写商户参数，保存并启用渠道。不要将私钥粘贴到聊天或前端公开配置。</li><li>先在观察模式核对真实小额订单、支付通知、订阅生效及用量，再开启付费额度拦截。</li></ol><p>保存配置不会发起扣款或证明商户产品已开通。此版本支持扫码购买和手动续费；退款在商户后台处理后还需联系平台核对权益，尚未提供自动退款入口。</p></section>
    <n-modal v-model:show="resolutionOpen" preset="card" title="核对AI用量" style="width:min(94vw,520px)">
      <p>请先核对上游调用记录，再选择结算或释放。操作会留下审计记录。运行中的预留须满1小时才能人工核对。</p>
      <n-form label-placement="top" @submit.prevent="submitResolution">
        <n-form-item label="核对结果"><n-select v-model:value="resolution.outcome" :options="[{label:'确认成功，按实际用量结算',value:'settle'},{label:'确认失败或未受理，释放额度',value:'release'}]" /></n-form-item>
        <template v-if="resolution.outcome === 'settle'">
          <n-form-item v-if="resolution.kind === 'video'" label="实际成功生成秒数"><n-input-number v-model:value="resolution.video_seconds" :min="1" :max="3600" :precision="0" /></n-form-item>
          <template v-else><n-form-item label="实际输入Token"><n-input-number v-model:value="resolution.input_tokens" :min="0" :max="100000000" :precision="0" /></n-form-item><n-form-item label="实际输出Token"><n-input-number v-model:value="resolution.output_tokens" :min="0" :max="100000000" :precision="0" /></n-form-item></template>
        </template>
        <n-form-item label="核对依据（至少5字）"><n-input v-model:value="resolution.note" type="textarea" :maxlength="250" :autosize="{minRows:3,maxRows:5}" /></n-form-item>
        <p v-if="resolutionError" role="alert" class="error">{{ resolutionError }}</p>
        <n-button type="primary" attr-type="submit" :loading="resolutionSaving" :disabled="resolution.note.trim().length < 5">确认处理</n-button>
      </n-form>
    </n-modal>
  </section>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { NButton, NCheckbox, NForm, NFormItem, NInput, NInputNumber, NSwitch, NTag, NPagination, NModal, NSelect } from 'naive-ui'
import api from '@/api/client'
type Field = { key: string; label: string; placeholder?: string; secret?: boolean; multiline?: boolean }
const common = [{ key: 'app_id', label: '应用 App ID' }]
const panels = reactive([
  { channel: 'wechat', title: '微信支付', description: '微信支付 API v3 / Native扫码，使用微信支付公钥验签。', fields: [...common,
    { key: 'merchant_id', label: '微信支付商户号' }, { key: 'merchant_serial_no', label: '商户 API 证书序列号' },
    { key: 'api_v3_key', label: 'API v3 密钥（32位）', secret: true }, { key: 'merchant_private_key', label: '商户 API 私钥', secret: true, multiline: true },
    { key: 'wechat_public_key_id', label: '微信支付公钥 ID', placeholder: 'PUB_KEY_ID_…' }, { key: 'wechat_public_key', label: '微信支付公钥', secret: true, multiline: true }, { key: 'notify_url', label: '异步通知地址' }] as Field[] },
  { channel: 'alipay', title: '支付宝支付', description: '当面付扫码 / RSA2公钥模式；使用平台支付宝商户收款。', fields: [...common,
    { key: 'seller_id', label: '支付宝商户 UID（16位）' }, { key: 'app_private_key', label: '应用私钥', secret: true, multiline: true },
    { key: 'alipay_public_key', label: '支付宝公钥', secret: true, multiline: true }, { key: 'notify_url', label: '异步通知地址' }, { key: 'return_url', label: '支付完成返回地址（选填，扫码支付不依赖跳转）', placeholder: 'https://campfire.dawoai.com/subscription' }] as Field[] },
].map(p => ({ ...p, enabled: false, loaded: false, saving: false, values: {} as Record<string, string>, configured: {} as Record<string, boolean>, clear: [] as string[], missing: [] as string[], error: '', success: false })))
type Panel = typeof panels[number]
const loadError = ref(''), catalog = ref<any>(null), catalogError = ref(''), catalogSaved = ref(false), catalogSaving = ref(false)
const recordsLoading = ref(false), recordsError = ref(''), orders = ref<any[]>([]), usage = ref<any[]>([]), orderPage = ref(1), usagePage = ref(1), orderTotal = ref(0), usageTotal = ref(0)
const orderLabels: Record<string,string> = { creating:'创建中',pending:'待支付',paid:'已支付',unknown:'待核对',expired:'已过期',failed:'失败' }
const usageLabels: Record<string,string> = {reserved:'冻结中',unknown:'待核对',settled:'已结算',released:'已释放'}
const costFields = [{key:'video_cost_fen_per_second',label:'视频成本（分/秒）'},{key:'llm_input_cost_fen_per_million',label:'文本输入成本（分/百万Token）'},{key:'llm_output_cost_fen_per_million',label:'文本输出成本（分/百万Token）'}]
const pointFields = [{key:'video_points_per_second',label:'视频（点/生成秒）'},{key:'llm_input_points_per_million',label:'文本输入（点/百万Token）'},{key:'llm_output_points_per_million',label:'文本输出（点/百万Token）'}]
function detail(e: any, fallback: string) { return typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : fallback }
function notifyUrl(channel: string) { return window.location.origin + '/api/v1/payments/' + channel + '/notify' }
function apply(panel: Panel, data: any) { panel.enabled = data.enabled; panel.configured = data.secret_configured; panel.missing = data.missing_fields; panel.clear = []; panel.fields.forEach(f => { panel.values[f.key] = f.secret ? '' : data[f.key] || '' }); panel.loaded = true }
function toggleClear(panel: Panel, key: string, checked: boolean) { panel.clear = checked ? [...panel.clear.filter(x=>x!==key),key] : panel.clear.filter(x=>x!==key); if(checked) panel.values[key]='' }
async function load() { loadError.value=''; const results=await Promise.allSettled([api.get('/admin/payment-settings'),api.get('/admin/billing-settings')]); if(results[0].status==='fulfilled') results[0].value.data.channels.forEach((d:any)=>{const p=panels.find(x=>x.channel===d.channel);if(p) apply(p,d)}); else loadError.value='支付渠道加载失败，请重试。'; if(results[1].status==='fulfilled')catalog.value=results[1].value.data;else loadError.value+=' 订阅方案加载失败。' }
async function saveChannel(panel: Panel) { panel.saving=true;panel.error='';panel.success=false;try{apply(panel,(await api.put('/admin/payment-settings/'+panel.channel,{...panel.values,enabled:panel.enabled,clear_secrets:panel.clear})).data);panel.success=true}catch(e){panel.error=detail(e,'保存失败，请检查字段格式。')}finally{panel.saving=false} }
async function saveCatalog(){catalogSaving.value=true;catalogSaved.value=false;catalogError.value='';try{catalog.value=(await api.put('/admin/billing-settings',catalog.value)).data;catalogSaved.value=true}catch(e){catalogError.value=detail(e,'保存失败，请检查套餐与价格。')}finally{catalogSaving.value=false}}
async function loadRecords(){recordsLoading.value=true;recordsError.value='';const r=await Promise.allSettled([api.get('/admin/payment-orders',{params:{page:orderPage.value}}),api.get('/admin/billing-usage',{params:{page:usagePage.value}})]);if(r[0].status==='fulfilled'){orders.value=r[0].value.data.items;orderTotal.value=r[0].value.data.total}else recordsError.value='订单读取失败。';if(r[1].status==='fulfilled'){usage.value=r[1].value.data.items;usageTotal.value=r[1].value.data.total}else recordsError.value+=' 用量读取失败。';recordsLoading.value=false}
const resolutionOpen=ref(false),resolutionSaving=ref(false),resolutionError=ref('')
const resolution=reactive({id:'',kind:'',outcome:'settle',note:'',input_tokens:0,output_tokens:0,video_seconds:5})
function resolveUsage(id:string){const row=usage.value.find(u=>u.id===id);if(!row)return;Object.assign(resolution,{id,kind:row.kind,outcome:'settle',note:'',input_tokens:0,output_tokens:0,video_seconds:5});resolutionError.value='';resolutionOpen.value=true}
async function submitResolution(){resolutionSaving.value=true;resolutionError.value='';try{await api.post('/admin/billing-usage/'+resolution.id+'/resolve',{outcome:resolution.outcome,note:resolution.note.trim(),input_tokens:resolution.outcome==='settle'&&resolution.kind==='llm'?resolution.input_tokens:0,output_tokens:resolution.outcome==='settle'&&resolution.kind==='llm'?resolution.output_tokens:0,video_seconds:resolution.outcome==='settle'&&resolution.kind==='video'?resolution.video_seconds:0});resolutionOpen.value=false;await loadRecords()}catch(e){resolutionError.value=detail(e,'核对失败，请检查实际用量。')}finally{resolutionSaving.value=false}}
onMounted(()=>{void load();void loadRecords()})
</script>
<style scoped>
.payments{max-width:1320px}.intro,.panel>p,.guide{color:var(--text-secondary)}.channels{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:24px;margin-top:24px}.panel{min-width:0;padding:24px;background:var(--surface-raised,#fff);border:1px solid var(--border-default,#e5e7eb);border-radius:12px}.panel header{display:flex;align-items:center;justify-content:space-between;gap:12px}.panel h2{margin:0 0 16px;font-size:20px}.panel h3{margin-top:24px}.catalog,.records,.guide{margin-top:24px}.hint,.secret-actions{font-size:12px;color:var(--text-secondary);overflow-wrap:anywhere}.secret-actions{display:flex;justify-content:space-between;gap:12px;margin:-10px 0 20px}.rates-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}.plan-row{display:grid;grid-template-columns:1fr 1fr 1fr 1fr 65px;gap:12px;padding-top:12px;border-top:1px solid #e5e7eb}.switch-label{margin-left:12px}.error{color:#c00000}.success{color:#16803c}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:12px;text-align:left;border-bottom:1px solid #e5e7eb}td small{display:block;color:#778195}.n-pagination{margin-top:16px}@media(max-width:800px){.plan-row{grid-template-columns:1fr 1fr}.panel{padding:16px}.switch-label{font-size:12px}}
</style>
