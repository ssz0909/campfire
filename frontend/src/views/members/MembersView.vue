<template>
  <div>
    <AppPageHeader :title="t('Members')" :subtitle="t('Manage team access and roles')">
      <template #actions>
        <n-button type="primary" @click="showInviteModal = true">
          <template #icon><PersonAddOutline /></template>
          {{ t('Invite Member') }}
        </n-button>
      </template>
    </AppPageHeader>

    <AppCard>
      <template v-if="loading">
        <AppLoader variant="table" :rows="5" />
      </template>
      <template v-else-if="members.length === 0">
        <AppEmpty
          :icon="PeopleOutline"
          :title="t('No team members')"
          :description="t('Invite colleagues to collaborate in this workspace')"
        >
          <template #action>
            <n-button type="primary" @click="showInviteModal = true">{{ t('Invite member') }}</n-button>
          </template>
        </AppEmpty>
      </template>
      <template v-else>
        <n-data-table
          :columns="columns"
          :data="members"
          :bordered="false"
        />
      </template>
    </AppCard>

    <!-- Invite modal -->
    <n-modal
      v-model:show="showInviteModal"
      preset="card"
      :title="t('Invite Team Member')"
      style="max-width: 440px"
      :mask-closable="false"
    >
      <n-form
        ref="formRef"
        :model="inviteForm"
        :rules="inviteRules"
        label-placement="top"
      >
        <n-form-item :label="t('Email address')" path="email">
          <n-input
            v-model:value="inviteForm.email"
            placeholder="colleague@company.com"
          />
        </n-form-item>
        <n-form-item :label="t('Role')" path="role">
          <n-select v-model:value="inviteForm.role" :options="roleOptions" />
        </n-form-item>
      </n-form>
      <p v-if="inviteError" class="invite-error" role="alert">{{ inviteError }}</p>
      <template #footer>
        <div class="modal-footer">
           <n-button @click="showInviteModal = false">{{ t('Cancel') }}</n-button>

          <n-button type="primary" :loading="inviteLoading" @click="handleInvite">
            {{ t('Send Invite') }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <ConfirmDialog
      v-model:show="showRemoveDialog"
      :title="t('Remove member')"
      :message="t('Remove {name} from this workspace?', { name: memberToRemove?.full_name })"
      type="error"
      :confirm-text="t('Remove')"
      :loading="removeLoading"
      @confirm="confirmRemove"
      @cancel="showRemoveDialog = false"
    />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, computed, onMounted, reactive, h } from 'vue'
import {
  NButton, NModal, NForm, NFormItem, NInput, NSelect, NDataTable,
  type DataTableColumns, type FormInst, type FormRules,
} from 'naive-ui'
import { PeopleOutline, PersonAddOutline } from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppEmpty from '@/components/common/AppEmpty.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import AppBadge from '@/components/common/AppBadge.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { useAuthStore } from '@/stores/auth'
import { membersApi } from '@/api/members'
import type { Member, Role } from '@/types/member'

const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const loading = ref(true)
const members = ref<Member[]>([])
const showInviteModal = ref(false)
const inviteLoading = ref(false)
const inviteError = ref('')
const showRemoveDialog = ref(false)
const removeLoading = ref(false)
const memberToRemove = ref<Member | null>(null)
const formRef = ref<FormInst | null>(null)

const inviteForm = reactive({ email: '', role: 'member' as Role })

const inviteRules: FormRules = {
  email: [
    { required: true, message: t('Email is required'), trigger: 'blur' },
    { type: 'email', message: t('Enter a valid email'), trigger: 'blur' },
  ],
  role: [{ required: true, message: t('Role is required'), trigger: 'change' }],
}

const roleOptions = computed(() => [
  { label: t('Admin'), value: 'admin' },
  { label: t('Member'), value: 'member' },
  { label: t('Viewer'), value: 'viewer' },
])

const roleBadge: Record<Role, string> = {
  owner: 'brand',
  admin: 'info',
  member: 'default',
  viewer: 'default',
}

const columns = computed<DataTableColumns<Member>>(() => [
  {
    title: t('Member column'),
    key: 'full_name',
    render: (row) =>
      h('div', { style: 'display:flex;align-items:center;gap:10px' }, [
        h('div', {
          style: `width:32px;height:32px;border-radius:50%;background:var(--color-brand-100);
                  color:var(--color-brand-600);font-size:13px;font-weight:700;
                  display:flex;align-items:center;justify-content:center;flex-shrink:0`,
          'aria-hidden': 'true',
        }, (row.full_name || row.email || '?').charAt(0).toUpperCase()),
        h('div', {}, [
          h('div', { style: 'font-weight:500;font-size:14px' }, row.full_name),
          h('div', { style: 'font-size:12px;color:var(--text-muted)' }, row.email),
        ]),
      ]),
  },
  {
    title: t('Role'),
    key: 'role',
    render: (row) =>
      h(AppBadge, { color: roleBadge[row.role] as unknown as 'default' }, () => t(row.role || 'Member')),
  },
  {
    title: t('Status'),
    key: 'is_active',
    render: (row) =>
      h(AppBadge, { color: row.is_active ? 'success' : 'default' }, () => t(row.is_active ? 'Active' : 'Inactive')),
  },
  {
    title: t('Joined'),
    key: 'joined_at',
    render: (row) => new Date(row.joined_at).toLocaleDateString(),
  },
  {
    title: t('Actions'),
    key: 'actions',
    render: (row) =>
      row.role !== 'owner'
        ? h(NButton, {
            size: 'small',
            type: 'error',
            ghost: true,
            onClick: () => { memberToRemove.value = row; showRemoveDialog.value = true },
          }, { default: () => t('Remove') })
        : null,
  },
])

onMounted(() => loadMembers())

async function loadMembers() {
  loading.value = true
  try {
    const res = await membersApi.list(companyId.value)
    members.value = res.data
  } catch {
    members.value = []
  } finally {
    loading.value = false
  }
}

async function handleInvite() {
  inviteError.value = ''
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  inviteLoading.value = true
  try {
    await membersApi.invite(companyId.value, inviteForm)
    showInviteModal.value = false
    inviteForm.email = ''
    inviteForm.role = 'member'
    await loadMembers()
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    inviteError.value = e?.response?.data?.detail ?? t('Failed to send invite')
  } finally {
    inviteLoading.value = false
  }
}

async function confirmRemove() {
  if (!memberToRemove.value) return
  removeLoading.value = true
  try {
    await membersApi.remove(companyId.value, memberToRemove.value.id)
    members.value = members.value.filter((m) => m.id !== memberToRemove.value!.id)
    showRemoveDialog.value = false
  } finally {
    removeLoading.value = false
    memberToRemove.value = null
  }
}
</script>

<style scoped>
.invite-error {
  font-size: var(--text-sm);
  color: var(--color-danger);
  background: oklch(93% 0.08 25);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  margin-top: var(--space-2);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}
</style>
