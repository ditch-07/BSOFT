<script setup lang="ts">
const api = useApi();
const router = useRouter();

const form = reactive({
  backup_path: "",
  auto_backup_enabled: true,
  retention_days: 7,
  strict_mode: true,
});

const saving = ref(false);
const data = ref<any>(null);
const loading = ref(true);
const error = ref<string | null>(null);

async function loadSettings() {
  loading.value = true;
  try {
    const response = await api.get<any>("/api/backup/settings/");
    data.value = response;
    form.backup_path = response.backup_path || "";
    form.auto_backup_enabled = response.auto_backup_enabled;
    form.retention_days = response.retention_days;
    form.strict_mode = response.strict_mode;
  } catch (e: any) {
    error.value = e.message || "Failed to load settings";
  } finally {
    loading.value = false;
  }
}

async function saveSettings() {
  saving.value = true;
  try {
    await api.patch("/api/backup/settings/", {
      backup_path: form.backup_path,
      auto_backup_enabled: form.auto_backup_enabled,
      retention_days: form.retention_days,
      strict_mode: form.strict_mode,
    });
    alert("Backup settings saved successfully.");
    await loadSettings();
  } catch (e: any) {
    alert(e.message || "Failed to save settings");
  } finally {
    saving.value = false;
  }
}

function setQuickPath(path: string) {
  form.backup_path = path;
}

