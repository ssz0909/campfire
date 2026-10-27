<template>
  <div>
    <AppPageHeader title="平台发布" subtitle="授权后，把已审批的视频或图文提交到抖音、微信视频号，并保留发布结果。" />
    <AppCard v-if="error" role="alert" class="error">{{ error }}</AppCard><AppCard v-if="notice" role="status" class="notice">{{ notice }}</AppCard>
    <AppCard><h2>发布平台</h2><div class="platforms"><div v-for="p in platforms" :key="p.platform" class="platform"><div><strong>{{ p.name }}</strong><p>{{ p.status === 'authorized' ? `已授权${p.account_name ? `：${p.account_name}` : ''}` : p.status === 'session_saved' ? '登录会话已保存（使用前校验）' : p.status === 'authorizing' ? '等待完成网页登录' : '未登录' }}</p></div><n-button :loading="opening === p.platform" :disabled="!!opening" type="primary" @click="authorize(p)">{{ ['authorized','session_saved'].includes(p.status) ? '重新打开窗口' : '打开网页登录' }}</n-button><n-button size="small" :loading="checking === p.platform" @click="checkStatus(p, true)">检查登录状态</n-button><n-tag v-if="p.status === 'authorized'" type="success">可发布</n-tag><n-tag v-if="(p.status === 'session_saved' || p.session_saved)" type="info">会话已保存</n-tag><n-button v-if="['authorized','session_saved','authorizing'].includes(p.status)" size="small" @click="logout(p)">退出 Web 登录</n-button></div></div><p class="hint">抖音与视频号可同时登录，会话按企业和平台独立保存。云端登录画面可在本页扫码操作；收起画面不会退出登录，重新打开或发布时会校验平台会话；过期后需重新扫码。点击退出 Web 登录才会清除对应平台的本地登录信息。发布前必须有已审批完成的任务、视频项目或素材。</p></AppCard>
    <AppCard v-if="loginPlatform" class="block login-panel">
      <div class="login-toolbar"><h2>{{ loginPlatform.name }} · 网页登录</h2><n-button @click="closeLoginView">收起画面</n-button><n-button :disabled="viewBusy" @click="sendLoginAction({kind:'refresh'})">刷新登录页</n-button></div>
      <p class="hint">这是云端浏览器的实时画面，请用手机扫码；需要切换登录方式时可直接点击画面，滑块验证可拖动操作。登录成功后本页会更新授权状态。收起画面不会退出平台登录。</p>
      <p v-if="viewError" role="alert" class="error">{{ viewError }} <n-button size="small" :loading="!!opening" @click="authorize(loginPlatform!)">重新打开登录页</n-button></p>
      <div v-if="loginImage" class="login-canvas">
        <img :src="loginImage" class="login-screen" alt="平台云端登录画面，点击可操作" draggable="false" @pointerdown="startLoginPointer" @pointerup="finishLoginPointer" @pointercancel="loginPointer=null" />
        <input v-if="activeField" :key="activeField.id" ref="directInput" class="login-direct-input" :style="directInputStyle" :type="activeField.type==='password'?'password':'text'" :inputmode="['tel','number'].includes(activeField.type)?'numeric':'text'" :placeholder="activeField.placeholder" :value="directText" maxlength="256" autocomplete="off" aria-label="云端登录输入框" @input="editDirectText" @compositionstart="composing=true" @compositionend="finishComposition" @blur="flushDirectText" @keydown.enter.prevent="submitDirectText" />
      </div>
      <p v-else class="hint">正在加载登录画面…</p>
      <p class="hint">输入手机号或验证码：点击画面里的输入框后，直接在出现的白色输入框中打字，文字会自动同步。下方文字栏也可作为备用。</p><div class="login-toolbar"><n-input ref="loginInput" v-model:value="loginText" type="password" show-password-on="click" placeholder="先点击画面中的输入框，再输入手机号或验证码" @keyup.enter="typeLoginText" /><n-button :disabled="viewBusy || !loginText" @click="typeLoginText">输入到登录页</n-button><n-button :disabled="viewBusy" @click="sendLoginAction({kind:'key',key:'Enter'})">回车</n-button><n-button :disabled="viewBusy" @click="sendLoginAction({kind:'scroll',delta:600})">向下滚动</n-button></div>
    </AppCard>
    <AppCard class="block" v-if="selectedPlatform"><h2>创建发布任务</h2><n-form label-placement="top" @submit.prevent="createJob"><n-form-item label="发布平台"><n-select v-model:value="selectedPlatform" :options="authorizedOptions" /></n-form-item><n-form-item label="标题"><n-input v-model:value="title" maxlength="255" /></n-form-item><n-form-item label="正文/描述"><n-input v-model:value="description" type="textarea" /></n-form-item><n-form-item label="地理位置（平台地点标签）"><n-input v-model:value="locationName" maxlength="100" placeholder="填写平台上的完整酒店地点名称" /></n-form-item><n-form-item label="媒体地址"><n-input v-model:value="mediaUrl" placeholder="填写已审批视频或图文素材地址" /></n-form-item><n-button type="primary" :disabled="!title.trim() || !mediaUrl.trim()" attr-type="submit">立即发布</n-button></n-form></AppCard>
    <AppCard class="block"><h2>发布记录</h2><div v-if="!jobs.length" class="hint">暂无发布记录</div><div v-for="j in jobs" :key="j.id" class="job"><span>{{ j.title }}</span><n-tag>{{ statusText(j.status) }}</n-tag><n-button v-if="['draft','queued','blocked','failed','manual_required','login_required'].includes(j.status) || submitting === j.id" size="small" :loading="submitting === j.id" :disabled="!!submitting" @click="submit(j)">{{ submitting === j.id ? '正在提交，请稍候' : '通过 Web 发布' }}</n-button><n-button v-if="j.status === 'published'" size="small" :disabled="!!submitting || !!republishing" :loading="republishing === j.id" @click="republish(j)">重新发布</n-button><n-button v-if="j.status === 'published'" size="small" @click="syncMetrics(j)">刷新平台数据</n-button><a v-if="j.provider_url" :href="j.provider_url" target="_blank">查看平台内容</a><small v-if="j.content_snapshot?.location_name" class="hint">地理位置：{{ j.content_snapshot.location_name }}</small><small v-if="j.error_message">{{ j.error_message }}</small><small v-if="submitting === j.id">正在上传并提交至平台，请稍候，勿重复点击。</small></div></AppCard>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'; import { useRoute } from 'vue-router'; import { NButton, NTag, NForm, NFormItem, NSelect, NInput, type InputInst } from 'naive-ui'; import AppPageHeader from '@/components/common/AppPageHeader.vue'; import AppCard from '@/components/common/AppCard.vue'; import { useAuthStore } from '@/stores/auth'; import { publishingApi, type PublishingPlatform, type PublishJob } from '@/api/publishing'
