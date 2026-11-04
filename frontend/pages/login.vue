<script setup lang="ts">
const router = useRouter();
const route = useRoute();
const auth = useAuth();

const username = ref('');
const password = ref('');
const error = ref('');
const loading = ref(false);
const showPassword = ref(false);
const capsLockOn = ref(false);
const role = ref('admin');

const requestedRedirect = route.query.redirect;
const redirect = typeof requestedRedirect === 'string'
  && requestedRedirect.startsWith('/')
  && !requestedRedirect.startsWith('//')
  ? requestedRedirect
  : '/';

const roles = [
  { value: 'admin', name: 'Administrator', description: 'Users, backups and system settings', icon: 'M10 2.5 16 5v4.5c0 3.5-2.5 6-6 8-3.5-2-6-4.5-6-8V5z' },
  { value: 'bursar', name: 'Bursar', description: 'Payments, fees and financial reports', icon: 'M3 5.5h14v9H3zM3 8h14M6 12h3' },
  { value: 'registrar', name: 'Registrar', description: 'Student registration and records', icon: 'M8 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM2.5 16c.4-3 2.2-4.5 5.5-4.5 1.2 0 2.2.2 3 .7' },
  { value: 'viewer', name: 'Viewer', description: 'Look up records and reports, read-only', icon: 'M1.8 10S5 4.5 10 4.5 18.2 10 18.2 10 15 15.5 10 15.5 1.8 10 1.8 10z' },
];

const selectedRole = computed(() => roles.find(item => item.value === role.value)?.name || 'Administrator');

onMounted(() => {
  try {
    const savedRole = localStorage.getItem('nrz.login.role');
    if (savedRole && roles.some(item => item.value === savedRole)) {
      role.value = savedRole;
    }
  } catch (error) {
    if (!(error instanceof DOMException) || error.name !== 'SecurityError') throw error;
  }
});

watch(role, (value) => {
  try {
    localStorage.setItem('nrz.login.role', value);
  } catch (error) {
    if (!(error instanceof DOMException) || !['SecurityError', 'QuotaExceededError'].includes(error.name)) {
      throw error;
    }
  }
});

function updateCapsLock(event: KeyboardEvent) {
  capsLockOn.value = event.getModifierState('CapsLock');
}

