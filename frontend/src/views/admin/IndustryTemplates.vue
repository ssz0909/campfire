<template>
  <section>
    <div class="template-header"><h1>行业与创作模板</h1><n-button @click="newTemplate">新增行业</n-button><n-button :loading="loading" @click="load">重新加载</n-button></div>
    <p class="note">草稿保存后不立即生效；发布后供新任务使用。已创建任务及定时计划保留原快照。通用制作规则、事实约束与权限由系统控制。</p>
    <p v-if="error" role="alert" class="error">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
    <div class="template-grid">
      <div class="template-list">
        <button v-for="row in rows" :key="row.code" :class="{active: selected?.code === row.code}" @click="edit(row)">
          <strong>{{ row.draft.name }}</strong><span>{{ row.code }} · {{ row.enabled ? '启用' : '停用' }} · {{ row.published_version ? `已发布v${row.published_version}` : '未发布' }}</span>
        </button>
      </div>
      <div class="template-editor">
        <n-form label-placement="top" @submit.prevent="save">
          <div class="identity"><n-form-item label="行业标识"><n-input v-model:value="code" :disabled="!!selected" placeholder="例如 restaurant，发布后不可修改" /></n-form-item>
          <n-form-item label="行业名称"><n-input v-model:value="form.name" :maxlength="60" /></n-form-item></div>
          <n-form-item label="行业说明"><n-input v-model:value="form.description" :maxlength="500" /></n-form-item>
          <n-form-item label="创作定位"><n-input v-model:value="form.positioning" type="textarea" :autosize="{minRows:2,maxRows:6}" :maxlength="2000" /></n-form-item>
          <n-form-item v-for="field in listFields" :key="field.key" :label="field.label + '（每行一条）'">
            <n-input v-model:value="lines[field.key]" type="textarea" :autosize="{minRows:2,maxRows:6}" />
          </n-form-item>
          <n-form-item label="发布文案语气"><n-input v-model:value="form.publish_tone" :maxlength="1000" /></n-form-item>
          <n-form-item label="发布文案要求"><n-input v-model:value="form.copy_guidance" type="textarea" :autosize="{minRows:2,maxRows:5}" :maxlength="2000" /></n-form-item>
          <div class="template-actions">
            <n-button attr-type="submit" type="primary" :loading="busy">{{ selected ? '保存草稿' : '创建行业草稿' }}</n-button>
            <n-button v-if="selected" :disabled="dirty" :loading="busy" @click="publish">发布当前草稿</n-button>
            <n-button v-if="selected && selected.code !== 'generic'" :disabled="dirty" :loading="busy" @click="toggle">{{ selected.enabled ? '停用行业' : '启用行业' }}</n-button>
          </div>
          <p v-if="selected && dirty" class="note">存在未保存修改，请先保存草稿再发布。切换行业或重新加载会丢弃未保存修改。</p>
        </n-form>
        <n-collapse style="margin-top:20px">
          <n-collapse-item title="预览：通用底座与已保存行业草稿"><pre>{{ selected?.preview || '创建草稿后可预览完整配置。' }}</pre></n-collapse-item>
          <n-collapse-item v-if="selected" title="已发布版本（只读）">
            <div v-for="v in selected.versions" :key="v.version" class="version-row"><div><h3>v{{ v.version }} · {{ new Date(v.created_at).toLocaleString() }}</h3><pre>{{ JSON.stringify(v.content, null, 2) }}</pre></div><n-button v-if="v.version!==selected.published_version" :disabled="dirty" :loading="busy" @click="restore(v.version)">以此版本恢复到草稿</n-button></div>
          </n-collapse-item>
        </n-collapse>
      </div>
    </div>
  </section>
