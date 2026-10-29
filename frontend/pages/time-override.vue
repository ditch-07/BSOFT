<script setup lang="ts">
const api = useApi();
const router = useRouter();

const data = ref<any>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const submitting = ref(false);
const frozenDatetime = ref("");

async function loadTimeOverride() {
  loading.value = true;
  try {
    const response = await api.get<any>("/api/time-override/");
    data.value = response;
    if (response.frozen) {
      frozenDatetime.value = response.frozen.slice(0, 16); // Format for datetime-local input
    }
  } catch (e: any) {
    error.value = e.message || "Failed to load time override";
  } finally {
    loading.value = false;
  }
}

async function setTimeOverride() {
  if (!frozenDatetime.value) {
    alert("Please select a date and time.");
    return;
  }
  
  submitting.value = true;
  try {
    const response = await api.post("/api/time-override/", {
      action: "set",
      frozen_datetime: frozenDatetime.value,
    });
    if (response.success) {
      await loadTimeOverride();
    }
  } catch (e: any) {
    alert(e.message || "Failed to set time override");
  } finally {
    submitting.value = false;
  }
}

async function clearTimeOverride() {
  if (!confirm("Are you sure you want to clear the time override? This will restore real system time.")) {
    return;
  }
  
  submitting.value = true;
  try {
    const response = await api.post("/api/time-override/", {
      action: "clear",
    });
    if (response.success) {
      await loadTimeOverride();
    }
  } catch (e: any) {
    alert(e.message || "Failed to clear time override");
  } finally {
    submitting.value = false;
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleString("en-US", { 
    year: "numeric", 
    month: "long", 
    day: "numeric", 
    hour: "2-digit", 
    minute: "2-digit",
    timeZoneName: "short"
  });
}

onMounted(() => {
  loadTimeOverride();
});
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Administration</p>
        <h1>Time Override</h1>
      </div>
      <NuxtLink to="/users" class="secondary-link">← User Management</NuxtLink>
    </section>

    <div v-if="loading" class="state-card">Loading time override status…</div>
    <div v-else-if="error" class="state-card error">{{ error }}</div>
    <div v-else-if="data">
      <div class="card border-0 shadow-sm mb-4">
        <div class="card-header">
          <h5 class="mb-0"><i class="bi bi-clock me-2"></i>Time Override (Testing Only)</h5>
        </div>
        <div class="card-body">
          <p class="text-muted mb-4">
            Set a fixed date/time to test semester logic, payment due dates, student progression, etc.
            The override persists across server restarts until you clear it.
          </p>
          
          <form @submit.prevent="setTimeOverride" class="row g-3 mb-4">
            <div class="col-12 col-md-6">
              <label class="form-label fw-semibold">Frozen Date & Time</label>
              <input
                type="datetime-local"
                v-model="frozenDatetime"
                class="form-control"
                :disabled="submitting"
              >
            </div>
            <div class="col-12 col-md-6 d-flex align-items-end gap-2">
              <button type="submit" class="btn btn-primary" :disabled="submitting || !frozenDatetime">
                <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>
                <i v-else class="bi bi-clock me-1"></i> Set Override
              </button>
              <button type="button" class="btn btn-outline-danger" @click="clearTimeOverride" :disabled="submitting || !data.is_frozen">
                <i class="bi bi-x-circle me-1"></i> Clear
              </button>
            </div>
          </form>
          
          <div v-if="data.is_frozen" class="alert alert-info mb-0">
            <strong>Currently frozen to:</strong> {{ formatDate(data.frozen) }}
            <br><small>All datetime functions will return this value. Student progression, semester status, and payment due dates will use this frozen time.</small>
          </div>
          <div v-else class="alert alert-success mb-0">
            <strong>No time override active.</strong> Using real system time.
          </div>
        </div>
      </div>

      <!-- Warning Card -->
      <div class="card border-0 shadow-sm border-warning">
        <div class="card-header bg-warning bg-opacity-10">
          <h5 class="mb-0"><i class="bi bi-exclamation-triangle me-2"></i>Important Notes</h5>
        </div>
        <div class="card-body">
          <ul class="mb-0 small">
            <li>Time override affects <strong>all</strong> datetime calculations in the system including student progression, semester status, payment due dates, and report date filtering.</li>
            <li>The override is stored in the database and <strong>persists across server restarts</strong>.</li>
            <li>Only superusers can access this page.</li>
            <li>Remember to <strong>clear the override</strong> when testing is complete to return to real-time operation.</li>
            <li>Background jobs (APScheduler) may also use the overridden time depending on their implementation.</li>
          </ul>
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
  max-width: 800px;
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
.card-header {
  padding: 1rem 1.2rem;
  border-bottom: 1px solid #e5e7eb;
  background: white;
}
.card-body {
  padding: 1.5rem;
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
.form-control:disabled {
  background: #f9fafb;
}
.row { display: flex; flex-wrap: wrap; margin: 0 -0.5rem; }
.g-3 { gap: 1rem; }
.col-12, .col-md-6 {
  padding: 0 0.5rem;
}
.col-12 { flex: 0 0 100%; max-width: 100%; }
.col-md-6 { flex: 0 0 50%; max-width: 50%; }
@media (max-width: 768px) {
  .col-md-6 { flex: 0 0 100%; max-width: 100%; }
}
.d-flex { display: flex; }
.align-items-end { align-items: flex-end; }
.gap-2 { gap: 0.5rem; }
.mb-4 { margin-bottom: 1.5rem; }
.mb-0 { margin-bottom: 0; }
.btn {
  padding: 0.6rem 1.2rem;
  border-radius: 8px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-primary { background: #2563eb; color: white; }
.btn-outline-danger {
  background: transparent;
  border: 1px solid #dc2626;
  color: #dc2626;
}
.btn-outline-secondary {
  background: transparent;
  border: 1px solid #d1d5db;
  color: #374151;
}
.alert {
  padding: 1rem 1.25rem;
  border-radius: 8px;
  border: 1px solid transparent;
}
.alert-info {
  background: #dbeafe;
  border-color: #93c5fd;
  color: #1e40af;
}
.alert-success {
  background: #dcfce7;
  border-color: #86efac;
  color: #166534;
}
.alert strong { font-weight: 600; }
.small { font-size: 0.85rem; }
.border-warning { border-color: #f59e0b !important; }
.bg-opacity-10 { --bs-bg-opacity: 0.1; background-color: rgba(245, 158, 11, var(--bs-bg-opacity)) !important; }
.bg-warning { background-color: #f59e0b !important; }
.spinner-border {
  display: inline-block;
  width: 1rem;
  height: 1rem;
  vertical-align: text-bottom;
  border: 0.2em solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: spinner-border 0.75s linear infinite;
}
@keyframes spinner-border {
  to { transform: rotate(360deg); }
}
.spinner-border-sm {
  width: 0.75rem;
  height: 0.75rem;
  border-width: 0.15em;
}
</style>