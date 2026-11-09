<template>
  <div class="geo-page"><h1>GEO · 企业公开主页</h1><p>确认并发布企业信息，让客户和检索系统了解你的服务。站内搜索与外部收录分别统计。</p>
    <p v-if="error" role="alert" class="error">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p><p v-if="loading">正在加载…</p>
    <template v-if="data"><section class="panel"><h2>主页配置 <small>{{ labels[data.status] }}</small></h2>
      <p>当前版本 {{ data.revision }} · 网址在首次发布后锁定，特殊更名请联系平台管理员。</p>
      <label>公开网址标识<input v-model="slug" :disabled="!!data.slug" maxlength="64" placeholder="例如 yunzhongxi" /></label>
      <p v-if="slug">公开地址：/shop/{{ slug }} <button :disabled="busy||!!data.slug" @click="availability">检查是否可用</button></p>
      <label>主页模板<select v-model="form.template"><option v-for="t in data.templates" :key="t.code" :value="t.code">{{ t.name }}</option></select></label>
      <div class="grid"><label>品牌色<input type="color" v-model="form.brand_color" /></label><label>模块顺序<select v-model="order"><option value="description,services,faq">介绍 → 服务 → 问答</option><option value="description,faq,services">介绍 → 问答 → 服务</option><option value="services,description,faq">服务 → 介绍 → 问答</option></select></label></div><label class="check"><input type="checkbox" v-model="form.show_services"/> 显示服务模块</label><label class="check"><input type="checkbox" v-model="form.show_faq"/> 显示问答模块</label>
      <div class="grid"><label v-for="field in fields" :key="field.key">{{ field.label }}<textarea v-if="field.long" v-model="form[field.key]" :maxlength="field.max" rows="5"/><input v-else v-model="form[field.key]" :maxlength="field.max" /></label></div>
      <label>公开封面（可选）<select v-model="form.cover_asset_id"><option value="">不使用封面</option><option v-for="a in assets" :key="a.id" :value="a.id">{{ a.name }}</option></select></label>
      <p><small>所选封面随主页公开，撤回或下架后停止公开访问。仅选择有权公开使用的图片。</small></p>
      <section><h3>事实与依据（可选）</h3><p>额外的服务承诺、资质或时效信息请注明依据；未确认或已过期的事实会阻止发布。</p><div class="grid" v-for="(f,i) in form.facts" :key="i"><label>事实名称<input v-model="f.key" maxlength="100"/></label><label>内容<input v-model="f.value" maxlength="1000"/></label><label>依据 / 信息来源<input v-model="f.source" maxlength="500"/></label><label>有效期（可选）<input type="date" v-model="f.valid_until" @change="f.valid_until=f.valid_until||null"/></label><label class="check"><input type="checkbox" :checked="f.status==='confirmed'" @change="f.status=($event.target as HTMLInputElement).checked?'confirmed':'pending'"/> 企业确认真实</label><button @click="form.facts.splice(i,1)">移除事实</button></div><button :disabled="form.facts?.length>=30" @click="form.facts.push({key:'',value:'',source:'',status:'pending',valid_until:null})">添加事实与依据</button></section>
      <label class="check"><input type="checkbox" v-model="form.confirmed"/> 我确认以上资料真实、有效，且有权公开所选资料和素材</label>
      <div class="actions"><button :disabled="busy" @click="save">保存草稿</button><button :disabled="busy" @click="preview">预览草稿</button><button class="primary" :disabled="busy||data.status==='blocked'" @click="publish">发布主页</button><button :disabled="busy||data.status!=='published'" @click="withdraw">撤回公开主页</button></div>
      <p v-if="data.url"><a :href="data.url+'?self_test=1'" target="_blank" rel="noopener">查看公开主页 ↗</a> · <a :href="'/search?self_test=1&q='+encodeURIComponent(form.name||'')" target="_blank" rel="noopener">查看入驻成果：试搜企业名称 ↗</a></p>
      <div v-if="data.check_result?.items"><h3>公开快照检查</h3><p>{{ data.check_result.scope }}</p><p v-for="i in data.check_result.items" :key="i.name">{{ i.passed?'✓':'待完善' }} {{ i.name }}</p><button :disabled="busy" @click="check">重新检查</button></div><p v-if="data.issues?.length">发布前检查：{{ data.issues.join('；') }}</p><p>搜索索引：{{ data.index_status==='semantic_ready'?'语义索引已就绪':data.index_status==='semantic_error'?'向量接口异常，关键词搜索可用':'关键词搜索可用；语义检索需管理员配置向量模型' }}</p>
    </section>
    <section v-if="previewHtml" class="panel"><h2>草稿预览</h2><iframe title="企业主页草稿预览" :srcdoc="previewHtml" sandbox="" /></section>
    <GeoMetrics v-if="companyId" :company-id="companyId" :key="data.revision"/>
    <section class="panel"><h2>发布历史</h2><p v-if="!versions.length">暂无发布版本</p><details v-for="v in versions" :key="v.revision"><summary>版本 {{ v.revision }} · {{ new Date(v.created_at).toLocaleString() }}</summary><pre>{{ v.content.description }}</pre></details><div class="actions"><button :disabled="versionPage===1" @click="versionPage--;history()">上一页</button><span>第 {{ versionPage }} 页 / {{ Math.max(1,Math.ceil(versionTotal/10)) }} 页</span><button :disabled="versionPage*10>=versionTotal" @click="versionPage++;history()">下一页</button></div></section>
    </template>
  </div>
