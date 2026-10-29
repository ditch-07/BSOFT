<script setup lang="ts">
const api = useApi();
const route = useRoute();

const data = ref<any>(null);
const loading = ref(true);
const error = ref<string | null>(null);

const filters = reactive({
  semester: "",
});

const allSemesters = ref<any[]>([]);

async function loadReport() {
  loading.value = true;
  error.value = null;
  try {
    const params = new URLSearchParams();
    if (filters.semester) params.set("semester", filters.semester);

    const response = await api.get<any>(`/api/reports/program-revenue/?${params.toString()}`);
    data.value = response;
    if (response.all_semesters) allSemesters.value = response.all_semesters;
  } catch (e: any) {
    error.value = e.message || "Failed to load program revenue report";
  } finally {
    loading.value = false;
  }
}

async function loadFilterOptions() {
  try {
    const semestersRes = await api.get<{ results: any[] }>("/api/semesters/");
    allSemesters.value = semestersRes.results ?? [];
  } catch (e) {
    console.error("Failed to load filter options:", e);
  }
}

function exportCSV() {
  const params = new URLSearchParams();
  if (filters.semester) params.set("semester", filters.semester);
  params.set("format", "csv");
  window.open(`/reports/program-revenue/?${params.toString()}`, "_blank");
}

function clearFilters() {
  filters.semester = "";
  loadReport();
}

