<template>
  <n-modal :show="show" preset="card" title="登录订单来了并选择门店" style="max-width: 460px"
    :mask-closable="!loading" :closable="!loading" @update:show="v => !v && close()">
    <n-form v-if="!stores.length" label-placement="top" @submit.prevent="submit">
      <n-form-item label="手机号"><n-input v-model:value="form.phone" autocomplete="username" :disabled="loading" /></n-form-item>
      <n-form-item label="密码"><n-input v-model:value="form.password" type="password" autocomplete="current-password" :disabled="loading" /></n-form-item>
      <n-form-item v-if="verificationRequired" label="设备验证短信验证码">
        <n-input v-model:value="form.sms" maxlength="6" :disabled="loading" />
      </n-form-item>
      <p v-if="verificationRequired">请按订单来了的设备验证要求输入收到的验证码；如未收到，请先在官网完成验证。</p>
      <n-button type="primary" attr-type="submit" :loading="loading">登录</n-button>
    </n-form>
    <template v-else>
      <n-form-item label="选择账号有权限的门店">
        <n-select v-model:value="selected" :options="stores.map(s => ({label: `${s.name || s.ntw_num}（${s.ntw_num}）`, value: s.id}))" />
      </n-form-item>
      <n-button type="primary" :disabled="!selected" :loading="loading" @click="bind">连接所选门店</n-button>
    </template>
    <p v-if="error" class="notice notice--fail" role="alert">{{ error }}</p>
    <p class="muted" style="margin-top: 16px">密码仅由后端用于登录，不保存密码；会话加密保存在服务端，用于读取所选门店数据。</p>
  </n-modal>
</template>
<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { NModal, NForm, NFormItem, NInput, NButton, NSelect } from 'naive-ui'
import { connectorsApi, type DddStore } from '@/api/connectors'
const props = defineProps<{show: boolean; companyId: string}>()
const emit = defineEmits<{close: []; success: []}>()
const form = reactive({phone: '', password: '', sms: ''})
const stores = ref<DddStore[]>([])
const selected = ref<string | null>(null)
const verificationRequired = ref(false)
const loading = ref(false)
const error = ref('')
function reset() {form.password = ''; form.sms = ''; stores.value = []; selected.value = null; error.value = ''; verificationRequired.value = false}
function close() {reset(); emit('close')}
watch(() => [props.show, props.companyId], () => {if (!props.show) reset()})
function message(err: any) {const d = err?.response?.data?.detail; return typeof d === 'string' ? d : d?.message || '连接失败，请检查账号或在官网完成验证'}
async function submit() {
  if (loading.value) return
  if (!/^(?:\+86)?1\d{10}$/.test(form.phone.trim()) || !form.password) {error.value = '请输入有效手机号和密码'; return}
  loading.value = true; error.value = ''
  try {
    const {data} = await connectorsApi.dddLogin(props.companyId, {phone: form.phone.trim(), password: form.password, sms_captcha: form.sms})
    verificationRequired.value = data.verification_required
    stores.value = data.stores
    if (!verificationRequired.value) form.password = ''
    if (stores.value.length === 1) selected.value = stores.value[0]!.id
    if (!stores.value.length && !data.verification_required) error.value = '此账号没有可访问的门店'
  } catch(err) {error.value = message(err)} finally {loading.value = false}
}
async function bind() {
  if (!selected.value || loading.value) return
  loading.value = true; error.value = ''
  try {await connectorsApi.dddSelectStore(props.companyId, selected.value); reset(); emit('success')}
  catch(err) {error.value = message(err)} finally {loading.value = false}
}
</script>
