<template>
  <section class="geo-metrics">
    <div class="heading"><h2>GEO与主页表现</h2><div><select v-model="days" @change="load"><option :value="7">近7天</option><option :value="30">近30天</option><option :value="90">近90天</option></select> <button @click="load">刷新</button> <router-link to="/geo">主页管理 →</router-link></div></div>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="loading">加载统计…</p>
    <template v-else-if="result">
      <p>主页状态：{{ statuses[result.site?.status] || result.site?.status }} <a v-if="result.site?.url" :href="result.site.url+'?self_test=1'" target="_blank" rel="noopener">查看公开主页</a></p>
      <template v-if="result.metrics"><div class="numbers"><div v-for="s in numbers" :key="s[0]"><small>{{ s[0] }}</small><strong>{{ s[1] }}</strong></div></div>
      <p class="muted">{{ result.metrics.definition }}</p>
      <div class="columns"><div><h3>每日浏览</h3><p v-if="!views.length">所选时间内暂无浏览事件</p><div v-for="r in views" :key="r.day" class="trend"><span>{{ r.day }}</span><meter :value="r.count" :max="maxView"/><b>{{ r.count }}</b></div></div><div><h3>访问来源</h3><p v-if="!Object.keys(result.metrics.sources).length">暂无来源数据</p><p v-for="(v,k) in result.metrics.sources" :key="k">{{ k }}：{{ v }}</p></div></div>
      <p v-for="key in ['external_search','model_citations','consultations']" :key="key" class="muted">{{ result.metrics[key].message }}</p>
      <div v-if="result.metrics.external_search.items?.length" class="search-results"><h3>外部搜索表现</h3><article v-for="item in result.metrics.external_search.items" :key="item.provider"><strong>{{ item.name }}</strong><p>曝光 {{ item.impressions }} · 点击 {{ item.clicks }} · 点击率 {{ (item.ctr*100).toFixed(2) }}%<span v-if="item.average_position!=null"> · 平均排名 {{ item.average_position.toFixed(1) }}</span></p><small>数据截至 {{ item.last_data_day }} · 来源：{{ item.sources.join('；') }}</small></article></div>
      <small>时区：{{ result.metrics.timezone }} · 最近读取：{{ new Date(result.metrics.updated_at).toLocaleString() }}</small></template>
      <p v-else>尚未创建公开主页。请先到GEO配置并发布，发布后开始采集。</p>
    </template>
  </section>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import api from '@/api/client'
const props=defineProps<{companyId:string}>()
const days=ref(30),result=ref<any>(null),loading=ref(false),error=ref('')
const statuses:Record<string,string>={draft:'未发布',published:'已发布',withdrawn:'已撤回',blocked:'平台下架'}
const numbers=computed(()=>{const c=result.value?.metrics?.counts||{};return [['主页浏览',c.view||0],['逐日访客估算',result.value?.metrics?.daily_visitor_estimates||0],['联系入口点击',c.contact||0],['站内结果展示',c.search_impression||0],['站内结果点击',c.search_click||0]]})
const views=computed(()=>result.value?.metrics?.trend?.filter((r:any)=>r.kind==='view')||[])
const maxView=computed(()=>Math.max(1,...views.value.map((r:any)=>r.count)))
async function load(){loading.value=true;error.value='';try{result.value=(await api.get(`/companies/${props.companyId}/geo/metrics`,{params:{days:days.value}})).data}catch(e:any){error.value=e.response?.data?.detail||'统计加载失败'}finally{loading.value=false}}
watch(()=>props.companyId,load,{immediate:true})
</script>
<style scoped>
.geo-metrics{background:var(--color-bg-card,#fff);border:1px solid #dedfd7;border-radius:12px;padding:24px;margin-bottom:24px}.heading{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}h2{font-size:20px;margin:0}.numbers{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:16px;margin:20px 0}.numbers small{display:block;color:#68746c}.numbers strong{font-size:29px}.muted{color:#68746c;font-size:13px}.columns{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:24px}.trend{display:flex;align-items:center;gap:12px}meter{flex:1}button,select{padding:7px;border:1px solid #ccc;border-radius:5px;background:white;color:#26332f}
</style>
