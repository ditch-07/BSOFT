<script setup lang="ts">
const api = useApi();
const route = useRoute();

const data = ref<any>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const creating = ref(false);
const uploading = ref(false);
const uploadingFile = ref<File | null>(null);

async function loadBackups() {
  loading.value = true;
  error.value = null;
  try {
    const response = await api.get<any>("/api/backups/");
    data.value = response;
  } catch (e: any) {
    error.value = e.message || "Failed to load backups";
  } finally {
    loading.value = false;
  }
}

async function createBackup() {
  creating.value = true;
  try {
    const response = await api.post("/api/backups/create/", {});
    if (response.success) {
      await loadBackups();
    }
  } catch (e: any) {
    alert(e.message || "Failed to create backup");
  } finally {
    creating.value = false;
  }
}

async function restoreBackup(filename: string) {
  if (!confirm(`Are you sure you want to restore from ${filename}? This will replace the current database. A safety backup will be created first.`)) {
    return;
  }
  
  try {
    const response = await api.post(`/api/backups/restore/${encodeURIComponent(filename)}/`, {});
    if (response.success) {
      alert("Database restored successfully. Please reload the page.");
      await loadBackups();
    }
  } catch (e: any) {
    alert(e.message || "Restore failed");
  }
}

async function handleFileUpload(event: Event) {
  const input = event.target as HTMLInputElement;
  if (input.files && input.files[0]) {
    uploadingFile.value = input.files[0];
  }
}

