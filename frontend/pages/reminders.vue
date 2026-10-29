<script setup lang="ts">
const api = useApi();
const route = useRoute();

const data = ref<any>(null);
const loading = ref(true);
const error = ref<string | null>(null);

async function loadReminders() {
  loading.value = true;
  error.value = null;
  try {
    const params = new URLSearchParams();
    params.set("page", String(route.query.page || 1));

    const response = await api.get<any>(`/api/reminders/?${params.toString()}`);
    data.value = response;
  } catch (e: any) {
    error.value = e.message || "Failed to load reminders";
  } finally {
    loading.value = false;
  }
}

watch(() => route.query.page, (val) => {
  if (val) {
    loadReminders();
  }
});

onMounted(() => {
  loadReminders();
});

function getMissingBadges(missing: string[]): string {
  return missing.map(m => `<span class="badge bg-light text-dark me-1 mb-1"><i class="bi bi-exclamation-circle text-warning"></i> ${m}</span>`).join('');
}
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Follow-up</p>
        <h1>Reminders</h1>
      </div>
      <div v-if="data?.total_reminders > 0" class="badge bg-warning text-dark fs-6">{{ data.total_reminders }} Missing Details</div>
    </section>

    <div v-if="loading" class="state-card">Loading reminders…</div>
    <div v-else-if="error" class="state-card error">{{ error }}</div>
    <div v-else-if="data">
      <div v-if="data.results.length">
        <!-- Reminders List -->
        <div class="card border-0 shadow-sm">
          <div class="card-body p-0">
            <div class="list-group list-group-flush">
              <div v-for="student in data.results" :key="student.id" class="list-group-item border-start-4 border-start-warning">
                <div class="d-flex justify-content-between align-items-start">
                  <div>
                    <h6 class="mb-1 fw-bold">
                      {{ student.student_number }} - {{ student.name }}
                    </h6>
                    <p class="text-muted small mb-2">
                      <i class="bi bi-bookmark"></i> {{ student.program.code }} - {{ student.program.name }}
                    </p>

                    <!-- Missing Details Indicators -->
                    <div class="small">
                      <span v-for="detail in student.missing_details" :key="detail" class="badge bg-light text-dark me-1 mb-1">
                        <i class="bi bi-exclamation-circle text-warning"></i> {{ detail }}
                      </span>
                    </div>
                  </div>

                  <!-- Action Button -->
                  <div>
                    <NuxtLink :to="`/students/${student.id}/edit`" class="btn btn-sm btn-primary">
                      <i class="bi bi-pencil me-1"></i>Edit
                    </NuxtLink>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Pagination -->
          <div v-if="data.pages > 1" class="card-footer bg-white">
            <nav>
              <ul class="pagination justify-content-center mb-0">
                <li v-if="data.page > 1" class="page-item">
                  <a class="page-link" :href="`/reminders/?page=${data.page - 1}`">&laquo; Previous</a>
                </li>
                <li class="page-item disabled">
                  <span class="page-link">Page {{ data.page }} of {{ data.pages }}</span>
                </li>
                <li v-if="data.page < data.pages" class="page-item">
                  <a class="page-link" :href="`/reminders/?page=${data.page + 1}`">Next &raquo;</a>
                </li>
              </ul>
            </nav>
          </div>
        </div>
      </div>

      <div v-else>
        <!-- No Reminders -->
        <div class="card border-0 shadow-sm">
          <div class="card-body text-center py-5">
            <i class="bi bi-check-circle text-success" style="font-size: 3rem;"></i>
            <h5 class="mt-3">All Set!</h5>
            <p class="text-muted">All active students have complete details.</p>
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
.fs-6 { font-size: 0.875rem; }
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
.list-group {
  border: none;
}
.list-group-item {
  border: 1px solid #e5e7eb;
  border-left-width: 4px;
  border-radius: 0;
  padding: 1rem;
}
.list-group-item:first-child {
  border-top-left-radius: 0.375rem;
  border-top-right-radius: 0.375rem;
}
.list-group-item:last-child {
  border-bottom-left-radius: 0.375rem;
  border-bottom-right-radius: 0.375rem;
}
.list-group-flush .list-group-item {
  border-left: 4px solid #ffc107;
  border-right: none;
  border-top: none;
  border-bottom: 1px solid #e5e7eb;
}
.d-flex { display: flex; }
.justify-content-between { justify-content: space-between; }
.align-items-start { align-items: flex-start; }
.mb-1 { margin-bottom: 0.25rem; }
.mb-2 { margin-bottom: 0.5rem; }
.fw-bold { font-weight: 700; }
.text-muted { color: #6b7280; }
.small { font-size: 0.85rem; }
.badge {
  padding: 0.35rem 0.65rem;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 0.5rem;
}
.bg-light { background: #f3f4f6; }
.text-dark { color: #111827; }
.text-warning { color: #ffc107; }
.text-success { color: #16a34a; }
.bg-warning { background: #ffc107; }
.bg-secondary { background: #e5e7eb; }
.border-start-4 { border-left-width: 4px !important; }
.border-start-warning { border-left-color: #ffc107 !important; }
.me-1 { margin-right: 0.25rem; }
.mb-1 { margin-bottom: 0.25rem; }
.ms-1 { margin-left: 0.25rem; }
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
.btn-primary { background: #2563eb; color: white; }
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
</style>