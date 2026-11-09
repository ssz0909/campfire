<template>
  <div class="geo-page"><h1>GEO · 企业公开主页</h1><p>确认并发布企业信息，让客户和检索系统了解你的服务。站内搜索与外部收录分别统计。</p>
    <p v-if="error" role="alert" class="error">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p><p v-if="loading">正在加载…</p>
    <template v-if="data"><section class="panel"><h2>主页配置 <small>{{ labels[data.status] }}</small></h2>
      <p>当前版本 {{ data.revision }} · 网址在首次发布后锁定，特殊更名请联系平台管理员。</p>
      <label>公开网址标识<input v-model="slug" :disabled="!!data.slug" maxlength="64" placeholder="例如 yunzhongxi" /></label>
      <p v-if="slug">公开地址：/shop/{{ slug }} <button :disabled="busy||!!data.slug" @click="availability">检查是否可用</button></p>

      <div class="grid"><label>品牌色<input type="color" v-model="form.brand_color" /></label><label>模块顺序<select v-model="order"><option value="description,services,faq">介绍 → 服务 → 问答</option><option value="description,faq,services">介绍 → 问答 → 服务</option><option value="services,description,faq">服务 → 介绍 → 问答</option></select></label></div><label class="check"><input type="checkbox" v-model="form.show_services"/> 显示服务模块</label><label class="check"><input type="checkbox" v-model="form.show_faq"/> 显示问答模块</label>
      <div class="grid"><label v-for="field in fields" :key="field.key">{{ field.label }}<textarea v-if="field.long" v-model="form[field.key]" :maxlength="field.max" rows="5"/><input v-else v-model="form[field.key]" :maxlength="field.max" /></label></div>
      <GeoEditor :key="companyId||''" :form="form" :templates="data.templates" :company-id="companyId!" :busy="busy" @preview="preview" @applied="notice='已采用AI建议，请核对并重新确认后保存或发布'" />
      <label class="check"><input type="checkbox" v-model="form.confirmed"/> 我确认以上资料真实、有效，且有权公开所选资料和素材</label>
      <div class="actions"><button :disabled="busy" @click="save">保存草稿</button><button :disabled="busy" @click="preview()">预览草稿</button><button class="primary" :disabled="busy||data.status==='blocked'" @click="publish">发布主页</button><button :disabled="busy||data.status!=='published'" @click="withdraw">撤回公开主页</button></div>
      <p v-if="data.url"><a :href="data.url+'?self_test=1'" target="_blank" rel="noopener">查看公开主页 ↗</a> · <a :href="'/search?self_test=1&q='+encodeURIComponent(form.name||'')" target="_blank" rel="noopener">查看入驻成果：试搜企业名称 ↗</a></p>
      <div v-if="data.check_result?.items"><h3>公开快照检查</h3><p>{{ data.check_result.scope }}</p><p v-for="i in data.check_result.items" :key="i.name">{{ i.passed?'✓':'待完善' }} {{ i.name }}</p><button :disabled="busy" @click="check">重新检查</button></div><p v-if="data.issues?.length">发布前检查：{{ data.issues.join('；') }}</p><p>搜索索引：{{ data.index_status==='semantic_ready'?'语义索引已就绪':data.index_status==='semantic_error'?'向量接口异常，关键词搜索可用':'关键词搜索可用；语义检索需管理员配置向量模型' }}</p>
    </section>
    <section v-if="previewHtml" ref="previewPanel" class="panel"><h2>草稿预览 · {{ previewName }}</h2><p>当前资料的预览，不会保存或改变公开主页。<button @click="mobilePreview=!mobilePreview">{{ mobilePreview?'电脑效果':'手机效果' }}</button> <button @click="previewHtml=''">收起预览</button></p><iframe :class="{mobile:mobilePreview}" title="企业主页草稿预览" :srcdoc="previewHtml" sandbox="" /></section>
    <GeoMetrics v-if="companyId" :company-id="companyId" :key="data.revision"/>
    <section class="panel"><h2>发布历史</h2><p v-if="!versions.length">暂无发布版本</p><details v-for="v in versions" :key="v.revision"><summary>版本 {{ v.revision }} · {{ new Date(v.created_at).toLocaleString() }}</summary><pre>{{ v.content.description }}</pre></details><div class="actions"><button :disabled="versionPage===1" @click="versionPage--;history()">上一页</button><span>第 {{ versionPage }} 页 / {{ Math.max(1,Math.ceil(versionTotal/10)) }} 页</span><button :disabled="versionPage*10>=versionTotal" @click="versionPage++;history()">下一页</button></div></section>
    </template>
  </div>
