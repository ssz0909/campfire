import {computed, onMounted, ref} from 'vue'
import {industryTemplatesApi, type IndustryOption} from '@/api/industryTemplates'

export function useIndustryCatalog() {
  const industries = ref<IndustryOption[]>([]), industryError = ref(''), industriesLoading = ref(false)
  async function loadIndustries() {
    industriesLoading.value = true; industryError.value = ''
    try { industries.value = (await industryTemplatesApi.catalog()).data }
    catch { industryError.value = '行业模板列表加载失败；未指定行业时使用通用模板。请刷新重试。' }
    finally { industriesLoading.value = false }
  }
  const industryOptions = computed(() => industries.value.map(i => ({label: i.name, value: i.code})))
  onMounted(loadIndustries)
  return {industries, industryOptions, industryError, industriesLoading, loadIndustries}
}