onMounted(() => {
  loadFilterOptions();
  loadReport();
});

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Reports</p>
        <h1>Program Revenue</h1>
      </div>
      <NuxtLink to="/reports" class="secondary-link">← All Reports</NuxtLink>
    </section>

    <!-- Filters -->
    <div class="card mb-4 print-hidden">
      <div class="card-body">
        <div class="row g-3 align-items-end flex-wrap">
          <div class="col-12 col-md-6">
            <label class="form-label fw-semibold small">Semester</label>
            <select v-model="filters.semester" class="form-select" @change="loadReport">
              <option value="">Select Semester</option>
              <option v-for="s in allSemesters" :key="s.id" :value="s.id">
                {{ s.name }}
              </option>
            </select>
          </div>
          <div class="col-12 col-md-3">
            <div class="d-flex gap-2">
              <a class="btn btn-outline-success w-100" @click="exportCSV">📥 CSV</a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="state-card">Loading program revenue report…</div>
    <div v-else-if="error" class="state-card error">{{ error }}</div>
    <div v-else-if="data">
      <div v-if="data.semester">
        <!-- Summary Cards -->
        <div class="row g-3 mb-4">
          <div class="col-6 col-md-3">
            <div class="card border-0 shadow-sm text-center p-3">
              <div class="text-muted small">Semester</div>
              <div class="fw-bold">{{ data.semester.name }}</div>
            </div>
          </div>
          <div class="col-6 col-md-3">
            <div class="card border-0 shadow-sm text-center p-3">
              <div class="text-muted small">Total Charged</div>
              <div class="display-6 fw-bold">${{ formatCurrency(data.totals.total_charged) }}</div>
            </div>
          </div>
          <div class="col-6 col-md-3">
            <div class="card border-0 shadow-sm text-center p-3">
              <div class="text-muted small">Total Paid</div>
              <div class="display-6 fw-bold text-success">${{ formatCurrency(data.totals.total_paid) }}</div>
            </div>
          </div>
          <div class="col-6 col-md-3">
            <div class="card border-0 shadow-sm text-center p-3">
              <div class="text-muted small">Total Outstanding</div>
              <div class="display-6 fw-bold text-danger">${{ formatCurrency(data.totals.total_outstanding) }}</div>
            </div>
          </div>
        </div>

        <!-- Results Table -->
        <div class="card border-0 shadow-sm">
          <div class="card-body p-0">
            <div v-if="data.revenue_data.length">
              <div class="table-responsive">
                <table class="table table-hover mb-0">
                  <thead class="table-light">
                    <tr>
                      <th>Program</th>
                      <th>Code</th>
                      <th class="text-end">Charged</th>
                      <th class="text-end">Paid</th>
                      <th class="text-end">Outstanding</th>
                      <th class="text-end">Collection %</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in data.revenue_data" :key="item.program.id">
                      <td>{{ item.program.name }}</td>
                      <td>{{ item.program.code }}</td>
                      <td class="text-end fw-bold">${{ formatCurrency(item.charged) }}</td>
                      <td class="text-end text-success">${{ formatCurrency(item.paid) }}</td>
                      <td class="text-end fw-bold" :class="item.outstanding > 0 ? 'text-danger' : 'text-success'">
                        ${{ formatCurrency(item.outstanding) }}
                      </td>
                      <td class="text-end">{{ item.collection_rate.toFixed(1) }}%</td>
                    </tr>
                  </tbody>
                  <tfoot class="table-light fw-bold">
                    <tr>
                      <td colspan="2">GRAND TOTAL</td>
                      <td class="text-end">${{ formatCurrency(data.totals.total_charged) }}</td>
                      <td class="text-end text-success">${{ formatCurrency(data.totals.total_paid) }}</td>
                      <td class="text-end text-danger">${{ formatCurrency(data.totals.total_outstanding) }}</td>
                      <td class="text-end">{{ data.totals.overall_collection_rate.toFixed(1) }}%</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
            <div v-else class="text-center py-5">
              <p class="text-muted mb-0">No revenue data for {{ data.semester.name }}.</p>
            </div>
          </div>
        </div>
      </div>
      <div v-else>
        <div class="card border-0 shadow-sm">
          <div class="card-body text-center py-5">
            <p class="text-muted mb-0">Select a semester to view program revenue comparison.</p>
          </div>
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
.secondary-link {
  color: #111827;
  background: #f3f4f6;
  text-decoration: none;
  border-radius: 10px;
  padding: 0.7rem 1rem;
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
.table-responsive {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th, td {
  padding: 0.75rem 0.5rem;
  border-bottom: 1px solid #e5e7eb;
  text-align: left;
}
th {
  background: #f9fafb;
  font-weight: 600;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.text-end { text-align: right; }
.text-success { color: #16a34a; }
.text-danger { color: #dc2626; }
.text-muted { color: #6b7280; }
.fw-bold { font-weight: 700; }
.small { font-size: 0.85rem; }
.form-label {
  font-weight: 600;
  margin-bottom: 0.4rem;
  display: block;
}
.form-select {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 0.6rem 0.8rem;
  width: 100%;
}
.row { display: flex; flex-wrap: wrap; margin: 0 -0.5rem; }
.g-3 { gap: 1rem; }
.align-items-end { align-items: flex-end; }
.flex-wrap { flex-wrap: wrap; }
.col-12, .col-md-3, .col-md-6 {
  padding: 0 0.5rem;
}
.col-12 { flex: 0 0 100%; max-width: 100%; }
.col-md-3 { flex: 0 0 25%; max-width: 25%; }
.col-md-6 { flex: 0 0 50%; max-width: 50%; }
@media (max-width: 768px) {
  .col-md-3, .col-md-6 { flex: 0 0 100%; max-width: 100%; }
}
.d-flex { display: flex; }
.gap-2 { gap: 0.5rem; }
.w-100 { width: 100%; }
.btn {
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  text-decoration: none;
  display: inline-block;
}
.btn-outline-success {
  background: transparent;
  border: 1px solid #16a34a;
  color: #16a34a;
}
.fs-6 { font-size: 0.875rem; }
.py-5 { padding-top: 3rem; padding-bottom: 3rem; }
.display-6 { font-size: 1.5rem; font-weight: 700; }
.print-hidden { display: block; }
@media print {
  .print-hidden { display: none !important; }
}
</style>