const loginPlatform=ref<PublishingPlatform|null>(null), loginImage=ref(''), loginText=ref(''), viewError=ref(''), viewBusy=ref(false);
const loginInput=ref<InputInst|null>(null);
type LoginField={id:string;type:string;placeholder:string;x:number;y:number;width:number;height:number};
const activeField=ref<LoginField|null>(null), directInput=ref<HTMLInputElement|null>(null), directText=ref(''), composing=ref(false);
const directInputStyle=computed(()=>activeField.value?{left:`${activeField.value.x/1440*100}%`,top:`${activeField.value.y/960*100}%`,width:`${activeField.value.width/1440*100}%`,height:`${activeField.value.height/960*100}%`}:{});
let directTimer:ReturnType<typeof setTimeout>|undefined;
let directDirty=false;
function editDirectText(event:Event){directText.value=(event.target as HTMLInputElement).value;directDirty=true;if(directTimer)clearTimeout(directTimer);if(!composing.value)directTimer=setTimeout(()=>{void flushDirectText()},350)}
function finishComposition(event:CompositionEvent){composing.value=false;editDirectText(event)}
async function flushDirectText(){
  if(directTimer)clearTimeout(directTimer);
  if(!directDirty||!activeField.value||composing.value)return;
  const field=activeField.value, text=directText.value;directDirty=false;
  if(!await sendLoginAction({kind:'fill',field_id:field.id,text})&&activeField.value?.id===field.id)directDirty=true;
}
async function submitDirectText(){await flushDirectText();if(!directDirty)await sendLoginAction({kind:'key',key:'Enter'})}

