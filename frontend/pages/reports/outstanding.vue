<script setup lang="ts">
const api = useApi();
const route = useRoute();

const data = ref<any>(null);
const loading = ref(true);
const error = ref<string | null>(null);

const filters = reactive({
  semester: "",
  program: "",
});

const allSemesters = ref<any[]>([]);
const allPrograms = ref<any[]>([]);

async function loadReport() {
  loading.value = true;
  error.value = null;
  try {
    const params = new URLSearchParams();
    params.set("page", String(route.query.page || 1));
    if (filters.semester) params.set("semester", filters.semester);
    if (filters.program) params.set("program", filters.program);

    const response = await api.get<any>(`/api/reports/outstanding/?${params.toString()}`);
    data.value = response;
    if (response.all_semesters) allSemesters.value = response.all_semesters;
    if (response.all_programs) allPrograms.value = response.all_programs;
  } catch (e: any) {
    error.value = e.message || "Failed to load outstanding balances report";
  } finally {
    loading.value = false;
  }
}

async function loadFilterOptions() {
  try {
    const [semestersRes, programsRes] = await Promise.all([
      api.get<{ results: any[] }>("/api/semesters/"),
      api.get<{ results: any[] }>("/api/programs/"),
    ]);
    allSemesters.value = semestersRes.results ?? [];
    allPrograms.value = programsRes.results ?? [];
  } catch (e) {
    console.error("Failed to load filter options:", e);
  }
}

function exportCSV() {
  const params = new URLSearchParams();
  if (filters.semester) params.set("semester", filters.semester);
  if (filters.program) params.set("program", filters.program);
  params.set("format", "csv");
  window.open(`/reports/outstanding/?${params.toString()}`, "_blank");
}

function clearFilters() {
  filters.semester = "";
  filters.program = "";
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

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
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
        <h1>Outstanding Balances</h1>
      </div>
      <NuxtLink to="/reports" class="secondary-link">← All Reports</NuxtLink>
    </section>

    <!-- Filters -->
    <div class="card mb-4 print-hidden">
      <div class="card-body">
        <div class="row g-3 align-items-end flex-wrap">
          <div class="col-12 col-md-5">
            <label class="form-label fw-semibold small">Semester</label>
            <select v-model="filters.semester" class="form-select" @change="loadReport">
              <option v-for="s in allSemesters" :key="s.id" :value="s.id">
                {{ s.name }}
              </option>
            </select>
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label fw-semibold small">Program</label>
            <select v-model="filters.program" class="form-select" @change="loadReport">
              <option value="">All Programs</option>
              <option v-for="p in allPrograms" :key="p.id" :value="p.id">
                {{ p.name }} ({{ p.code }})
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

    <!-- Summary Cards -->
    <div v-if="data?.semester" class="row g-3 mb-4">
      <div class="col-6 col-md-3">
        <div class="card border-0 shadow-sm text-center p-3">
          <div class="text-muted small">Semester</div>
          <div class="fw-bold">{{ data.semester.name }}</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="card border-0 shadow-sm text-center p-3">
          <div class="text-muted small">Students with Balance</div>
          <div class="display-6 fw-bold text-danger">{{ data.totals.total_students }}</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="card border-0 shadow-sm text-center p-3">
          <div class="text-muted small">Total Outstanding</div>
          <div class="display-6 fw-bold text-danger">
            ${{ formatCurrency(data.totals.total_outstanding) }}
          </div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="card border-0 shadow-sm text-center p-3">
          <div class="text-muted small">Avg Outstanding</div>
          <div class="display-6 fw-bold">
            ${{ formatCurrency(data.totals.avg_outstanding) }}
          </div>
        </div>
      </div>
    </div>

    <!-- Results Table -->
    <div class="card">
      <div v-if="loading" class="state-card">Loading outstanding balances…</div>
      <div v-else-if="error" class="state-card error">{{ error }}</div>
      <div v-else-if="data">
        <div class="card-body p-0">
          <div class="table-responsive">
            <table class="table table-hover mb-0">
              <thead class="table-light">
                <tr>
                  <th>Student Number</th>
                  <th>Name</th>
                  <th>Program</th>
                  <th class="text-end">Charged</th>
                  <th class="text-end">Paid</th>
                  <th class="text-end">Outstanding</th>
                  <th class="text-end">Collection %</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="student in data.results" :key="student.id">
                  <td class="fw-bold">{{ student.student_number }}</td>
                  <td>
                    <NuxtLink :to="`/students/${student.id}`" class="text-decoration-none">
                      {{ student.name }}
                    </NuxtLink>
                  </td>
                  <td>{{ student.program }}</td>
                  <td class="text-end">${{ formatCurrency(student.charged) }}</td>
                  <td class="text-end text-success">${{ formatCurrency(student.paid) }}</td>
                  <td class="text-end fw-bold" :class="student.outstanding > 0 ? 'text-danger' : 'text-success'">
                    ${{ formatCurrency(student.outstanding) }}
                  </td>
                  <td class="text-end">{{ student.collection_rate.toFixed(1) }}%</td>
                </tr>
                <tr v-if="!data.results.length">
                  <td colspan="7" class="text-center text-muted py-4">
                    No students with outstanding balances{{ data.semester ? ` for ${data.semester.name}` : '' }}.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="data.pages > 1" class="card-footer bg-white">
          <nav>
            <ul class="pagination justify-content-center mb-0">
              <li v-if="data.page > 1" class="page-item">
                <a class="page-link" :href="`/reports/outstanding/?page=${data.page - 1}`">Previous</a>
              </li>
              <li class="page-item disabled">
                <span class="page-link">Page {{ data.page }} of {{ data.pages }} ({{ data.count }} students)</span>
              </li>
              <li v-if="data.page < data.pages" class="page-item">
                <a class="page-link" :href="`/reports/outstanding/?page=${data.page + 1}`">Next</a>
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
.col-12, .col-md-3, .col-md-4, .col-md-5, .col-6 {
  padding: 0 0.5rem;
}
.col-12 { flex: 0 0 100%; max-width: 100%; }
.col-md-3 { flex: 0 0 25%; max-width: 25%; }
.col-md-4 { flex: 0 0 33.333%; max-width: 33.333%; }
.col-md-5 { flex: 0 0 41.667%; max-width: 41.667%; }
.col-6 { flex: 0 0 50%; max-width: 50%; }
@media (max-width: 768px) {
  .col-md-3, .col-md-4, .col-md-5, .col-6 { flex: 0 0 100%; max-width: 100%; }
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
.display-6 { font-size: 1.5rem; font-weight: 700; }
.table-light { background: #f9fafb; }
.print-hidden { display: block; }
@media print {
  .print-hidden { display: none !important; }
}
</style>