async function uploadBackup() {
  if (!uploadingFile.value) return;
  
  uploading.value = true;
  const formData = new FormData();
  formData.append('backup_file', uploadingFile.value);
  
  try {
    const response = await api.post("/api/backups/upload/", formData);
    if (response.success) {
      uploadingFile.value = null;
      (document.getElementById('uploadFile') as HTMLInputElement).value = '';
      await loadBackups();
    }
  } catch (e: any) {
    alert(e.message || "Upload failed");
  } finally {
    uploading.value = false;
  }
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString("en-US", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function downloadBackup(filename: string) {
  window.open(`/api/backups/download/${encodeURIComponent(filename)}/`, "_blank");
}

onMounted(() => {
  loadBackups();
});
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Administration</p>
        <h1>Backup & Restore</h1>
      </div>
      <div class="d-flex gap-2">
        <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#uploadModal" :disabled="uploading">
          <i class="bi bi-upload me-1"></i> Upload Backup
        </button>
        <button class="btn btn-success" @click="createBackup" :disabled="creating">
          <i v-if="creating" class="bi bi-hourglass-split me-1"></i>
          <i v-else class="bi bi-plus-circle me-1"></i> Create Backup
        </button>
      </div>
    </section>

    <div v-if="loading" class="state-card">Loading backups…</div>
    <div v-else-if="error" class="state-card error">{{ error }}</div>
    <div v-else-if="data">
      <!-- Config Status -->
      <div class="row g-3 mb-4">
        <div class="col-12 col-md-4">
          <div class="card border-0 shadow-sm">
            <div class="card-body text-center">
              <div class="text-muted small">Backup Path</div>
              <div class="font-monospace small">{{ data.backup_path || "(default)" }}</div>
            </div>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="card border-0 shadow-sm">
            <div class="card-body text-center">
              <div class="text-muted small">Status</div>
              <span class="badge" :class="data.backup_available ? 'text-bg-success' : 'text-bg-danger'">
                {{ data.backup_available ? 'Available' : 'Unavailable' }}
              </span>
            </div>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="card border-0 shadow-sm">
            <div class="card-body text-center">
              <div class="text-muted small">Auto Backup</div>
              <span class="badge" :class="data.config.auto_backup_enabled ? 'text-bg-success' : 'text-bg-secondary'">
                {{ data.config.auto_backup_enabled ? 'Enabled' : 'Disabled' }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Backups List -->
      <div class="card border-0 shadow-sm">
        <div class="card-body">
          <div v-if="data.backups.length">
            <div class="table-responsive">
              <table class="table table-hover align-middle mb-0">
                <thead class="table-light">
                  <tr>
                    <th>Filename</th>
                    <th>Modified</th>
                    <th>Size</th>
                    <th class="text-end">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="backup in data.backups" :key="backup.name">
                    <td class="font-monospace">{{ backup.name }}</td>
                    <td>{{ formatDate(backup.modified) }}</td>
                    <td>{{ formatBytes(backup.size) }}</td>
                    <td class="text-end">
                      <div class="btn-group btn-group-sm">
                        <a :href="`/api/backups/download/${encodeURIComponent(backup.name)}/`" class="btn btn-outline-secondary" title="Download">
                          <i class="bi bi-download"></i>
                        </a>
                        <button class="btn btn-outline-warning" @click="restoreBackup(backup.name)" title="Restore">
                          <i class="bi bi-arrow-counterclockwise"></i>
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div v-else class="text-center py-5">
            <i class="bi bi-hdd-stack display-4 text-muted"></i>
            <p class="mt-3 text-muted">No backups found.</p>
            <button class="btn btn-success" @click="createBackup" :disabled="creating">
              <i v-if="creating" class="bi bi-hourglass-split me-1"></i>
              <i v-else class="bi bi-plus-circle me-1"></i> Create First Backup
            </button>
          </div>
        </div>
      </div>

      <NuxtLink to="/backup/settings" class="btn btn-outline-primary mt-3">
        <i class="bi bi-gear me-1"></i> Backup Settings
      </NuxtLink>
    </div>
  </div>

  <!-- Upload Modal -->
  <div class="modal fade" id="uploadModal" tabindex="-1" aria-labelledby="uploadModalLabel" aria-hidden="true">
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title" id="uploadModalLabel">Upload Backup</h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
        </div>
        <div class="modal-body">
          <div class="mb-3">
            <label for="uploadFile" class="form-label">Select Backup File</label>
            <input type="file" id="uploadFile" ref="uploadFile" @change="handleFileUpload" class="form-control" accept=".sqlite3,.db" required>
            <div class="form-text">Choose a <code>.sqlite3</code> or <code>.db</code> file from your local machine.</div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
          <button type="button" class="btn btn-primary" @click="uploadBackup" :disabled="uploading || !uploadingFile">
            <span v-if="uploading" class="spinner-border spinner-border-sm me-1"></span>
            Upload
          </button>
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
.text-end { text-align: right; }
.text-muted { color: #6b7280; }
.font-monospace { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
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
.form-text {
  font-size: 0.8rem;
  color: #6b7280;
  margin-top: 0.3rem;
}
.row { display: flex; flex-wrap: wrap; margin: 0 -0.5rem; }
.g-3 { gap: 1rem; }
.col-12, .col-md-4 {
  padding: 0 0.5rem;
}
.col-12 { flex: 0 0 100%; max-width: 100%; }
.col-md-4 { flex: 0 0 33.333%; max-width: 33.333%; }
@media (max-width: 768px) {
  .col-md-4 { flex: 0 0 100%; max-width: 100%; }
}
.d-flex { display: flex; }
.gap-2 { gap: 0.5rem; }
.btn {
  padding: 0.5rem 1rem;
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
.btn-success { background: #16a34a; color: white; }
.btn-outline-secondary {
  background: transparent;
  border: 1px solid #d1d5db;
  color: #374151;
}
.btn-outline-warning {
  background: transparent;
  border: 1px solid #f59e0b;
  color: #f59e0b;
}
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
.text-bg-secondary { background: #e5e7eb; color: #374151; }
.btn-group { display: inline-flex; }
.btn-group-sm .btn { padding: 0.25rem 0.5rem; font-size: 0.85rem; }
.display-4 { font-size: 2.5rem; }
.mt-3 { margin-top: 1rem; }
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