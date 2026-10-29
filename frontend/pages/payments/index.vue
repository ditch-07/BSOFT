<script setup lang="ts">
const api = useApi();
const route = useRoute();
const router = useRouter();

const payments = ref<any[]>([]);
const totalCount = ref(0);
const currentPage = ref(1);
const totalPages = ref(1);
const loading = ref(false);
const error = ref<string | null>(null);

const filters = reactive({
  student: "",
  semester: "",
  method: "",
  date_from: "",
  date_to: "",
});

const semesters = ref<any[]>([]);
const students = ref<any[]>([]);

async function loadSemesters() {
  try {
    const response = await api.get<{ results: any[] }>("/api/semesters/");
    semesters.value = response.results ?? [];
  } catch (e) {
    console.error("Failed to load semesters:", e);
  }
}

async function loadPayments() {
  loading.value = true;
  error.value = null;
  try {
    const params = new URLSearchParams();
    params.set("page", String(currentPage.value));
    if (filters.student) params.set("student", filters.student);
    if (filters.semester) params.set("semester", filters.semester);
    if (filters.method) params.set("method", filters.method);
    if (filters.date_from) params.set("date_from", filters.date_from);
    if (filters.date_to) params.set("date_to", filters.date_to);

    const response = await api.get<{ count: number; page: number; pages: number; results: any[] }>(`/api/payments/?${params.toString()}`);
    payments.value = response.results ?? [];
    totalCount.value = response.count ?? 0;
    currentPage.value = response.page ?? 1;
    totalPages.value = response.pages ?? 1;
  } catch (e: any) {
    error.value = e.message || "Failed to load payments";
  } finally {
    loading.value = false;
  }
}

async function searchStudents(query: string) {
  if (query.length < 2) {
    students.value = [];
    return;
  }
  try {
    const response = await api.get<{ students: any[] }>(`/api/students/search/?q=${encodeURIComponent(query)}`);
    students.value = response.students ?? [];
  } catch (e) {
    students.value = [];
  }
}

function onStudentSelect(s: any) {
  filters.student = String(s.id);
  students.value = [];
  currentPage.value = 1;
  loadPayments();
}

