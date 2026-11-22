import { createApp } from 'vue'
import WinUIOnWeb from 'winuionweb'
import 'winuionweb/style.css'
import './styles/theme.css'
import App from './App.vue'

const app = createApp(App)
app.use(WinUIOnWeb, { locale: 'zh-CN' })
app.mount('#app')
