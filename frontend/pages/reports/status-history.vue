<script setup lang="ts">
const api = useApi();
const route = useRoute();

const data = ref<any>(null);
const loading = ref(true);
const error = ref<string | null>(null);

const filters = reactive({
  student: "",
  start_date: "",
  end_date: "",
});

const allStudents = ref<any[]>([]);

async function loadReport() {
  loading.value = true;
  error.value = null;
  try {
    const params = new URLSearchParams();
    params.set("page", String(route.query.page || 1));
    if (filters.student) params.set("student", filters.student);
    if (filters.start_date) params.set("start_date", filters.start_date);
    if (filters.end_date) params.set("end_date", filters.end_date);

    const response = await api.get<any>(`/api/reports/status-history/?${params.toString()}`);
    data.value = response;
    if (response.all_students) allStudents.value = response.all_students;
  } catch (e: any) {
    error.value = e.message || "Failed to load status history report";
  } finally {
    loading.value = false;
  }
}

async function loadFilterOptions() {
  try {
    const studentsRes = await api.get<{ results: any[] }>("/api/students/?status=all");
    allStudents.value = studentsRes.results ?? [];
  } catch (e) {
    console.error("Failed to load filter options:", e);
  }
}

function exportCSV() {
  const params = new URLSearchParams();
  if (filters.student) params.set("student", filters.student);
  if (filters.start_date) params.set("start_date", filters.start_date);
  if (filters.end_date) params.set("end_date", filters.end_date);
  params.set("format", "csv");
  window.open(`/reports/status-history/?${params.toString()}`, "_blank");
}

function clearFilters() {
  filters.student = "";
  filters.start_date = "";
  filters.end_date = "";
  loadReport();
}

watch(() => route.query.page, (val) => {
  if (val) {
    loadReport();
  }
});

onMounted(() => {
  loadFilterOptions();
  loadReport();
});

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString("en-US", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function getStatusBadgeClass(status: string): string {
  switch (status) {
    case "ACTIVE": return "text-bg-success";
    case "DEFERRED": return "text-bg-warning";
    case "WITHDRAWN": return "text-bg-secondary";
    case "COMPLETED": return "text-bg-primary";
    default: return "text-bg-light text-dark";
  }
}
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Reports</p>
        <h1>Status Change History</h1>
      </div>
      <NuxtLink to="/reports" class="secondary-link">← All Reports</NuxtLink>
    </section>

    <!-- Filters -->
    <div class="card mb-4 print-hidden">
      <div class="card-body">
        <div class="row g-3 align-items-end flex-wrap">
          <div class="col-12 col-md-4">
            <label class="form-label fw-semibold small">Student</label>
            <select v-model="filters.student" class="form-select" @change="loadReport">
              <option value="">All Students</option>
              <option v-for="s in allStudents" :key="s.id" :value="s.id">
                {{ s.student_number }} - {{ s.name }} ({{ s.program?.code || 'N/A' }})
              </option>
            </select>
          </div>
          <div class="col-12 col-md-3">
            <label class="form-label fw-semibold small">From Date</label>
            <input type="date" v-model="filters.start_date" class="form-control" @change="loadReport">
          </div>
          <div class="col-12 col-md-3">
            <label class="form-label fw-semibold small">To Date</label>
            <input type="date" v-model="filters.end_date" class="form-control" @change="loadReport">
          </div>
          <div class="col-12 col-md-2">
            <div class="d-flex gap-2">
              <a class="btn btn-outline-success w-100" @click="exportCSV">📥 CSV</a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Results Table -->
    <div class="card">
      <div v-if="loading" class="state-card">Loading status history…</div>
      <div v-else-if="error" class="state-card error">{{ error }}</div>
      <div v-else-if="data">
        <div class="card-body p-0">
          <div v-if="data.results.length">
            <div class="table-responsive">
              <table class="table table-hover mb-0">
                <thead class="table-light">
                  <tr>
                    <th>Date Changed</th>
                    <th>Student</th>
                    <th>Student #</th>
                    <th>Program</th>
                    <th>Status</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="log in data.results" :key="log.id">
                    <td>{{ formatDate(log.date_changed) }}</td>
                    <td>
                      <NuxtLink :to="`/students/${log.student.id}`" class="text-decoration-none">
                        {{ log.student.name }}
                      </NuxtLink>
                    </td>
                    <td>{{ log.student.student_number }}</td>
                    <td>{{ log.student.program }}</td>
                    <td>
                      <span class="badge" :class="getStatusBadgeClass(log.status)">
                        {{ log.status_display }}
                      </span>
                    </td>
                    <td class="text-muted small">{{ log.note || "—" }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div v-else class="text-center py-5">
            <p class="text-muted mb-0">No status changes found for the selected filters.</p>
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="data.pages > 1" class="card-footer bg-white">
          <nav>
            <ul class="pagination justify-content-center mb-0">
              <li v-if="data.page > 1" class="page-item">
                <a class="page-link" :href="`/reports/status-history/?page=${data.page - 1}`">Previous</a>
              </li>
              <li class="page-item disabled">
                <span class="page-link">Page {{ data.page }} of {{ data.pages }} ({{ data.count }} records)</span>
              </li>
              <li v-if="data.page < data.pages" class="page-item">
                <a class="page-link" :href="`/reports/status-history/?page=${data.page + 1}`">Next</a>
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
.form-select, .form-control {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 0.6rem 0.8rem;
  width: 100%;
}
.row { display: flex; flex-wrap: wrap; margin: 0 -0.5rem; }
.g-3 { gap: 1rem; }
.align-items-end { align-items: flex-end; }
.flex-wrap { flex-wrap: wrap; }
.col-12, .col-md-2, .col-md-3, .col-md-4 {
  padding: 0 0.5rem;
}
.col-12 { flex: 0 0 100%; max-width: 100%; }
.col-md-2 { flex: 0 0 16.667%; max-width: 16.667%; }
.col-md-3 { flex: 0 0 25%; max-width: 25%; }
.col-md-4 { flex: 0 0 33.333%; max-width: 33.333%; }
@media (max-width: 768px) {
  .col-md-2, .col-md-3, .col-md-4 { flex: 0 0 100%; max-width: 100%; }
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
.badge {
  padding: 0.35rem 0.65rem;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 0.5rem;
}
.text-bg-success { background: #dcfce7; color: #166534; }
.text-bg-warning { background: #fef9c3; color: #854d0e; }
.text-bg-secondary { background: #e5e7eb; color: #374151; }
.text-bg-primary { background: #dbeafe; color: #1e40af; }
.text-bg-light { background: #f3f4f6; color: #111827; }
.text-decoration-none { text-decoration: none; }
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
.table-light { background: #f9fafb; }
.print-hidden { display: block; }
@media print {
  .print-hidden { display: none !important; }
}
</style>