function clearFilters() {
  filters.student = "";
  filters.semester = "";
  filters.method = "";
  filters.date_from = "";
  filters.date_to = "";
  currentPage.value = 1;
  loadPayments();
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

const methodLabels: Record<string, string> = {
  CASH: "Cash",
  BANK: "Bank",
  ECOCASH: "EcoCash",
  OTHER: "Other",
};

onMounted(() => {
  loadSemesters();
  loadPayments();
});

watch(() => route.query.page, (val) => {
  if (val) {
    currentPage.value = parseInt(val as string, 10);
    loadPayments();
  }
});
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Payments</p>
        <h1>Payment History</h1>
      </div>
      <NuxtLink to="/payments/new" class="primary-link">Record Payment</NuxtLink>
    </section>

    <!-- Filters -->
    <div class="card mb-4">
      <div class="card-body">
        <div class="row g-3 align-items-end">
          <div class="col-md-3">
            <label class="form-label fw-semibold">Student</label>
            <input
              type="text"
              class="form-control"
              placeholder="Search student..."
              v-model="filters.student"
              @input="() => searchStudents(filters.student)"
            >
            <div v-if="students.length > 0" class="list-group mt-1 shadow-sm" style="position: relative; z-index: 10;">
              <a v-for="s in students" :key="s.id" class="list-group-item list-group-item-action" @click.prevent="onStudentSelect(s)">
                <strong>{{ s.name }}</strong> — {{ s.student_number }}
              </a>
            </div>
          </div>
          <div class="col-md-2">
            <label class="form-label fw-semibold">Semester</label>
            <select v-model="filters.semester" class="form-select" @change="loadPayments">
              <option value="">All Semesters</option>
              <option v-for="sem in semesters" :key="sem.id" :value="sem.id">{{ sem.name }}</option>
            </select>
          </div>
          <div class="col-md-2">
            <label class="form-label fw-semibold">Method</label>
            <select v-model="filters.method" class="form-select" @change="loadPayments">
              <option value="">All Methods</option>
              <option value="CASH">Cash</option>
              <option value="BANK">Bank</option>
              <option value="ECOCASH">EcoCash</option>
              <option value="OTHER">Other</option>
            </select>
          </div>
          <div class="col-md-2">
            <label class="form-label fw-semibold">Date From</label>
            <input type="date" v-model="filters.date_from" class="form-control" @change="loadPayments">
          </div>
          <div class="col-md-2">
            <label class="form-label fw-semibold">Date To</label>
            <input type="date" v-model="filters.date_to" class="form-control" @change="loadPayments">
          </div>
          <div class="col-md-1 d-flex align-items-end">
            <button class="btn btn-outline-secondary w-100" @click="clearFilters">Clear</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Payments Table -->
    <div class="card">
      <div v-if="loading" class="state-card">Loading payments…</div>
      <div v-else-if="error" class="state-card error">{{ error }}</div>
      <div v-else-if="payments.length === 0" class="state-card">No payments found.</div>
      <div v-else>
        <div class="table-responsive">
          <table class="table table-hover">
            <thead>
              <tr>
                <th>Receipt #</th>
                <th>Date</th>
                <th>Student</th>
                <th>Semester</th>
                <th>Method</th>
                <th class="text-end">Amount</th>
                <th>Reference</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in payments" :key="p.id">
                <td class="fw-bold">
                  <NuxtLink :to="`/payments/${p.id}/receipt`">{{ p.receipt_number }}</NuxtLink>
                </td>
                <td>{{ formatDate(p.payment_date) }}</td>
                <td>
                  <NuxtLink :to="`/students/${p.student.id}`">{{ p.student.name }}</NuxtLink>
                  <br><small class="text-muted">{{ p.student.student_number }}</small>
                </td>
                <td>{{ p.semester.name }}</td>
                <td>{{ methodLabels[p.method] || p.method }}</td>
                <td class="text-end text-success fw-bold">${{ formatCurrency(p.amount) }}</td>
                <td>{{ p.reference || "—" }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pagination -->
        <div v-if="totalPages > 1" class="d-flex justify-content-center gap-2 mt-3">
          <button class="btn btn-sm btn-outline-secondary" :disabled="currentPage === 1" @click="currentPage--, loadPayments()">Previous</button>
          <span class="d-flex align-items-center px-2">
            Page {{ currentPage }} of {{ totalPages }} ({{ totalCount }} total)
          </span>
          <button class="btn btn-sm btn-outline-secondary" :disabled="currentPage === totalPages" @click="currentPage++, loadPayments()">Next</button>
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
.fw-semibold { font-weight: 600; }
.small { font-size: 0.85rem; }
.form-label {
  font-weight: 600;
  margin-bottom: 0.4rem;
  display: block;
}
.form-control, .form-select {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 0.6rem 0.8rem;
  width: 100%;
}
.row { display: flex; flex-wrap: wrap; margin: 0 -0.5rem; }
.g-3 { gap: 1rem; }
.align-items-end { align-items: flex-end; }
.col-md-1, .col-md-2, .col-md-3 {
  padding: 0 0.5rem;
}
.col-md-1 { flex: 0 0 8.333%; max-width: 8.333%; }
.col-md-2 { flex: 0 0 16.667%; max-width: 16.667%; }
.col-md-3 { flex: 0 0 25%; max-width: 25%; }
@media (max-width: 768px) {
  .col-md-1, .col-md-2, .col-md-3 { flex: 0 0 100%; max-width: 100%; }
}
.d-flex { display: flex; }
.justify-content-center { justify-content: center; }
.justify-content-between { justify-content: space-between; }
.gap-2 { gap: 0.5rem; }
.mt-1 { margin-top: 0.25rem; }
.mt-3 { margin-top: 1rem; }
.mb-4 { margin-bottom: 1.5rem; }
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
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-sm { padding: 0.4rem 0.8rem; font-size: 0.85rem; }
.btn-outline-secondary {
  background: transparent;
  border: 1px solid #d1d5db;
  color: #374151;
}
.list-group { border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; background: white; }
.list-group-item { padding: 0.75rem 1rem; border-bottom: 1px solid #e5e7eb; cursor: pointer; }
.list-group-item:last-child { border-bottom: none; }
.list-group-item:hover { background: #f9fafb; }
.list-group-item-action { text-decoration: none; color: inherit; display: block; }
</style>