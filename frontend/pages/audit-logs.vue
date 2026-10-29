<script setup lang="ts">
const api = useApi();
const route = useRoute();

const data = ref<any>(null);
const loading = ref(true);
const error = ref<string | null>(null);

const filters = reactive({
  action: "",
  user: "",
  student: "",
  date_from: "",
  date_to: "",
});

const allActions = ref<any[]>([]);
const allUsers = ref<any[]>([]);

async function loadLogs() {
  loading.value = true;
  error.value = null;
  try {
    const params = new URLSearchParams();
    params.set("page", String(route.query.page || 1));
    if (filters.action) params.set("action", filters.action);
    if (filters.user) params.set("user", filters.user);
    if (filters.student) params.set("student", filters.student);
    if (filters.date_from) params.set("date_from", filters.date_from);
    if (filters.date_to) params.set("date_to", filters.date_to);

    const response = await api.get<any>(`/api/audit-logs/?${params.toString()}`);
    data.value = response;
    if (response.all_actions) allActions.value = response.all_actions;
    if (response.all_users) allUsers.value = response.all_users;
  } catch (e: any) {
    error.value = e.message || "Failed to load audit logs";
  } finally {
    loading.value = false;
  }
}

function clearFilters() {
  filters.action = "";
  filters.user = "";
  filters.student = "";
  filters.date_from = "";
  filters.date_to = "";
  loadLogs();
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString("en-US", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function getActionBadgeClass(action: string): string {
  switch (action) {
    case "REGISTER": return "text-bg-success";
    case "STATUS_CHANGE": return "text-bg-warning";
    case "PAYMENT": return "text-bg-primary";
    case "WITHDRAWAL": return "text-bg-danger";
    default: return "text-bg-secondary";
  }
}

watch(() => route.query.page, (val) => {
  if (val) {
    loadLogs();
  }
});

onMounted(() => {
  loadLogs();
});
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Administration</p>
        <h1>Audit Trail</h1>
      </div>
    </section>

    <!-- Filters -->
    <div class="card mb-4 print-hidden">
      <div class="card-body">
        <div class="row g-3 align-items-end flex-wrap">
          <div class="col-12 col-md-3">
            <label class="form-label fw-semibold small">Action</label>
            <select v-model="filters.action" class="form-select" @change="loadLogs">
              <option value="">All Actions</option>
              <option v-for="a in allActions" :key="a.value" :value="a.value">{{ a.label }}</option>
            </select>
          </div>
          <div class="col-12 col-md-3">
            <label class="form-label fw-semibold small">User</label>
            <select v-model="filters.user" class="form-select" @change="loadLogs">
              <option value="">All Users</option>
              <option v-for="u in allUsers" :key="u.id" :value="u.id">{{ u.username }}</option>
            </select>
          </div>
          <div class="col-12 col-md-2">
            <label class="form-label fw-semibold small">From</label>
            <input type="date" v-model="filters.date_from" class="form-control" @change="loadLogs">
          </div>
          <div class="col-12 col-md-2">
            <label class="form-label fw-semibold small">To</label>
            <input type="date" v-model="filters.date_to" class="form-control" @change="loadLogs">
          </div>
          <div class="col-12 col-md-2">
            <button class="btn btn-outline-secondary w-100" @click="clearFilters">Clear</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Results Table -->
    <div class="card border-0 shadow-sm">
      <div v-if="loading" class="state-card">Loading audit logs…</div>
      <div v-else-if="error" class="state-card error">{{ error }}</div>
      <div v-else-if="data">
        <div class="card-body p-0">
          <div class="table-responsive">
            <table class="table table-hover align-middle mb-0">
              <thead class="table-light">
                <tr>
                  <th>Date & Time</th>
                  <th>User</th>
                  <th>Action</th>
                  <th>Category</th>
                  <th>Student</th>
                  <th>Summary</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="log in data.results" :key="log.id">
                  <td class="text-nowrap">{{ formatDate(log.timestamp) }}</td>
                  <td>{{ log.user?.username || "System" }}</td>
                  <td>
                    <span class="badge" :class="getActionBadgeClass(log.action)">
                      {{ log.action_display }}
                    </span>
                  </td>
                  <td>
                    <span class="badge bg-light text-dark text-uppercase small">{{ log.category }}</span>
                  </td>
                  <td>
                    <NuxtLink v-if="log.student" :to="`/students/${log.student.id}`" class="text-decoration-none">
                      {{ log.student.student_number }}
                    </NuxtLink>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td class="text-truncate" style="max-width: 200px;">{{ log.summary }}</td>
                  <td>
                    <button v-if="log.details && Object.keys(log.details).length" class="btn btn-sm btn-outline-secondary" @click="showDetails(log.details)">
                      View Details
                    </button>
                    <span v-else class="text-muted">—</span>
                  </td>
                </tr>
                <tr v-if="!data.results.length">
                  <td colspan="7" class="text-center text-muted py-4">No audit logs found.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-if="data.pages > 1" class="card-footer bg-white">
          <nav>
            <ul class="pagination justify-content-center mb-0">
              <li v-if="data.page > 1" class="page-item">
                <a class="page-link" :href="`/audit-logs/?page=${data.page - 1}`">&laquo; Previous</a>
              </li>
              <li class="page-item disabled">
                <span class="page-link">Page {{ data.page }} of {{ data.pages }} ({{ data.count }} logs)</span>
              </li>
              <li v-if="data.page < data.pages" class="page-item">
                <a class="page-link" :href="`/audit-logs/?page=${data.page + 1}`">Next &raquo;</a>
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
  vertical-align: middle;
}
th {
  background: #f9fafb;
  font-weight: 600;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.text-nowrap { white-space: nowrap; }
.text-muted { color: #6b7280; }
.text-truncate { overflow: hidden; text-overflow: ellipsis; }
.small { font-size: 0.85rem; }
.text-uppercase { text-transform: uppercase; }
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
.col-12, .col-md-2, .col-md-3 {
  padding: 0 0.5rem;
}
.col-12 { flex: 0 0 100%; max-width: 100%; }
.col-md-2 { flex: 0 0 16.667%; max-width: 16.667%; }
.col-md-3 { flex: 0 0 25%; max-width: 25%; }
@media (max-width: 768px) {
  .col-md-2, .col-md-3 { flex: 0 0 100%; max-width: 100%; }
}
.d-flex { display: flex; }
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
.badge {
  padding: 0.35rem 0.65rem;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 0.5rem;
}
.text-bg-success { background: #dcfce7; color: #166534; }
.text-bg-warning { background: #fef9c3; color: #854d0e; }
.text-bg-primary { background: #dbeafe; color: #1e40af; }
.text-bg-danger { background: #fecaca; color: #991b1b; }
.text-bg-secondary { background: #e5e7eb; color: #374151; }
.bg-light { background: #f3f4f6; }
.text-dark { color: #111827; }
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