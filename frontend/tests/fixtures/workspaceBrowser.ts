import { createApp, defineComponent, h, ref } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import '../../src/styles.css'
import App from '../../src/App.vue'
import { fixtureApi } from './workspaceApi'
const requests=ref(0)
const api=fixtureApi(localStorage,()=>requests.value++)
// Prediction uses XHR for progress. Never let a fixture send real uploads via Vite's proxy.
const NativeXHR = window.XMLHttpRequest
window.XMLHttpRequest = class extends NativeXHR {
  override send(_body?: Document | XMLHttpRequestBodyInit | null) {
    throw new Error('Direct XHR uploads are disabled in the isolated UI fixture.')
  }
}
window.fetch=async (input,init)=>{const url=String(input);if(!url.startsWith('/api/')) throw new Error('Fixture blocks external API traffic');try{return new Response(JSON.stringify(await api(url,init)),{status:200,headers:{'Content-Type':'application/json'}})}catch{return new Response(JSON.stringify({detail:'Synthetic artifact unavailable'}),{status:404,headers:{'Content-Type':'application/json'}})}}
createApp(defineComponent({setup:()=>()=>h('div',[
  h('aside',{style:'position:fixed;bottom:0;right:0;z-index:9999;background:#fff;padding:8px;border:1px solid #ddd'},[
    h('strong','Synthetic UI test · no real API/DB · '),h('span',{'data-testid':'request-count'},String(requests.value)),
    h('button',{'data-testid':'complete-job',onClick:()=>localStorage.setItem('edgeml-test-job-status','completed')},'完成合成背景工作'),
  ]),h(App,{request:api}),
])})).use(ElementPlus).mount('#fixture')
