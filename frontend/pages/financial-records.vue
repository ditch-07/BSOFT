<script setup lang="ts">
const api = useApi();
const route = useRoute();
const router = useRouter();

const data = ref<any>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const years = ref<any[]>([]);
const selectedYearId = ref("");

async function loadYears() {
  try {
    const response = await api.get<{ results: any[] }>("/api/academic-years/");
    years.value = response.results ?? [];
    // Set default to current year
    const currentYear = years.value.find(y => y.is_current);
    if (currentYear) {
      selectedYearId.value = String(currentYear.id);
    }
  } catch (e) {
    console.error("Failed to load years:", e);
  }
}

async function loadFinancialRecords() {
  loading.value = true;
  error.value = null;
  try {
    const params = new URLSearchParams();
    if (selectedYearId.value) {
      params.set("academic_year", selectedYearId.value);
    }
    const response = await api.get<any>(`/api/financial-records/?${params.toString()}`);
    data.value = response;
  } catch (e: any) {
    error.value = e.message || "Failed to load financial records";
  } finally {
    loading.value = false;
  }
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function printReport() {
  window.print();
}

watch(selectedYearId, () => {
  loadFinancialRecords();
});

onMounted(() => {
  loadYears();
  loadFinancialRecords();
});
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Financials</p>
        <h1>Financial Records</h1>
      </div>
      <div class="d-flex gap-2">
        <button class="primary-link" @click="printReport">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5"/><path d="M18 18h2a2 2 0 0 0 2-2v-5"/><rect x="6" y="14" width="12" height="8"/></svg>
          Print Report
        </button>
        <NuxtLink to="/payments" class="secondary-link">Payment History</NuxtLink>
      </div>
    </section>

    <!-- Academic Year Filter -->
    <div class="card mb-4 print-hidden">
      <div class="card-body">
        <div class="row g-3 align-items-end">
          <div class="col-md-4">
            <label for="academic_year" class="form-label fw-semibold">Academic Year</label>
            <select
              id="academic_year"
              v-model="selectedYearId"
              class="form-select"
            >
              <option value="">All Years</option>
              <option v-for="y in years" :key="y.id" :value="y.id">
                {{ y.name }}
              </option>
            </select>
          </div>
          <div class="col-md-8">
            <span class="form-text d-block">
              <span v-if="data?.selected_year">Showing: {{ data.selected_year }}</span>
              <span v-else>Showing all academic years</span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Print-only header -->
    <div class="print-only mb-4 text-center">
      <h2 class="fw-bold mb-1">BSoft Student Management</h2>
      <h3 class="text-muted mb-2">Financial Records Report</h3>
      <p class="text-muted small">
        Generated: {{ new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}
        <span v-if="data?.selected_year"> | Filter: {{ data.selected_year }}</span>
      </p>
      <hr>
    </div>

    <div v-if="loading" class="state-card">Loading financial records…</div>
    <div v-else-if="error" class="state-card error">{{ error }}</div>
    <div v-else-if="data">
      <!-- Year Groups -->
      <div v-for="group in data.year_groups" :key="group.year" class="card mb-4">
        <div class="card-header bg-light">
          <h5 class="mb-0">{{ group.year }} - Annual Summary</h5>
        </div>
        <div class="card-body p-0">
          <div class="table-responsive">
            <table class="table table-hover mb-0">
              <thead>
                <tr>
                  <th>Semester</th>
                  <th class="text-end">Students Charged</th>
                  <th class="text-end">Charged</th>
                  <th class="text-end">Paid</th>
                  <th class="text-end">Outstanding</th>
                  <th class="text-end">Collection %</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in group.semesters" :key="s.semester.id">
                  <td>{{ s.semester.name }}</td>
                  <td class="text-end fw-bold">{{ s.students_charged }}</td>
                  <td class="text-end fw-bold">${{ formatCurrency(s.total_charged) }}</td>
                  <td class="text-end text-success fw-bold">${{ formatCurrency(s.total_paid) }}</td>
                  <td class="text-end fw-bold" :class="s.outstanding > 0 ? 'text-danger' : 'text-success'">${{ formatCurrency(s.outstanding) }}</td>
                  <td class="text-end">{{ s.collection_rate.toFixed(1) }}%</td>
                </tr>
                <!-- Year total row -->
                <tr class="table-secondary fw-bold">
                  <td>{{ group.year }} TOTAL</td>
                  <td class="text-end">—</td>
                  <td class="text-end">${{ formatCurrency(group.totals.charged) }}</td>
                  <td class="text-end text-success">${{ formatCurrency(group.totals.paid) }}</td>
                  <td class="text-end text-danger">${{ formatCurrency(group.totals.outstanding) }}</td>
                  <td class="text-end">{{ group.totals.collection_rate.toFixed(1) }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Grand totals -->
      <div class="card">
        <div class="card-header bg-dark text-white">
          <h5 class="mb-0">Grand Totals</h5>
        </div>
        <div class="card-body">
          <div class="row text-center">
            <div class="col-md-3">
              <div class="text-muted small">Total Charged</div>
              <div class="fw-bold fs-4">${{ formatCurrency(data.grand_total_charged) }}</div>
            </div>
            <div class="col-md-3">
              <div class="text-muted small">Total Paid</div>
              <div class="fw-bold fs-4 text-success">${{ formatCurrency(data.grand_total_paid) }}</div>
            </div>
            <div class="col-md-3">
              <div class="text-muted small">Total Outstanding</div>
              <div class="fw-bold fs-4 text-danger">${{ formatCurrency(data.grand_total_outstanding) }}</div>
            </div>
            <div class="col-md-3">
              <div class="text-muted small">Overall Collection</div>
              <div class="fw-bold fs-4">{{ data.grand_collection_rate.toFixed(1) }}%</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="state-card">No financial records found.</div>
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
.primary-link, .secondary-link {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  text-decoration: none;
  border-radius: 10px;
  padding: 0.7rem 1rem;
  font-weight: 600;
}
.primary-link {
  color: white;
  background: #2563eb;
}
.secondary-link {
  color: #111827;
  background: #f3f4f6;
}
.icon { width: 18px; height: 18px; }
.card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.card-header {
  padding: 1rem 1.2rem;
  border-bottom: 1px solid #e5e7eb;
  background: white;
}
.card-header.bg-light { background: #f9fafb; }
.card-header.bg-dark { background: #111827; }
.card-header h5 { margin: 0; }
.card-body { padding: 1.2rem; }
.state-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 1.2rem;
  text-align: center;
}
.error { color: #b91c1c; }
.table-responsive { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td {
  padding: 0.75rem 0.5rem;
  border-bottom: 1px solid #e5e7eb;
  text-align: left;
}
th { background: #f9fafb; font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
.table-secondary { background: #f1f3f4; }
.text-end { text-align: right; }
.text-success { color: #16a34a; }
.text-danger { color: #dc2626; }
.text-muted { color: #6b7280; }
.fw-bold { font-weight: 700; }
.fw-semibold { font-weight: 600; }
.fs-4 { font-size: 1.5rem; }
.small { font-size: 0.85rem; }
.form-label { font-weight: 600; margin-bottom: 0.4rem; display: block; }
.form-select { border: 1px solid #d1d5db; border-radius: 8px; padding: 0.6rem 0.8rem; width: 100%; }
.form-text { font-size: 0.8rem; color: #6b7280; margin-top: 0.3rem; }
.row { display: flex; flex-wrap: wrap; margin: 0 -0.5rem; }
.g-3 { gap: 1rem; }
.align-items-end { align-items: flex-end; }
.col-md-3, .col-md-4, .col-md-8 { padding: 0 0.5rem; }
.col-md-3 { flex: 0 0 25%; max-width: 25%; }
.col-md-4 { flex: 0 0 33.333%; max-width: 33.333%; }
.col-md-8 { flex: 0 0 66.667%; max-width: 66.667%; }
@media (max-width: 768px) {
  .col-md-3, .col-md-4, .col-md-8 { flex: 0 0 100%; max-width: 100%; }
}
.d-flex { display: flex; }
.justify-content-center { justify-content: center; }
.gap-2 { gap: 0.5rem; }
.print-hidden { display: block; }
.print-only { display: none; }
@media print {
  .hero, .btn, .secondary-link, .primary-link, .print-hidden, .card-header { display: none !important; }
  .page-shell { padding: 0; }
  .card { border: 1px solid #dee2e6 !important; box-shadow: none !important; page-break-inside: avoid; margin-bottom: 1rem !important; }
  .table { font-size: 0.85rem; }
  .table-secondary { background: #f8f9fa !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .bg-light { background: #f8f9fa !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .bg-dark { background: #212529 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .text-white { color: #fff !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .text-success { color: #198754 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .text-danger { color: #dc3545 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .card-body { padding: 0.5rem !important; }
  .print-only { display: block !important; }
  .table-responsive { overflow: visible; }
  .table { width: 100%; }
}
</style>