</template>
<script setup lang="ts">
import {computed, onMounted, reactive, ref} from 'vue'
import {NButton, NForm, NFormItem, NInput, NCollapse, NCollapseItem} from 'naive-ui'
import {industryTemplatesApi as api, type IndustryTemplate, type TemplateContent} from '@/api/industryTemplates'
const rows=ref<IndustryTemplate[]>([]), selected=ref<IndustryTemplate|null>(null), code=ref(''), loading=ref(false), busy=ref(false), error=ref(''), message=ref('')
const empty=():TemplateContent=>({name:'',description:'',positioning:'根据企业实际业务与素材事实创作',themes:[],material_hints:[],terminology:[],forbidden_expressions:[],selection_keywords:[],publish_tone:'自然、具体，避免空泛宣传',copy_guidance:'围绕成片真实展示的亮点，默认引导关注或咨询'})
type ListKey='themes'|'material_hints'|'terminology'|'forbidden_expressions'|'selection_keywords'
const listFields:{key:ListKey;label:string}[]=[{key:'themes',label:'内容方向'},{key:'material_hints',label:'选材与场景规则'},{key:'terminology',label:'行业用语'},{key:'forbidden_expressions',label:'禁用表达与约束'},{key:'selection_keywords',label:'选材关键词（仅辅助排序）'}]
const form=reactive(empty()), lines=reactive<Record<ListKey,string>>({themes:'',material_hints:'',terminology:'',forbidden_expressions:'',selection_keywords:''})
function payload():TemplateContent {return {...form,...Object.fromEntries(listFields.map(f=>[f.key,lines[f.key].split('\n').map(x=>x.trim()).filter(Boolean)]))}}
const dirty=computed(()=>{if(!selected.value)return false;const current=payload();return (Object.keys(current) as (keyof TemplateContent)[]).some(k=>JSON.stringify(current[k])!==JSON.stringify(selected.value!.draft[k]))})
function edit(row:IndustryTemplate){selected.value=row;code.value=row.code;Object.assign(form,row.draft);for(const f of listFields)lines[f.key]=row.draft[f.key].join('\n');error.value=''}
function newTemplate(){selected.value=null;code.value='';Object.assign(form,empty());for(const f of listFields)lines[f.key]='';error.value='';message.value=''}
async function load(){loading.value=true;try{rows.value=(await api.list()).data;const current=rows.value.find(r=>r.code===selected.value?.code)||rows.value.find(r=>r.code==='travel')||rows.value[0];if(current)edit(current)}catch{error.value='模板加载失败，请重试。'}finally{loading.value=false}}
function accept(row:IndustryTemplate){const index=rows.value.findIndex(r=>r.code===row.code);if(index<0)rows.value.push(row);else rows.value[index]=row;edit(row)}
async function action(work:()=>Promise<{data:IndustryTemplate}>, notice:string){if(busy.value)return;busy.value=true;error.value='';message.value='';try{accept((await work()).data);message.value=notice}catch(e:any){const detail=e.response?.data?.detail;error.value=typeof detail==='string'?detail:'保存失败，请核对行业标识、必填内容及每条规则长度。'}finally{busy.value=false}}
function save(){return action(()=>selected.value?api.save(selected.value,payload()):api.create(code.value.trim(),payload()),'草稿已保存；发布后才对新任务生效。')}
function publish(){if(selected.value&&!dirty.value)return action(()=>api.publish(selected.value!),'模板已发布，新任务可使用此版本。')}
function toggle(){if(selected.value)return action(()=>api.status(selected.value!,!selected.value!.enabled),'行业状态已更新；已有任务快照保持原版本。')}
function restore(version:number){if(selected.value)return action(()=>api.restore(selected.value!,version),'已将历史版本复制到草稿；发布后新任务再使用。')}
onMounted(load)
</script>
<style scoped>
.template-header,.template-actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.template-header h1{font-size:22px;margin-right:auto}.note{font-size:13px;color:var(--text-secondary);line-height:1.8;margin:16px 0}.error{color:var(--color-danger)}.template-grid{display:grid;grid-template-columns:220px minmax(0,1fr);gap:24px;margin-top:20px}.template-list{display:flex;flex-direction:column;gap:8px}.template-list button{text-align:left;padding:12px;background:var(--surface-card);border:1px solid var(--border-default);border-radius:8px;color:var(--text-primary);cursor:pointer}.template-list button.active{border-color:var(--color-brand-500)}.template-list span{display:block;font-size:12px;margin-top:6px;color:var(--text-secondary)}.template-editor{padding:20px;border:1px solid var(--border-default);border-radius:12px;background:var(--surface-card);min-width:0}.identity{display:grid;grid-template-columns:1fr 1fr;gap:16px}.version-row{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;border-top:1px solid var(--border-default)}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;line-height:1.7}h3{margin-top:16px}@media(max-width:800px){.template-grid,.identity{grid-template-columns:1fr}.template-list{max-height:200px;overflow:auto}.template-editor{padding:12px}}
</style>