async function handleLogin() {
  error.value = '';
  loading.value = true;
  try {
    await auth.login(username.value.trim(), password.value);
    await router.push(redirect);
  } catch (e: any) {
    const detail = e.data?.errors?.detail;
    error.value = (Array.isArray(detail) ? detail[0] : detail)
      || e.data?.detail
      || e.data?.message
      || 'Sign in failed. Check your username and password, then try again.';
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="lg">
    <section class="lg-brand">
      <img class="lg-art" :src="'/static/img/login-illustration.svg'" alt="" aria-hidden="true">
      <NuxtLink class="lg-lockup" to="/" aria-label="BSoft Student Management">
        <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
          <path d="M3 22C8 22 8 12 14 12C20 12 19 21 29 21" stroke="#8AD4CE" stroke-width="1.7" stroke-linecap="round" />
          <path d="M3 26C10 26 11 17 17 17C22 17 23 25 29 25" stroke="#DDF4F1" stroke-width="1.4" stroke-linecap="round" />
          <path d="M4 17C8 17 9 7 15 7C21 7 22 16 28 16" stroke="#55B7BB" stroke-width="1.2" stroke-linecap="round" />
        </svg>
        <span class="lg-lockup-name">BSoft</span>
        <span class="lg-lockup-product">Student Management</span>
      </NuxtLink>
      <div class="lg-copy">
        <h1 class="lg-headline">A clearer view of every student journey.</h1>
        <ul class="lg-points">
          <li><span class="lg-dot" aria-hidden="true" /><div><strong>Student records</strong><span>Keep enrolment and contact details together.</span></div></li>
          <li><span class="lg-dot" aria-hidden="true" /><div><strong>Fees and payments</strong><span>Follow charges, receipts and outstanding balances.</span></div></li>
          <li><span class="lg-dot" aria-hidden="true" /><div><strong>Reports that help</strong><span>Understand activity across semesters and programmes.</span></div></li>
        </ul>
      </div>
      <p class="lg-brand-foot">A focused workspace for student administration.</p>
    </section>

    <main class="lg-main">
      <div class="lg-wrap">
        <section class="ui-card lg-card">
          <h2 class="lg-title">Welcome back</h2>
          <p class="lg-sub">Sign in to continue to BSoft Student Management.</p>

          <div v-if="error" class="ui-banner lg-alert" role="alert">
            <span class="ui-lamp ui-lamp--red" aria-hidden="true" />
            <div><strong>Unable to sign in</strong>{{ error }}</div>
          </div>

          <form class="lg-form" @submit.prevent="handleLogin">
            <fieldset class="lg-roles">
              <legend>Choose your workspace</legend>
              <div class="lg-role-grid">
                <label v-for="item in roles" :key="item.value" class="lg-role">
                  <input v-model="role" type="radio" name="role" :value="item.value" :disabled="loading">
                  <span class="lg-role-card">
                    <svg class="lg-role-icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                      <path :d="item.icon" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                    <span class="lg-role-text"><strong>{{ item.name }}</strong><span>{{ item.description }}</span></span>
                    <span class="lg-role-check" aria-hidden="true" />
                  </span>
                </label>
              </div>
              <p class="lg-role-note">Available features depend on the permissions assigned to your account.</p>
            </fieldset>

            <div class="lg-field">
              <label for="username">Username</label>
              <input
                id="username"
                v-model="username"
                class="lg-input"
                type="text"
                autocomplete="username"
                autocapitalize="none"
                spellcheck="false"
                required
                autofocus
                :disabled="loading"
              >
            </div>

            <div class="lg-field">
              <label for="password">Password</label>
              <div class="lg-pw">
                <input
                  id="password"
                  v-model="password"
                  class="lg-input"
                  :type="showPassword ? 'text' : 'password'"
                  autocomplete="current-password"
                  required
                  :disabled="loading"
                  @keydown="updateCapsLock"
                  @keyup="updateCapsLock"
                >
                <button class="lg-toggle" type="button" :aria-pressed="showPassword" @click="showPassword = !showPassword">
                  {{ showPassword ? 'Hide' : 'Show' }}
                </button>
              </div>
            </div>
            <p v-if="capsLockOn" class="lg-caps" role="status">
              <span class="ui-lamp ui-lamp--amber" aria-hidden="true" /> Caps Lock is on
            </p>

            <button type="submit" class="ui-btn ui-btn--solid lg-submit" :disabled="loading">
              {{ loading ? 'Signing in…' : `Sign in as ${selectedRole}` }}
            </button>
          </form>

          <p class="lg-help">Forgot your password? Ask your administrator to reset it.</p>
        </section>
        <p class="lg-foot">BSoft Student Management System</p>
      </div>
    </main>
  </div>
</template>

<style scoped>
.lg {
  display: grid;
  grid-template-columns: minmax(360px, 42%) minmax(0, 1fr);
  min-height: 100vh;
  min-height: 100dvh;
}
.lg h1, .lg h2, .lg p, .lg fieldset { margin: 0; }
.lg-brand {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 640px;
  padding: 2rem clamp(1.5rem, 4vw, 3rem);
  color: #fff;
  background: radial-gradient(520px 320px at 78% 24%, rgb(85 183 187 / 22%), transparent 70%), linear-gradient(180deg, #0b2238, #0e2b45 55%, #0b2238);
}
.lg-art {
  position: absolute;
  inset: auto 0 0;
  z-index: -1;
  width: 100%;
  max-height: 48%;
  opacity: .8;
  pointer-events: none;
}
.lg-lockup { display: inline-flex; align-items: center; gap: .55rem; color: #fff; text-decoration: none; }
.lg-lockup svg { width: 34px; height: 34px; }
.lg-lockup-name { color: #fff; font-size: 1.25rem; font-weight: 800; }
.lg-lockup-product { color: #d6e5ea; font-size: .82rem; }
.lg-copy { max-width: 31rem; margin-top: clamp(2.5rem, 10vh, 6rem); }
.lg-headline { color: #fff; font-size: clamp(1.8rem, 1.2rem + 1.6vw, 2.5rem); font-weight: 800; line-height: 1.12; }
.lg-points { display: grid; gap: 1rem; margin-top: 1.8rem !important; padding: 0; list-style: none; }
.lg-points li { display: grid; grid-template-columns: auto 1fr; gap: .7rem; }
.lg-dot { width: 8px; height: 8px; margin-top: .42rem; border-radius: 50%; background: #8ad4ce; box-shadow: 0 0 0 3px rgb(138 212 206 / 22%); }
.lg-points strong, .lg-points li div > span { display: block; }
.lg-points strong { color: #fff; font-size: .92rem; }
.lg-points li div > span { margin-top: .15rem; color: #d6e5ea; font-size: .8rem; }
.lg-brand-foot { margin-top: auto !important; padding-top: 2rem; color: #c9dce2; font-size: .75rem; }
.lg-main { display: grid; place-items: center; padding: 2rem 1.25rem; }
.lg-wrap { width: 100%; max-width: 480px; }
.lg-card { padding: clamp(1.2rem, 4vw, 2rem); }
.lg-title { color: var(--ink); font-size: clamp(1.5rem, 1.2rem + 1vw, 2rem); font-weight: 800; line-height: 1.15; }
.lg-sub { margin-top: .4rem !important; color: var(--ink-2); font-size: .82rem; }
.lg-alert { margin-top: 1rem; align-items: flex-start; }
.lg-form { margin-top: 1.25rem; }
.lg-roles { min-width: 0; margin-bottom: 1.2rem; padding: 0; border: 0; }
.lg-roles legend { margin-bottom: .45rem; color: var(--ink-2); font-size: .75rem; font-weight: 650; }
.lg-role-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .55rem; }
.lg-role { position: relative; display: block; min-width: 0; }
.lg-role input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: pointer; }
.lg-role-card { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: .15rem .55rem; align-items: start; height: 100%; min-height: 58px; padding: .6rem; border: 1px solid #aeb7bc; border-radius: 8px; background: var(--paper); }
.lg-role input:checked + .lg-role-card { border-color: var(--rail); background: var(--rail-soft); box-shadow: inset 0 0 0 1px var(--rail); }
.lg-role input:focus-visible + .lg-role-card { outline: 3px solid var(--rail); outline-offset: 2px; }
.lg-role-icon { width: 19px; height: 19px; color: var(--rail); }
.lg-role-text { min-width: 0; }
.lg-role-text strong, .lg-role-text span { display: block; }
.lg-role-text strong { font-size: .76rem; }
.lg-role-text span { margin-top: .1rem; color: var(--ink-2); font-size: .64rem; line-height: 1.3; }
.lg-role-check { width: 14px; height: 14px; margin-top: .1rem; border: 1.5px solid var(--grey); border-radius: 50%; background: var(--paper); }
.lg-role input:checked + .lg-role-card .lg-role-check { border-color: var(--rail); background: var(--rail); box-shadow: inset 0 0 0 3px #fff; }
.lg-role-note { margin-top: .5rem !important; color: var(--ink-2); font-size: .68rem; }
.lg-field { margin-bottom: 1rem; }
.lg-field label { display: block; margin-bottom: .3rem; color: var(--ink-2); font-size: .75rem; font-weight: 650; }
.lg-input { display: block; width: 100%; min-height: 46px; padding: .6rem .8rem; border: 1px solid var(--grey); border-radius: 7px; background: var(--paper); color: var(--ink); font-size: .9375rem; }
.lg-input:focus-visible { border-color: var(--rail); outline: 3px solid var(--rail); outline-offset: 2px; }
.lg-pw { position: relative; }
.lg-pw .lg-input { padding-right: 4.25rem; }
.lg-toggle { position: absolute; top: 50%; right: .35rem; min-height: 36px; padding: 0 .65rem; transform: translateY(-50%); border: 0; border-radius: 6px; background: transparent; color: var(--rail); font-size: .8rem; font-weight: 650; cursor: pointer; }
.lg-toggle:hover { background: var(--rail-soft); }
.lg-caps { display: flex; align-items: center; gap: .5rem; margin: -.35rem 0 1rem !important; color: var(--ink-2); font-size: .75rem; }
.lg-submit { width: 100%; min-height: 48px; margin-top: .25rem; }
.lg-submit:disabled { opacity: .75; cursor: progress; }
.lg-help { margin-top: 1.1rem !important; color: var(--ink-2); font-size: .78rem; text-align: center; }
.lg-foot { margin-top: 1rem !important; color: var(--ink-2); font-size: .72rem; text-align: center; }
@media (max-width: 850px) {
  .lg { grid-template-columns: minmax(280px, 38%) minmax(0, 1fr); }
  .lg-brand { padding-inline: 1.35rem; }
  .lg-role-grid { grid-template-columns: 1fr; }
}
@media (max-width: 650px) {
  .lg { grid-template-columns: 1fr; }
  .lg-brand { min-height: 220px; padding: 1.25rem 1.5rem; }
  .lg-copy { margin-top: 1.5rem; }
  .lg-headline { font-size: 1.55rem; }
  .lg-points { display: none; }
  .lg-brand-foot { display: none; }
  .lg-main { padding: 1.25rem .9rem; }
  .lg-role-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
