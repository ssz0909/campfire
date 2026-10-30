<template>
  <div class="music-picker">
    <n-select :value="musicAssetId" :options="options" clearable filterable placeholder="保留模型音轨，或选择上传的音乐"
      @update:value="emit('update:musicAssetId', $event)" />
    <label>上传背景音乐（MP3 / WAV）<input type="file" accept=".mp3,.wav,audio/mpeg,audio/wav" :disabled="uploading" @change="upload" /></label>
    <p v-if="error" role="alert">{{ error }}</p>
    <template v-if="musicAssetId">
      <audio v-if="selected?.file_url" :src="selected.file_url" controls preload="none" />
      <label>音乐音量 {{ Math.round(musicVolume*100) }}%
        <n-slider :value="Math.round(musicVolume*100)" :min="0" :max="100" @update:value="emit('update:musicVolume',$event/100)" />
      </label>
      <p>使用所选音乐替换全部模型音轨；自动跳过开头静音，再循环或截取至成片时长，首尾淡入淡出。请使用有权发布的音乐。</p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed,onMounted,ref } from 'vue'
import { NSelect,NSlider } from 'naive-ui'
import { assetsApi } from '@/api/assets'
import type { Asset } from '@/types/asset'
const props=defineProps<{companyId:string;musicAssetId:string|null;musicVolume:number}>()
const emit=defineEmits<{ 'update:musicAssetId':[value:string|null]; 'update:musicVolume':[value:number] }>()
const assets=ref<Asset[]>([]),uploading=ref(false),error=ref('')
const options=computed(()=>assets.value.map(a=>({label:a.name,value:a.id})))
const selected=computed(()=>assets.value.find(a=>a.id===props.musicAssetId))
onMounted(async()=>{
  try { assets.value=(await assetsApi.list(props.companyId,{type:'audio',limit:100})).data.filter(a=>a.processing_status==='ready') }
  catch { error.value='音乐列表加载失败，可刷新后重试' }
})
async function upload(event:Event) {
  const input=event.target as HTMLInputElement
  const file=input.files?.[0];if(!file)return
  uploading.value=true;error.value=''
  try {
    const asset=(await assetsApi.upload(props.companyId,{file})).data
    if(asset.processing_status!=='ready'){throw new Error('音频尚未处理完成，请稍后刷新音乐列表')}
    assets.value=[asset,...assets.value]
    emit('update:musicAssetId',asset.id)
  } catch(e:any) { error.value=e.response?.data?.detail||e.message||'音乐上传失败' }
  finally {uploading.value=false;input.value=''}
}
</script>
<style scoped>
.music-picker { display:grid;gap:12px;min-width:0 }
label { display:grid;gap:8px }
audio { width:100%;max-width:420px }
p { font-size:13px;color:var(--text-secondary);line-height:1.6 }
</style>
