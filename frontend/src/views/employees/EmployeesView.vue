<template>
  <div>
    <AppPageHeader :title="t('Digital Employees')" :subtitle="t('Five default employees are ready. Add extra employees when needed.')">
      <template #actions>
        <n-button type="primary" @click="showCreateModal = true">
          <template #icon><AddOutline /></template>
          {{ t('Add Extra Employee') }}
        </n-button>
      </template>
    </AppPageHeader>

    <template v-if="loading">
      <div class="employees-grid">
        <AppCard v-for="i in 6" :key="i">
          <AppLoader variant="card" />
        </AppCard>
      </div>
    </template>

    <template v-else-if="employees.length === 0">
      <AppEmpty
        :icon="PeopleOutline"
        :title="t('No digital employees yet')"
        :description="t('Create your first AI employee to start automating tasks')"
      >
        <template #action>
          <n-button type="primary" @click="showCreateModal = true">
            {{ t('Create employee') }}
          </n-button>
        </template>
      </AppEmpty>
    </template>

    <template v-else>
      <div class="employees-grid">
        <AppCard
          v-for="emp in employees"
          :key="emp.id"
          hoverable
          @click="router.push(`/employees/${emp.id}`)"
        >
          <div class="emp-card">
            <div class="emp-card__header">
              <div class="emp-card__avatar">
                {{ emp.name.charAt(0).toUpperCase() }}
              </div>
              <AppBadge :color="emp.is_active ? 'success' : 'default'" dot>{{ t(emp.is_active ? 'Active' : 'Inactive') }}</AppBadge>
            </div>
            <h3 class="emp-card__name">{{ emp.name }}</h3>
            <p class="emp-card__role">{{ t(emp.role) }}</p>
            <p v-if="emp.description" class="emp-card__desc">{{ emp.description }}</p>
            <p v-if="emp.last_run_at" class="emp-card__last-run">
              {{ t('Last run {date}', { date: new Date(emp.last_run_at).toLocaleDateString(locale) }) }}
            </p>
          </div>
        </AppCard>
      </div>
    </template>

    <CreateEmployeeModal
      v-model:show="showCreateModal"
      @created="onEmployeeCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NButton } from 'naive-ui'
import { AddOutline, PeopleOutline } from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppEmpty from '@/components/common/AppEmpty.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import AppBadge from '@/components/common/AppBadge.vue'
import CreateEmployeeModal from './CreateEmployeeModal.vue'
import { useAuthStore } from '@/stores/auth'
import { digitalEmployeesApi } from '@/api/digitalEmployees'
import type { DigitalEmployee } from '@/types/digitalEmployee'

const { t, locale } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const loading = ref(true)
const employees = ref<DigitalEmployee[]>([])
const showCreateModal = ref(false)

onMounted(() => loadEmployees())

async function loadEmployees() {
  loading.value = true
  try {
    const res = await digitalEmployeesApi.list(companyId.value)
    employees.value = res.data
  } catch {
    employees.value = []
  } finally {
    loading.value = false
  }
}

async function onEmployeeCreated() {
  showCreateModal.value = false
  await loadEmployees()
}
</script>

<style scoped>
.employees-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
}

.emp-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.emp-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}

.emp-card__avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--color-brand-100);
  color: var(--color-brand-600);
  font-size: var(--text-xl);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.emp-card__name {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
}

.emp-card__role {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  text-transform: capitalize;
}

.emp-card__desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.emp-card__stats {
  display: flex;
  gap: var(--space-6);
  margin-top: var(--space-2);
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-default);
}

.emp-card__stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.emp-card__stat-value {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.emp-card__stat-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.emp-card__last-run {
  font-size: var(--text-xs);
  color: var(--text-muted);
}
</style>
