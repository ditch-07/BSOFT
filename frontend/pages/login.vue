<script setup lang="ts">
const api = useApi();
const router = useRouter();
const route = useRoute();

const username = ref('');
const password = ref('');
const error = ref('');
const loading = ref(false);

const redirect = route.query.redirect || '/';

async function handleLogin() {
  error.value = '';
  loading.value = true;
  try {
    await api.post('/api/auth/login/', { username: username.value, password: password.value });
    await router.push(redirect);
  } catch (e: any) {
    error.value = e.data?.detail || e.data?.message || 'Login failed';
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <h1>NRZ Student Management</h1>
        <p>Sign in to continue</p>
      </div>
      
      <div v-if="error" class="alert error">{{ error }}</div>
      
      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label for="username">Username</label>
          <input
            id="username"
            v-model="username"
            type="text"
            autocomplete="username"
            required
            :disabled="loading"
            class="form-control"
          />
        </div>
        
        <div class="form-group">
          <label for="password">Password</label>
          <input
            id="password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            :disabled="loading"
            class="form-control"
          />
        </div>
        
        <button type="submit" :disabled="loading" class="btn btn-primary w-100">
          <span v-if="loading">Signing in…</span>
          <span v-else>Sign in</span>
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f3f4f6;
  padding: 1.5rem;
}
.login-card {
  width: 100%;
  max-width: 400px;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 2rem;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.08);
}
.login-header {
  text-align: center;
  margin-bottom: 1.5rem;
}
.login-header h1 {
  margin: 0 0 0.5rem;
  font-size: 1.5rem;
  color: #111827;
}
.login-header p {
  margin: 0;
  color: #6b7280;
}
.login-form {
  display: grid;
  gap: 1rem;
}
.form-group {
  display: grid;
  gap: 0.35rem;
}
.form-group label {
  font-size: 0.85rem;
  font-weight: 500;
  color: #374151;
}
.form-control {
  width: 100%;
  padding: 0.625rem 0.875rem;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 1rem;
  transition: border-color 0.15s, box-shadow 0.15s;
  box-sizing: border-box;
}
.form-control:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
}
.form-control:disabled {
  background: #f9fafb;
}
.btn {
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.95rem;
  border: none;
  cursor: pointer;
  transition: background 0.15s;
}
.btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}
.btn-primary {
  background: #2563eb;
  color: white;
}
.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}
.w-100 {
  width: 100%;
}
.alert {
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.9rem;
}
.alert.error {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
}
</style>