import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './AuthenticatedApp.vue'
import './styles.css'

createApp(App).use(ElementPlus).mount('#app')