</template>
<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {useAuthStore} from '@/stores/auth'
import api from '@/api/client'
import GeoMetrics from './GeoMetrics.vue'
const auth=useAuthStore(),companyId=computed(()=>auth.currentCompanyId)
const data=ref<any>(null),form=ref<any>({}),slug=ref(''),assets=ref<any[]>([]),versions=ref<any[]>([]),versionPage=ref(1),versionTotal=ref(0),error=ref(''),notice=ref(''),busy=ref(false),loading=ref(false),previewHtml=ref('')
const order=computed({get:()=>form.value.module_order?.join(',')||'description,services,faq',set:(v:string)=>{form.value.module_order=v.split(',')}})
const labels:Record<string,string>={draft:'未发布',published:'已发布',withdrawn:'已撤回',blocked:'平台下架'}
const fields=[{key:'name',label:'公开名称',max:120},{key:'industry',label:'行业（例如 酒旅·住宿）',max:80},{key:'region',label:'地区（例如 浙江 湖州 安吉）',max:120},{key:'address',label:'公开地址',max:300},{key:'contact',label:'公开联系信息',max:300},{key:'description',label:'企业介绍',max:6000,long:true},{key:'services',label:'实际提供的产品与服务',max:6000,long:true},{key:'faq',label:'常见问题与回答',max:6000,long:true}]
function apply(d:any){data.value={...data.value,...d}}
async function load(){if(!companyId.value)return;loading.value=true;error.value='';try{data.value=(await api.get(`/companies/${companyId.value}/geo`)).data;const d=data.value;form.value={name:'',description:'',industry:'',region:'',address:'',contact:'',services:'',faq:'',template:'generic',cover_asset_id:'',brand_color:'#c05929',show_services:true,show_faq:true,module_order:['description','services','faq'],facts:[],confirmed:false,...(Object.keys(d.draft).length?d.draft:d.suggestion)};slug.value=d.slug||d.suggested_slug||'';await history();try{const r=await api.get(`/companies/${companyId.value}/assets`,{params:{asset_type:'image',page_size:100}});assets.value=(r.data.items||r.data.assets||[]).filter((a:any)=>['image/jpeg','image/png','image/webp'].includes(a.mime_type))}catch{assets.value=[]}}catch(e:any){error.value=e.response?.data?.detail||'加载失败'}finally{loading.value=false}}
async function history(){const r=await api.get(`/companies/${companyId.value}/geo/versions`,{params:{page:versionPage.value}});versions.value=r.data.items;versionTotal.value=r.data.total}
async function action(fn:()=>Promise<void>){busy.value=true;error.value='';notice.value='';try{await fn()}catch(e:any){error.value=typeof e.response?.data?.detail==='string'?e.response.data.detail:'操作失败，请检查资料后重试'}finally{busy.value=false}}
async function saveDraft(){const r=await api.put(`/companies/${companyId.value}/geo/draft`,{expected_revision:data.value.revision,content:form.value});apply(r.data)}
function availability(){return action(async()=>{const r=(await api.get(`/companies/${companyId.value}/geo/slug-availability`,{params:{slug:slug.value}})).data;notice.value=r.available?'该网址当前可用，发布时确认占用':'该网址格式不合法或已被保留'})}
function check(){return action(async()=>{data.value.check_result=(await api.post(`/companies/${companyId.value}/geo/check`)).data})}
function save(){return action(async()=>{await saveDraft();notice.value='草稿已保存，公开页面未变化'})}
function preview(){return action(async()=>{await saveDraft();previewHtml.value=(await api.get(`/companies/${companyId.value}/geo/preview`)).data})}
function publish(){if(!window.confirm('确认公开以上资料和封面？首次发布后网址不可自行修改。'))return;return action(async()=>{await saveDraft();apply((await api.post(`/companies/${companyId.value}/geo/publish`,{expected_revision:data.value.revision,slug:slug.value})).data);notice.value='主页发布成功，已进入站内搜索';await history()})}
function withdraw(){if(!window.confirm('撤回后主页和封面将停止公开访问，网址仍然保留。'))return;return action(async()=>{apply((await api.post(`/companies/${companyId.value}/geo/withdraw`)).data);notice.value='已撤回'})}
watch(companyId,()=>{data.value=null;previewHtml.value='';versionPage.value=1;load()},{immediate:true})
</script>
<style scoped>
.geo-page{max-width:1100px}.panel{background:var(--color-bg-card,#fff);border:1px solid #dedfd7;border-radius:12px;padding:24px;margin-bottom:24px}h1{font-size:28px}h2{font-size:20px}small{font-weight:normal;color:#68746c}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}label{display:block;margin:14px 0;font-size:14px}input,textarea,select{display:block;width:100%;padding:10px;margin-top:7px;border:1px solid #cbd3ca;border-radius:6px;font:inherit;background:#fff;color:#26332f}input[type=color]{height:42px;padding:4px}.check{display:flex;gap:10px;align-items:center}.check input{width:auto;margin:0}.actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:20px}button{border:1px solid #cbd3ca;border-radius:7px;padding:10px 16px;background:white;color:#26332f;cursor:pointer}button.primary{background:#b44d25;color:white}button:disabled{opacity:.45;cursor:default}.error{color:#b42318}iframe{width:100%;height:650px;border:1px solid #ddd}pre{white-space:pre-wrap}
</style>
