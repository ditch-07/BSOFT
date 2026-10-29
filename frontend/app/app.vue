<template>
  <div class="app-shell">
    <NuxtRouteAnnouncer />
    <header class="topbar">
      <nav class="nav">
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
      </nav>
    </header>
    <main class="content"><NuxtPage /></main>
  </div>
</template>

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
</style>