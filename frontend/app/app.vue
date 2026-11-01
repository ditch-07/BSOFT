<template>
  <div class="app-shell">
    <NuxtRouteAnnouncer />
    <header class="topbar">
      <nav class="nav">
        <template v-if="isAuthenticated">
          <NuxtLink to="/">Dashboard</NuxtLink>
          <NuxtLink to="/students">Students</NuxtLink>
          <NuxtLink to="/payments">Payments</NuxtLink>
          <NuxtLink to="/financial-records">Financial Records</NuxtLink>
          <NuxtLink to="/reports">Reports</NuxtLink>
          <NuxtLink to="/reminders">Reminders</NuxtLink>
          <NuxtLink to="/backups">Backups</NuxtLink>
          <NuxtLink to="/audit-logs">Audit Log</NuxtLink>
          <NuxtLink to="/users">Users</NuxtLink>
          <NuxtLink to="/time-override">Time Override</NuxtLink>
          <NuxtLink to="/programs">Programs</NuxtLink>
          <NuxtLink to="/academic-years">Academic years</NuxtLink>
          <NuxtLink to="/semesters">Semesters</NuxtLink>
        </template>
        <NuxtLink v-else to="/login">Sign in</NuxtLink>
        <div v-if="isAuthenticated" class="user-actions">
          <span>{{ user?.username }}</span>
          <button type="button" @click="handleLogout">Sign out</button>
        </div>
      </nav>
      <p v-if="logoutError" class="logout-error" role="alert">{{ logoutError }}</p>
    </header>
    <main class="content"><NuxtPage /></main>
  </div>
</template>

<script setup lang="ts">
const { isAuthenticated, user, logout } = useAuth();
const router = useRouter();
const logoutError = ref('');

async function handleLogout() {
  logoutError.value = '';
  try {
    await logout();
    await router.push('/login');
  } catch (error) {
    logoutError.value = error instanceof Error ? error.message : 'Sign out failed.';
  }
}
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: #f3f4f6;
  color: #111827;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
.topbar {
  background: #111827;
  color: white;
  padding: 0.9rem 1.5rem;
}
.nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 1rem;
}
.nav a {
  color: white;
  text-decoration: none;
  font-weight: 600;
}
.content {
  max-width: 1200px;
  margin: 0 auto;
}
.user-actions {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin-left: auto;
}
.user-actions button {
  border: 1px solid rgba(255, 255, 255, 0.5);
  border-radius: 0.5rem;
  padding: 0.4rem 0.65rem;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.logout-error {
  margin: 0.75rem 0 0;
  color: #fecaca;
}
</style>