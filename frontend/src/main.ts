import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { getLocale, i18n, setLocale } from './i18n'
import './styles/main.scss'

const pinia = createPinia()
const app = createApp(App)

app.use(pinia)
app.use(router)
app.use(i18n)
setLocale(getLocale())

app.mount('#app')
