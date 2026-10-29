<script setup lang="ts">
const api = useApi();
const route = useRoute();

const data = ref<any>(null);
const loading = ref(true);
const error = ref<string | null>(null);

const filters = reactive({
  date_from: "",
  date_to: "",
});

async function loadReport() {
  loading.value = true;
  error.value = null;
  try {
    const params = new URLSearchParams();
    params.set("page", String(route.query.page || 1));
    if (filters.date_from) params.set("date_from", filters.date_from);
    if (filters.date_to) params.set("date_to", filters.date_to);

    const response = await api.get<any>(`/api/reports/daily-collections/?${params.toString()}`);
    data.value = response;
  } catch (e: any) {
    error.value = e.message || "Failed to load daily collections report";
  } finally {
    loading.value = false;
  }
}

function exportCSV() {
  const params = new URLSearchParams();
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  params.set("format", "csv");
  window.open(`/reports/daily-collections/?${params.toString()}`, "_blank");
}

function clearFilters() {
  filters.date_from = "";
  filters.date_to = "";
  loadReport();
}

watch(() => route.query.page, (val) => {
  if (val) {
    loadReport();
  }
});

onMounted(() => {
  loadReport();
});

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

function getMethodBadgeClass(method: string): string {
  switch (method) {
    case "CASH": return "bg-success";
    case "BANK": return "bg-primary";
    case "ECOCASH": return "bg-warning text-dark";
    default: return "bg-secondary";
  }
}
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Reports</p>
        <h1>Daily Collections</h1>
      </div>
      <NuxtLink to="/reports" class="secondary-link">← All Reports</NuxtLink>
    </section>

    <!-- Filters -->
    <div class="card mb-4 print-hidden">
      <div class="card-body">
        <div class="row g-3 align-items-end flex-wrap">
          <div class="col-12 col-md-3">
            <label class="form-label fw-semibold small">From Date</label>
            <input type="date" v-model="filters.date_from" class="form-control" @change="loadReport">
          </div>
          <div class="col-12 col-md-3">
            <label class="form-label fw-semibold small">To Date</label>
            <input type="date" v-model="filters.date_to" class="form-control" @change="loadReport">
          </div>
          <div class="col-12 col-md-2">
            <div v-if="filters.date_from || filters.date_to">
              <button class="btn btn-outline-secondary w-100" @click="clearFilters">Clear</button>
            </div>
          </div>
          <div class="col-12 col-md-4 text-md-end">
            <div class="d-flex gap-2 justify-content-center justify-content-md-end">
              <a class="btn btn-outline-success" @click="exportCSV">📥 CSV</a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Summary Cards -->
    <div v-if="data" class="row g-3 mb-4">
      <div class="col-6 col-md-3">
        <div class="card border-0 shadow-sm text-center p-3">
          <div class="text-muted small">Period</div>
          <div class="fw-bold">{{ data.display_date }}</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="card border-0 shadow-sm text-center p-3">
          <div class="text-muted small">Transactions</div>
          <div class="display-6 fw-bold">{{ data.totals.transaction_count }}</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="card border-0 shadow-sm text-center p-3">
          <div class="text-muted small">Total Collected</div>
          <div class="display-6 fw-bold text-success">${{ formatCurrency(data.totals.total) }}</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="card border-0 shadow-sm text-center p-3">
          <div class="text-muted small">Avg Transaction</div>
          <div class="display-6 fw-bold">
            ${{ formatCurrency(data.totals.avg_transaction) }}
          </div>
        </div>
      </div>
    </div>

    <!-- Results Table -->
    <div class="card">
      <div v-if="loading" class="state-card">Loading daily collections…</div>
      <div v-else-if="error" class="state-card error">{{ error }}</div>
      <div v-else-if="data">
        <div class="card-body p-0">
          <div v-if="data.results.length">
            <div class="table-responsive">
              <table class="table table-hover mb-0">
                <thead class="table-light">
                  <tr>
                    <th>Receipt</th>
                    <th>Student</th>
                    <th>Student #</th>
                    <th>Semester</th>
                    <th>Method</th>
                    <th class="text-end">Amount</th>
                    <th>Reference</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="payment in data.results" :key="payment.id">
                    <td class="fw-bold">
                      <NuxtLink :to="`/payments/${payment.id}/receipt`">{{ payment.receipt_number }}</NuxtLink>
                    </td>
                    <td>
                      <NuxtLink :to="`/students/${payment.student.id}`" class="text-decoration-none">
                        {{ payment.student.name }}
                      </NuxtLink>
                    </td>
                    <td>{{ payment.student.student_number }}</td>
                    <td>{{ payment.semester.name }}</td>
                    <td>
                      <span class="badge" :class="getMethodBadgeClass(payment.method)">
                        {{ payment.method_display }}
                      </span>
                    </td>
                    <td class="text-end fw-bold">${{ formatCurrency(payment.amount) }}</td>
                    <td>{{ payment.reference || "—" }}</td>
                  </tr>
                </tbody>
                <tfoot class="table-light fw-bold">
                  <tr>
                    <td colspan="5" class="text-end">TOTAL</td>
                    <td class="text-end">${{ formatCurrency(data.totals.total) }}</td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
          <div v-else class="text-center py-5">
            <p class="text-muted mb-0">No payments recorded for {{ data.display_date }}.</p>
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="data.pages > 1" class="card-footer bg-white">
          <nav>
            <ul class="pagination justify-content-center mb-0">
              <li v-if="data.page > 1" class="page-item">
                <a class="page-link" :href="`/reports/daily-collections/?page=${data.page - 1}`">Previous</a>
              </li>
              <li class="page-item disabled">
                <span class="page-link">Page {{ data.page }} of {{ data.pages }} ({{ data.count }} records)</span>
              </li>
              <li v-if="data.page < data.pages" class="page-item">
                <a class="page-link" :href="`/reports/daily-collections/?page=${data.page + 1}`">Next</a>
              </li>
            </ul>
          </nav>
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
.card-footer {
  padding: 0.75rem 1.2rem;
  border-top: 1px solid #e5e7eb;
  background: white;
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
.text-muted { color: #6b7280; }
.fw-bold { font-weight: 700; }
.small { font-size: 0.85rem; }
.form-label {
  font-weight: 600;
  margin-bottom: 0.4rem;
  display: block;
}
.form-control {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 0.6rem 0.8rem;
  width: 100%;
}
.row { display: flex; flex-wrap: wrap; margin: 0 -0.5rem; }
.g-3 { gap: 1rem; }
.align-items-end { align-items: flex-end; }
.flex-wrap { flex-wrap: wrap; }
.col-12, .col-md-2, .col-md-3, .col-md-4, .col-6 {
  padding: 0 0.5rem;
}
.col-12 { flex: 0 0 100%; max-width: 100%; }
.col-md-2 { flex: 0 0 16.667%; max-width: 16.667%; }
.col-md-3 { flex: 0 0 25%; max-width: 25%; }
.col-md-4 { flex: 0 0 33.333%; max-width: 33.333%; }
.col-6 { flex: 0 0 50%; max-width: 50%; }
@media (max-width: 768px) {
  .col-md-2, .col-md-3, .col-md-4, .col-6 { flex: 0 0 100%; max-width: 100%; }
}
.d-flex { display: flex; }
.justify-content-center { justify-content: center; }
.justify-content-md-end { justify-content: flex-end; }
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
.btn-sm { padding: 0.4rem 0.8rem; font-size: 0.85rem; }
.btn-outline-secondary {
  background: transparent;
  border: 1px solid #d1d5db;
  color: #374151;
}
.btn-outline-success {
  background: transparent;
  border: 1px solid #16a34a;
  color: #16a34a;
}
.badge {
  padding: 0.35rem 0.65rem;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 0.5rem;
}
.bg-success { background: #dcfce7; color: #166534; }
.bg-primary { background: #dbeafe; color: #1e40af; }
.bg-warning { background: #fef9c3; color: #854d0e; }
.bg-secondary { background: #e5e7eb; color: #374151; }
.text-dark { color: #111827; }
.display-6 { font-size: 1.5rem; font-weight: 700; }
.table-light { background: #f9fafb; }
.pagination {
  display: flex;
  padding-left: 0;
  list-style: none;
}
.page-item { margin: 0 0.25rem; }
.page-link {
  padding: 0.375rem 0.75rem;
  border: 1px solid #dee2e6;
  color: #2563eb;
  text-decoration: none;
  border-radius: 0.375rem;
}
.page-link:hover { background: #eff6ff; }
.page-item.disabled .page-link {
  color: #6c757d;
  pointer-events: none;
  background-color: #fff;
  border-color: #dee2e6;
}
.print-hidden { display: block; }
@media print {
  .print-hidden { display: none !important; }
}
</style>