onMounted(() => {
  loadSettings();
});
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Administration</p>
        <h1>Backup Settings</h1>
      </div>
      <NuxtLink to="/backups" class="secondary-link">← Back to Backups</NuxtLink>
    </section>

    <div v-if="loading" class="state-card">Loading settings…</div>
    <div v-else-if="error" class="state-card error">{{ error }}</div>
    <div v-else>
      <div class="card border-0 shadow-sm mb-4">
        <div class="card-body">
          <form @submit.prevent="saveSettings">
            <div class="mb-3">
              <label for="backup_path" class="form-label fw-semibold">Backup Path</label>
              <input
                type="text"
                id="backup_path"
                v-model="form.backup_path"
                class="form-control"
                placeholder="/path/to/backup"
              >
              <div class="form-text">
                Absolute path to backup directory. Leave empty to use default project backups folder.
              </div>
              <div class="mt-2">
                <span class="text-muted small me-2">Quick paths:</span>
                <button type="button" class="btn btn-sm btn-outline-primary path-btn me-1 mb-1" @click="setQuickPath('')">Default (project/backups)</button>
                <button type="button" class="btn btn-sm btn-outline-primary path-btn me-1 mb-1" @click="setQuickPath('D:\\backups')">D:\backups</button>
                <button type="button" class="btn btn-sm btn-outline-primary path-btn me-1 mb-1" @click="setQuickPath('E:\\backups')">E:\backups</button>
                <button type="button" class="btn btn-sm btn-outline-primary path-btn me-1 mb-1" @click="setQuickPath('F:\\backups')">F:\backups</button>
              </div>
            </div>

            <div class="mb-3">
              <div class="form-check form-switch">
                <input
                  type="checkbox"
                  id="auto_backup_enabled"
                  v-model="form.auto_backup_enabled"
                  class="form-check-input"
                >
                <label class="form-check-label fw-semibold" for="auto_backup_enabled">Enable automatic daily backups</label>
              </div>
              <div class="form-text">When enabled, the <code>backup_auto</code> management command will create daily backups (schedule via cron).</div>
            </div>

            <div class="mb-3">
              <label for="retention_days" class="form-label fw-semibold">Retention Days</label>
              <input
                type="number"
                id="retention_days"
                v-model.number="form.retention_days"
                class="form-control"
                min="1"
                max="365"
              >
              <div class="form-text">Number of days to keep backup files before automatic cleanup.</div>
            </div>

            <div class="mb-3">
              <div class="form-check form-switch">
                <input
                  type="checkbox"
                  id="strict_mode"
                  v-model="form.strict_mode"
                  class="form-check-input"
                >
                <label class="form-check-label fw-semibold" for="strict_mode">Strict mode</label>
              </div>
              <div class="form-text">When ON, dashboard will show an alert if the configured backup path is not available/writable.</div>
            </div>

            <button type="submit" class="btn btn-primary" :disabled="saving">
              <span v-if="saving">Saving…</span>
              <span v-else>Save Settings</span>
            </button>
          </form>
        </div>
      </div>

      <div v-if="data" class="card border-0 shadow-sm">
        <div class="card-body">
          <h5>Current Status</h5>
          <hr>
          <dl class="row mb-0">
            <dt class="col-sm-3 text-muted">Backup path</dt>
            <dd class="col-sm-9"><code>{{ data.effective_backup_path }}</code></dd>
            
            <dt class="col-sm-3 text-muted">Available</dt>
            <dd class="col-sm-9">
              <span class="badge" :class="data.backup_available ? 'text-bg-success' : 'text-bg-danger'">
                {{ data.backup_available ? 'Yes' : 'No' }}
              </span>
              <span v-if="!data.backup_available" class="text-muted small ms-2">(path does not exist or is not writable)</span>
            </dd>
            
            <dt class="col-sm-3 text-muted">Strict mode</dt>
            <dd class="col-sm-9">
              <span class="badge" :class="data.strict_mode ? 'text-bg-warning' : 'text-bg-secondary'">
                {{ data.strict_mode ? 'ON' : 'OFF' }}
              </span>
            </dd>
            
            <dt class="col-sm-3 text-muted">Auto backup</dt>
            <dd class="col-sm-9">
              <span class="badge" :class="data.auto_backup_enabled ? 'text-bg-success' : 'text-bg-secondary'">
                {{ data.auto_backup_enabled ? 'Enabled' : 'Disabled' }}
              </span>
              <span v-if="data.auto_backup_enabled" class="text-muted ms-2">(runs daily via cron)</span>
            </dd>
            
            <dt class="col-sm-3 text-muted">Retention</dt>
            <dd class="col-sm-9">{{ data.retention_days }} days</dd>
          </dl>
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
.form-text {
  font-size: 0.8rem;
  color: #6b7280;
  margin-top: 0.3rem;
}
.form-check {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.form-check-input {
  width: 1.5rem;
  height: 1rem;
  cursor: pointer;
}
.form-check-label {
  cursor: pointer;
  font-weight: 500;
}
.form-switch .form-check-input {
  background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='-4 -4 8 8'%3e%3ccircle r='3' fill='rgba%280, 0, 0, 0.25%29'/%3e%3c/svg%3e");
  background-position: left center;
  border-radius: 2em;
  transition: background-position 0.15s ease-in-out;
}
.form-switch .form-check-input:checked {
  background-position: right center;
  background-color: #2563eb;
  border-color: #2563eb;
}
.btn {
  padding: 0.6rem 1.2rem;
  border-radius: 8px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  text-decoration: none;
  display: inline-block;
}
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-primary { background: #2563eb; color: white; }
.btn-sm { padding: 0.4rem 0.8rem; font-size: 0.85rem; }
.btn-outline-primary {
  background: transparent;
  border: 1px solid #2563eb;
  color: #2563eb;
}
.badge {
  padding: 0.35rem 0.65rem;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 0.5rem;
}
.text-bg-success { background: #dcfce7; color: #166534; }
.text-bg-danger { background: #fecaca; color: #991b1b; }
.text-bg-warning { background: #fef9c3; color: #854d0e; }
.text-bg-secondary { background: #e5e7eb; color: #374151; }
.text-muted { color: #6b7280; }
.dl-horizontal dt { text-align: right; }
.row { display: flex; flex-wrap: wrap; margin: 0 -0.5rem; }
.col-sm-3 { flex: 0 0 25%; max-width: 25%; padding: 0 0.5rem; }
.col-sm-9 { flex: 0 0 75%; max-width: 75%; padding: 0 0.5rem; }
</style>