let viewGeneration=0;
let viewRequest:Promise<unknown>=Promise.resolve();
function closeLoginView(){if(directTimer)clearTimeout(directTimer);directDirty=false;activeField.value=null;directText.value='';viewGeneration++;loginPlatform.value=null;loginImage.value='';loginText.value='';viewError.value=''}
async function refreshLoginView(){
  if(!loginPlatform.value||viewBusy.value)return;
  await requestLoginView();
}
function requestLoginView(action?:Record<string,unknown>):Promise<boolean>{
  const p=loginPlatform.value, generation=viewGeneration;
  if(!p)return Promise.resolve(false);
  const request=viewRequest.then(async()=>{
    if(disposed||generation!==viewGeneration)return false;
    viewBusy.value=true;
    try{
      const result=action?await publishingApi.webAction(auth.currentCompanyId!,p.platform,action):await publishingApi.webView(auth.currentCompanyId!,p.platform);
      if(disposed||generation!==viewGeneration)return false;
      loginImage.value=result.image;viewError.value='';
      const field=result.input_field as LoginField|null;
      if(field?.id!==activeField.value?.id){activeField.value=field??null;directText.value='';directDirty=false}
      if(action?.kind==='click'&&field){await nextTick();directInput.value?.focus()}
      else if(action?.kind==='click'&&result.input_focused){await nextTick();loginInput.value?.focus()}
      return true;
    }catch(e:any){if(generation===viewGeneration){viewError.value=e.response?.data?.detail??'登录操作失败，请重试。';if(e.response?.status===409&&String(viewError.value).includes('窗口已关闭')){loginImage.value='';activeField.value=null}}return false}
    finally{viewBusy.value=false}
  });
  viewRequest=request;
  return request;
}
async function sendLoginAction(action:Record<string,unknown>){return requestLoginView(action)}
let loginPointer:{x:number;y:number}|null=null;
function loginCoordinates(event:PointerEvent){const rect=(event.currentTarget as HTMLImageElement).getBoundingClientRect();return {x:Math.min(1439,Math.max(0,Math.floor((event.clientX-rect.left)*1440/rect.width))),y:Math.min(959,Math.max(0,Math.floor((event.clientY-rect.top)*960/rect.height)))}}
function startLoginPointer(event:PointerEvent){loginPointer=loginCoordinates(event);(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)}
function finishLoginPointer(event:PointerEvent){if(!loginPointer)return;const start=loginPointer,end=loginCoordinates(event);loginPointer=null;void flushDirectText();void sendLoginAction(Math.hypot(end.x-start.x,end.y-start.y)>8?{kind:'drag',...start,end_x:end.x,end_y:end.y}:{kind:'click',...end})}
async function typeLoginText(){if(viewBusy.value||!loginText.value)return;const text=loginText.value;if(await sendLoginAction({kind:'text',text}) && loginText.value===text)loginText.value=''}
const submitting=ref(''), republishing=ref('');
const notice=ref(''), opening=ref(''), checking=ref(''); let pollTimer: ReturnType<typeof setInterval> | undefined; let polling=false; let disposed=false;
const route=useRoute(), auth=useAuthStore(), platforms=ref<PublishingPlatform[]>([]), jobs=ref<PublishJob[]>([]), error=ref(''), selectedPlatform=ref<string|null>(null), title=ref(String(route.query.title??'')), description=ref(String(route.query.description??'')), mediaUrl=ref(String(route.query.media_url??'')); const authorizedOptions=computed(()=>platforms.value.filter(p=>['authorized','session_saved'].includes(p.status)).map(p=>({label:p.name,value:p.platform})))
const locationName=ref(String(auth.currentCompany?.business_goals?.publish_location_name??''));
function selectAuthorized(){if(!platforms.value.some(p=>p.platform===selectedPlatform.value && ['authorized','session_saved'].includes(p.status)))selectedPlatform.value=authorizedOptions.value[0]?.value??null}
async function checkStatus(p:PublishingPlatform, manual=false){
  if(manual)checking.value=p.platform
  try{const st=await publishingApi.webStatus(auth.currentCompanyId!,p.platform);p.session_saved=st.session_saved===true||st.status==='session_saved';p.status=st.status==='authorized'?'authorized':st.status==='session_saved'?'session_saved':st.status==='login_required'?'authorizing':'disconnected';selectAuthorized();if(manual)notice.value=st.message??'尚未检测到登录成功，请在平台窗口完成扫码登录。'}
  catch(e:any){if(manual)error.value=e.response?.data?.detail??'检查登录状态失败，请重试。'}
  finally{if(manual)checking.value=''}
}
async function load(){try{platforms.value=(await publishingApi.platforms(auth.currentCompanyId!)).items;await Promise.all(platforms.value.map(p=>checkStatus(p)));jobs.value=await publishingApi.jobs(auth.currentCompanyId!);selectAuthorized()}catch{error.value='平台发布服务加载失败，请稍后重试。'}}
async function authorize(p:PublishingPlatform){opening.value=p.platform;error.value='';notice.value='正在加载云端登录页面，请稍候。';try{await publishingApi.webStart(auth.currentCompanyId!,p.platform);closeLoginView();loginPlatform.value=p;p.status='authorizing';notice.value='请在下方云端登录画面完成扫码登录。';await refreshLoginView();await checkStatus(p)}catch(e:any){notice.value='';error.value=e.response?.data?.detail??'无法打开平台登录窗口，请重试。'}finally{opening.value=''}}
async function logout(p:PublishingPlatform){try{await publishingApi.webLogout(auth.currentCompanyId!,p.platform);if(loginPlatform.value?.platform===p.platform)closeLoginView();p.status='disconnected';p.session_saved=false;selectAuthorized();notice.value='已退出平台网页登录。'}catch(e:any){error.value=e.response?.data?.detail??'退出登录失败。'}}
async function createJob(){if(!selectedPlatform.value)return;try{const j=await publishingApi.create(auth.currentCompanyId!,selectedPlatform.value,{title:title.value,description:description.value,location_name:locationName.value.trim()||undefined,media_url:mediaUrl.value,video_project_id:route.query.video_project_id,task_id:route.query.task_id,asset_ids:[],request_key:crypto.randomUUID(),media_type:'video'});jobs.value.unshift(j);await submit(j)}catch(e:any){error.value=e.response?.data?.detail??'创建发布任务失败。'}}
async function submit(j:PublishJob){
  if(submitting.value)return;
  submitting.value=j.id;error.value='';notice.value='正在上传并提交至平台，请稍候，勿重复点击。';
  try{
    Object.assign(j,await publishingApi.submit(auth.currentCompanyId!,j.id));
    if(j.status==='published')notice.value='平台已确认发布成功。';
    else{notice.value='';error.value=j.error_message||('当前发布状态：'+statusText(j.status));}
  }catch(e:any){
    notice.value='';error.value=e.response?.data?.detail??'未能确认发布结果，请先核对平台作品管理，勿重复提交。';
    try{jobs.value=await publishingApi.jobs(auth.currentCompanyId!)}catch{}
  }finally{submitting.value=''}
}
async function republish(j:PublishJob){
  if(submitting.value||republishing.value)return;
  const location=j.content_snapshot?.location_name||locationName.value.trim();
  if(!window.confirm(`将再次向平台公开发布这条视频，产生一条独立记录。${location?'地理位置：'+location+'。':''}确认重新发布？`))return;
  republishing.value=j.id;error.value='';
  try{
    const copy=await publishingApi.republish(auth.currentCompanyId!,j.id,location||undefined);
    jobs.value.unshift(copy);
    await submit(copy);
  }catch(e:any){error.value=e.response?.data?.detail??'未能创建重新发布记录，请刷新发布记录后核对。'}
  finally{republishing.value=''}
}
async function syncMetrics(j:PublishJob){try{Object.assign(j,await publishingApi.webMetrics(auth.currentCompanyId!,j.id))}catch(e:any){error.value=e.response?.data?.detail??'平台数据暂不可读取。'}}
function statusText(s:string){return({waiting_approval:'待发布审批',rejected:'发布审批退回',publishing:'正在发布',draft:'发布草稿',queued:'待 Web 发布',published:'已发布',blocked:'等待平台接口配置',manual_required:'需人工确认',failed:'发布失败',login_required:'需要重新登录'}as Record<string,string>)[s]??s}onMounted(async()=>{await load();if(disposed)return;pollTimer=setInterval(async()=>{if(polling||opening.value||submitting.value)return;polling=true;try{await Promise.all(platforms.value.filter(p=>['authorizing','authorized'].includes(p.status)).map(p=>checkStatus(p)));await refreshLoginView()}finally{polling=false}},4000)});onUnmounted(()=>{disposed=true;closeLoginView();if(pollTimer)clearInterval(pollTimer)})
</script>
<style scoped>.login-canvas{position:relative}.login-direct-input{position:absolute;box-sizing:border-box;z-index:1;min-width:0;padding:2px 8px;border:2px solid #2563eb;border-radius:4px;background:white;color:#111827;font-size:clamp(12px,1.2vw,16px);outline:none}.login-screen{display:block;width:100%;height:auto;border:1px solid var(--border-default);border-radius:8px;cursor:pointer;touch-action:none}.login-toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:10px;margin:12px 0}.login-toolbar h2{margin:0;flex:1}.login-toolbar .n-input{max-width:420px}.login-panel .hint{margin-bottom:12px}.platforms{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}.platform{display:flex;flex-wrap:wrap;gap:10px;justify-content:space-between;align-items:center;border:1px solid var(--border-default);padding:16px;border-radius:8px}.platform p,.hint{color:var(--text-secondary);font-size:13px}.block{margin-top:20px}h2{font-size:18px;margin:0 0 16px}.job{display:flex;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid var(--border-default);flex-wrap:wrap}.job small{color:var(--color-danger);width:100%}.error{color:var(--color-danger);margin-bottom:16px}.notice{margin-bottom:16px}</style>
