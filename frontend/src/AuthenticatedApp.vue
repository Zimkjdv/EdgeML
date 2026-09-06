<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import App from './App.vue'
import { locale, toggleLocale } from './i18n'
import { setCsrf } from './webAuth'

const en = computed(() => locale.value === 'en')
const ready = ref(false), allowed = ref(false), configured = ref(false), busy = ref(false)
const username = ref('admin'), password = ref(''), error = ref('')
async function check() {
  ready.value = false
  try {
    const response = await fetch('/api/auth/session', { credentials: 'same-origin', cache: 'no-store' })
    if (!response.ok) throw new Error(en.value ? 'Unable to check login status.' : '無法取得登入狀態。')
    const data = await response.json()
    configured.value = data.configured
    allowed.value = !data.required || data.authenticated
    setCsrf(data.csrf_token)
    error.value = ''
  } catch (e) { allowed.value = false; error.value = e instanceof Error ? e.message : String(e) }
  finally { ready.value = true }
}
function expired() { allowed.value = false; password.value = ''; setCsrf(null); void check() }
async function login() {
  busy.value = true; error.value = ''
  try {
    const response = await fetch('/api/auth/session', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-EdgeML-Login': '1' }, body: JSON.stringify({ username: username.value, password: password.value }) })
    if (!response.ok) {
      const messages: Record<number, string> = { 401: en.value ? 'Incorrect username or password.' : '帳號或密碼不正確。', 429: en.value ? 'Too many attempts. Wait five minutes.' : '嘗試次數過多，請五分鐘後再試。' }
      throw new Error(messages[response.status] || (en.value ? 'Login failed. Check server configuration.' : '登入失敗，請確認伺服器設定。'))
    }
    setCsrf((await response.json()).csrf_token)
    password.value = ''; allowed.value = true
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}
onMounted(() => { window.addEventListener('edgeml-session-expired', expired); void check() })
onUnmounted(() => window.removeEventListener('edgeml-session-expired', expired))
</script>

<template>
  <App v-if="ready && allowed" />
  <div v-else class="login-screen">
    <section class="login-panel" aria-labelledby="login-title">
      <div class="login-heading"><strong>EdgeML</strong><button @click="toggleLocale">{{ en ? '繁中' : 'English' }}</button></div>
      <h1 id="login-title">{{ en ? 'Sign in to your workspace' : '登入工作平台' }}</h1>
      <p>{{ en ? 'Use your workspace administrator account.' : '使用工作平台管理員帳號登入。' }}</p>
      <p v-if="!ready" role="status">{{ en ? 'Checking session…' : '正在確認登入狀態…' }}</p>
      <form v-else-if="configured" @submit.prevent="login">
        <label for="web-username">{{ en ? 'Username' : '帳號' }}</label>
        <input id="web-username" v-model="username" autocomplete="username" maxlength="128" required />
        <label for="web-password">{{ en ? 'Password' : '密碼' }}</label>
        <input id="web-password" v-model="password" type="password" autocomplete="current-password" maxlength="1024" required />
        <button class="login-submit" :disabled="busy">{{ busy ? (en ? 'Signing in…' : '登入中…') : (en ? 'Sign in' : '登入') }}</button>
      </form>
      <p v-else-if="!error">{{ en ? 'Web login has not been configured. Ask the administrator to set EDGEML_WEB_PASSWORD in the server .env and restart the backend.' : '尚未設定網頁登入。請管理員在伺服器 .env 設定 EDGEML_WEB_PASSWORD，並重新啟動後端。' }}</p>
      <p v-if="error" class="login-error" role="alert">{{ error }}</p>
      <button v-if="ready && !configured" @click="check">{{ en ? 'Retry' : '重新檢查' }}</button>
    </section>
  </div>
</template>

<style scoped>
.login-screen {min-height:100vh;display:grid;place-items:center;padding:24px;background:#f3f7fc}.login-panel {width:min(100%,430px);padding:32px;border:1px solid #dbe6f4;border-radius:20px;background:white;box-shadow:0 12px 36px #244d8010}.login-heading {display:flex;justify-content:space-between;align-items:center;color:#215caa}.login-heading strong {font-size:24px}h1 {font-size:24px;margin-top:28px;letter-spacing:0}p {color:#62758b;line-height:1.6}label {display:block;margin:18px 0 8px;color:#344c68}input {box-sizing:border-box;width:100%;padding:12px;border:1px solid #cbd9eb;border-radius:8px;font:inherit}button {cursor:pointer;font:inherit;border:1px solid #cfdded;background:#f5f9ff;color:#235eaa;border-radius:8px;padding:8px 12px}.login-submit {margin-top:24px;width:100%;padding:12px;background:#286dcd;color:white}.login-submit:disabled {opacity:.6}.login-error {color:#bd3434}input:focus-visible,button:focus-visible {outline:2px solid #3985e4;outline-offset:2px}
</style>
