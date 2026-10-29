<script setup lang="ts">
const api = useApi();
const { data, pending, error } = await useAsyncData('dashboard', () => api.get<{
  total_students: number;
  today_total: number;
  current_semester: string | null;
  financials: {
    charged: number;
    paid: number;
    outstanding: number;
    collection_rate: number;
  };
}>('/api/dashboard/'));
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Student management</p>
        <h1>NRZ dashboard</h1>
      </div>
      <NuxtLink to="/students" class="primary-link">Open students</NuxtLink>
    </section>

    <div v-if="pending" class="state-card">Loading dashboard…</div>
    <div v-else-if="error" class="state-card error">Unable to load dashboard. {{ error.message }}</div>

    <div v-else class="stats-grid">
      <div class="stat-card">
        <span class="label">Active students</span>
        <strong>{{ data?.total_students ?? 0 }}</strong>
      </div>
      <div class="stat-card">
        <span class="label">Today collections</span>
        <strong>{{ (data?.today_total ?? 0).toFixed(2) }}</strong>
      </div>
      <div class="stat-card">
        <span class="label">Current semester</span>
        <strong>{{ data?.current_semester ?? 'Not configured' }}</strong>
      </div>
      <div class="stat-card">
        <span class="label">Collection rate</span>
        <strong>{{ ((data?.financials?.collection_rate ?? 0) * 100).toFixed(1) }}%</strong>
      </div>
    </div>

    <div v-if="data" class="info-panel">
      <h2>Financial overview</h2>
      <ul>
        <li>Charged: {{ (data.financials?.charged ?? 0).toFixed(2) }}</li>
        <li>Paid: {{ (data.financials?.paid ?? 0).toFixed(2) }}</li>
        <li>Outstanding: {{ (data.financials?.outstanding ?? 0).toFixed(2) }}</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.page-shell {
  display: grid;
  gap: 1.25rem;
  padding: 1.5rem;
}
.hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  background: #111827;
  color: white;
  border-radius: 16px;
  padding: 1.5rem 2rem;
}
.eyebrow {
  margin: 0 0 0.4rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 0.7rem;
  opacity: 0.8;
}
.hero h1 {
  margin: 0;
  font-size: clamp(1.8rem, 3vw, 2.8rem);
}
.primary-link {
  color: white;
  background: #2563eb;
  text-decoration: none;
  border-radius: 10px;
  padding: 0.75rem 1rem;
  font-weight: 600;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
}
.stat-card,
.info-panel,
.state-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 1.2rem;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.label {
  display: block;
  color: #6b7280;
  font-size: 0.78rem;
  margin-bottom: 0.55rem;
}
.stat-card strong {
  font-size: 1.6rem;
}
.error {
  color: #b91c1c;
}
.info-panel ul {
  margin: 0.5rem 0 0;
  padding-left: 1.25rem;
}
</style>