</template>
<script setup lang="ts">
import {computed,nextTick,ref,watch} from 'vue'
import {useAuthStore} from '@/stores/auth'
import api from '@/api/client'
import GeoMetrics from './GeoMetrics.vue'
import GeoEditor from './GeoEditor.vue'
import {geoPayload} from './geoEditor'
const auth=useAuthStore(),companyId=computed(()=>auth.currentCompanyId)
const data=ref<any>(null),form=ref<any>({}),slug=ref(''),versions=ref<any[]>([]),versionPage=ref(1),versionTotal=ref(0),error=ref(''),notice=ref(''),busy=ref(false),loading=ref(false),previewHtml=ref('')
const previewPanel=ref<HTMLElement>(),previewName=ref(''),mobilePreview=ref(false)
const order=computed({get:()=>form.value.module_order?.join(',')||'description,services,faq',set:(v:string)=>{form.value.module_order=v.split(',')}})
const labels:Record<string,string>={draft:'未发布',published:'已发布',withdrawn:'已撤回',blocked:'平台下架'}
const fields=[{key:'name',label:'公开名称',max:120},{key:'industry',label:'行业（例如 酒旅·住宿）',max:80},{key:'region',label:'地区（例如 浙江 湖州 安吉）',max:120},{key:'address',label:'公开地址',max:300},{key:'contact',label:'公开联系信息',max:300},{key:'description',label:'企业介绍',max:6000,long:true}]
function apply(d:any){data.value={...data.value,...d}}
async function load(){if(!companyId.value)return;loading.value=true;error.value='';try{data.value=(await api.get(`/companies/${companyId.value}/geo`)).data;const d=data.value;form.value={name:'',description:'',industry:'',region:'',address:'',contact:'',services:'',faq:'',template:'generic',cover_asset_id:'',brand_color:'#c05929',show_services:true,show_faq:true,module_order:['description','services','faq'],facts:[],confirmed:false,...(Object.keys(d.draft).length?d.draft:d.suggestion)};form.value.service_items??=form.value.services?[{name:'产品与服务',description:form.value.services}]:[];form.value.faq_items??=form.value.faq?[{question:'常见问题与回答',answer:form.value.faq}]:[];slug.value=d.slug||d.suggested_slug||'';await history()}catch(e:any){error.value=e.response?.data?.detail||'加载失败'}finally{loading.value=false}}
async function history(){const r=await api.get(`/companies/${companyId.value}/geo/versions`,{params:{page:versionPage.value}});versions.value=r.data.items;versionTotal.value=r.data.total}
async function action(fn:()=>Promise<void>){busy.value=true;error.value='';notice.value='';try{await fn()}catch(e:any){error.value=typeof e.response?.data?.detail==='string'?e.response.data.detail:!e.response?e.message:'资料不完整或超过字数限制，请检查后重试'}finally{busy.value=false}}
async function saveDraft(){const r=await api.put(`/companies/${companyId.value}/geo/draft`,{expected_revision:data.value.revision,content:geoPayload(form.value)});apply(r.data)}
function availability(){return action(async()=>{const r=(await api.get(`/companies/${companyId.value}/geo/slug-availability`,{params:{slug:slug.value}})).data;notice.value=r.available?'该网址当前可用，发布时确认占用':'该网址格式不合法或已被保留'})}
function check(){return action(async()=>{data.value.check_result=(await api.post(`/companies/${companyId.value}/geo/check`)).data})}
function save(){return action(async()=>{await saveDraft();notice.value='草稿已保存，公开页面未变化'})}
function preview(code?:string){return action(async()=>{const d=geoPayload(form.value);d.template=code||d.template;previewHtml.value=(await api.post(`/companies/${companyId.value}/geo/preview`,d)).data;previewName.value=data.value.templates.find((t:any)=>t.code===d.template)?.name||d.template;await nextTick();previewPanel.value?.scrollIntoView({behavior:'smooth',block:'start'})})}
function publish(){if(!window.confirm('确认公开以上资料和封面？首次发布后网址不可自行修改。'))return;return action(async()=>{await saveDraft();apply((await api.post(`/companies/${companyId.value}/geo/publish`,{expected_revision:data.value.revision,slug:slug.value})).data);notice.value='主页发布成功，已进入站内搜索';await history()})}
function withdraw(){if(!window.confirm('撤回后主页和封面将停止公开访问，网址仍然保留。'))return;return action(async()=>{apply((await api.post(`/companies/${companyId.value}/geo/withdraw`)).data);notice.value='已撤回'})}
watch(companyId,()=>{data.value=null;previewHtml.value='';versionPage.value=1;load()},{immediate:true})
</script>
<style scoped>
.geo-page{max-width:1100px}.panel{background:var(--color-bg-card,#fff);border:1px solid #dedfd7;border-radius:12px;padding:24px;margin-bottom:24px}h1{font-size:28px}h2{font-size:20px}small{font-weight:normal;color:#68746c}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}label{display:block;margin:14px 0;font-size:14px}input,textarea,select{display:block;width:100%;padding:10px;margin-top:7px;border:1px solid #cbd3ca;border-radius:6px;font:inherit;background:#fff;color:#26332f}input[type=color]{height:42px;padding:4px}.check{display:flex;gap:10px;align-items:center}.check input{width:auto;margin:0}.actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:20px}button{border:1px solid #cbd3ca;border-radius:7px;padding:10px 16px;background:white;color:#26332f;cursor:pointer}button.primary{background:#b44d25;color:white}button:disabled{opacity:.45;cursor:default}.error{color:#b42318}iframe{display:block;box-sizing:border-box;margin:16px auto;width:100%;height:650px;border:1px solid #ddd}iframe.mobile{width:390px;max-width:100%}pre{white-space:pre-wrap}.geo-page{min-width:0}input,textarea,select{box-sizing:border-box}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}@media(max-width:650px){.panel{padding:16px}.grid{grid-template-columns:1fr}}
</style>
