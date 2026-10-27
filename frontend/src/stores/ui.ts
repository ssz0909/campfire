import { defineStore } from 'pinia'
import { ref } from 'vue'

export type NotificationType = 'success' | 'error' | 'warning' | 'info'

export interface AppNotification {
  id: string
  type: NotificationType
  title: string
  message?: string
  duration?: number
}

export const useUiStore = defineStore('ui', () => {
  const sidebarCollapsed = ref(false)
  const notifications = ref<AppNotification[]>([])

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function addNotification(n: Omit<AppNotification, 'id'>) {
    const id = crypto.randomUUID()
    notifications.value.push({ ...n, id })
    const duration = n.duration ?? 4000
    if (duration > 0) {
      setTimeout(() => removeNotification(id), duration)
    }
    return id
  }

  function removeNotification(id: string) {
    const idx = notifications.value.findIndex((n) => n.id === id)
    if (idx !== -1) notifications.value.splice(idx, 1)
  }

  return {
    sidebarCollapsed,
    notifications,
    toggleSidebar,
    addNotification,
    removeNotification,
  }
})
