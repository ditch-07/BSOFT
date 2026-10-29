<script setup lang="ts">
const api = useApi();

const { data, pending, error } = await useAsyncData('reports-index', () => api.get<{
  reports: Array<{ slug: string; name: string; view: string; desc: string }>;
}>('/api/reports/'));

const formatRoute = (view: string): string => {
  const routeMap: Record<string, string> = {
    'financial_records': '/financial-records',
    'enrollment_report': '/reports/enrollment',
    'outstanding_report': '/reports/outstanding',
    'fee_audit_report': '/reports/fee-audit',
    'payment_methods_report': '/reports/payment-methods',
    'program_revenue_report': '/reports/program-revenue',
    'daily_collections_report': '/reports/daily-collections',
    'status_history_report': '/reports/status-history',
  };
  return routeMap[view] || `/reports/${view}`;
};
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Analytics</p>
        <h1>Reports</h1>
      </div>
    </section>

    <div v-if="pending" class="state-card">Loading reports…</div>
    <div v-else-if="error" class="state-card error">Unable to load reports. {{ error.message }}</div>
    <div v-else>
      <div class="row g-3">
        <div v-for="r in data?.reports ?? []" :key="r.slug" class="col-12 col-md-6 col-lg-4">
          <NuxtLink :to="formatRoute(r.view)" class="text-decoration-none">
            <div class="card border-0 shadow-sm report-card h-100">
              <div class="card-body">
                <h5 class="fw-bold mb-2">{{ r.name }}</h5>
                <p class="text-muted small mb-3">{{ r.desc }}</p>
                <span class="btn btn-sm btn-outline-primary">View Report →</span>
              </div>
            </div>
          </NuxtLink>
        </div>
      </div>
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
.card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.card-body {
  padding: 1.2rem;
}
.state-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 1.2rem;
  text-align: center;
}
.error {
  color: #b91c1c;
}
.report-card {
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.report-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}
.row {
  display: flex;
  flex-wrap: wrap;
  margin: 0 -0.5rem;
}
.g-3 {
  gap: 1rem;
}
.col-12, .col-md-6, .col-lg-4 {
  padding: 0 0.5rem;
}
.col-12 { flex: 0 0 100%; max-width: 100%; }
.col-md-6 { flex: 0 0 50%; max-width: 50%; }
.col-lg-4 { flex: 0 0 33.333%; max-width: 33.333%; }
@media (max-width: 992px) {
  .col-lg-4 { flex: 0 0 50%; max-width: 50%; }
}
@media (max-width: 768px) {
  .col-md-6, .col-lg-4 { flex: 0 0 100%; max-width: 100%; }
}
.btn {
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  text-decoration: none;
  display: inline-block;
}
.btn-sm {
  padding: 0.4rem 0.8rem;
  font-size: 0.85rem;
}
.btn-outline-primary {
  background: transparent;
  border: 1px solid #2563eb;
  color: #2563eb;
}
.text-decoration-none { text-decoration: none; }
.fw-bold { font-weight: 700; }
.mb-2 { margin-bottom: 0.5rem; }
.mb-3 { margin-bottom: 1rem; }
.text-muted { color: #6b7280; }
.small { font-size: 0.85rem; }
.h-100 { height: 100%; }
</style>