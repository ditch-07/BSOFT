<script setup lang="ts">
const api = useApi();
const route = useRoute();

const data = ref<any>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const editingUser = ref<any>(null);

async function loadUsers() {
  loading.value = true;
  error.value = null;
  try {
    const params = new URLSearchParams();
    params.set("page", String(route.query.page || 1));
    const response = await api.get<any>(`/api/users/?${params.toString()}`);
    data.value = response;
  } catch (e: any) {
    error.value = e.message || "Failed to load users";
  } finally {
    loading.value = false;
  }
}

async function toggleUserStatus(user: any) {
  if (user.is_superuser && user.id === editingUser.value?.id) {
    alert("Cannot deactivate your own account.");
    return;
  }
  
  const newStatus = !user.is_active;
  try {
    await api.patch(`/api/users/${user.id}/`, { is_active: newStatus });
    await loadUsers();
  } catch (e: any) {
    alert(e.message || "Failed to update user status");
  }
}

async function toggleStaffStatus(user: any) {
  const newStatus = !user.is_staff;
  try {
    await api.patch(`/api/users/${user.id}/`, { is_staff: newStatus });
    await loadUsers();
  } catch (e: any) {
    alert(e.message || "Failed to update staff status");
  }
}

async function editUserGroups(user: any) {
  editingUser.value = { ...user };
}

async function saveUserGroups() {
  if (!editingUser.value) return;
  
  try {
    const groupId = editingUser.value.groups.length > 0 ? editingUser.value.groups[0].id : null;
    await api.patch(`/api/users/${editingUser.value.id}/`, { group: groupId });
    editingUser.value = null;
    await loadUsers();
  } catch (e: any) {
    alert(e.message || "Failed to update user groups");
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleString("en-US", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function getRoleBadge(groups: any[]): string {
  if (groups.length === 0) return '<span class="badge bg-secondary">No role</span>';
  return groups.map(g => `<span class="badge bg-primary">${g.name}</span>`).join(' ');
}

watch(() => route.query.page, (val) => {
  if (val) {
    loadUsers();
  }
});

onMounted(() => {
  loadUsers();
});
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Administration</p>
        <h1>User Management</h1>
      </div>
      <NuxtLink to="/users/new" class="primary-link">+ Add User</NuxtLink>
    </section>

    <div v-if="loading" class="state-card">Loading users…</div>
    <div v-else-if="error" class="state-card error">{{ error }}</div>
    <div v-else-if="data">
      <div class="card border-0 shadow-sm">
        <div class="card-body p-0">
          <div class="table-responsive">
            <table class="table table-hover align-middle mb-0">
              <thead class="table-light">
                <tr>
                  <th>Username</th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Staff</th>
                  <th>Superuser</th>
                  <th>Active</th>
                  <th>Date Joined</th>
                  <th>Last Login</th>
                  <th class="text-end">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="user in data.results" :key="user.id">
                  <td class="fw-bold">{{ user.username }}</td>
                  <td>{{ user.first_name }} {{ user.last_name }}</td>
                  <td>{{ user.email || "—" }}</td>
                  <td v-html="getRoleBadge(user.groups)"></td>
                  <td>
                    <input type="checkbox" :checked="user.is_staff" @change="toggleStaffStatus(user)" :disabled="user.is_superuser && user.id === editingUser.value?.id" class="form-check-input" style="width: 1.25rem; height: 1.25rem;">
                  </td>
                  <td>
                    <span v-if="user.is_superuser" class="badge bg-danger">Yes</span>
                    <span v-else class="text-muted">No</span>
                  </td>
                  <td>
                    <input type="checkbox" :checked="user.is_active" @change="toggleUserStatus(user)" :disabled="user.is_superuser && user.id === editingUser.value?.id" class="form-check-input" style="width: 1.25rem; height: 1.25rem;">
                  </td>
                  <td>{{ formatDate(user.date_joined) }}</td>
                  <td>{{ formatDate(user.last_login) }}</td>
                  <td class="text-end">
                    <div class="btn-group btn-group-sm">
                      <button v-if="!editingUser.value || editingUser.value.id !== user.id" class="btn btn-outline-secondary" @click="editUserGroups(user)" title="Edit Role">
                        <i class="bi bi-people"></i>
                      </button>
                      <div v-else class="btn-group btn-group-sm">
                        <select v-model="editingUser.groups" class="form-select form-select-sm" style="width: auto;">
                          <option value="">— No Role —</option>
                          <option v-for="g in data.all_groups" :key="g.id" :value="[{ id: g.id, name: g.name }]">{{ g.name }}</option>
                        </select>
                        <button class="btn btn-success" @click="saveUserGroups" title="Save">
                          <i class="bi bi-check"></i>
                        </button>
                        <button class="btn btn-outline-secondary" @click="editingUser = null" title="Cancel">
                          <i class="bi bi-x"></i>
                        </button>
                      </div>
                    </div>
                  </td>
                </tr>
                <tr v-if="!data.results.length">
                  <td colspan="10" class="text-center text-muted py-4">No users found.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-if="data.pages > 1" class="card-footer bg-white">
          <nav>
            <ul class="pagination justify-content-center mb-0">
              <li v-if="data.page > 1" class="page-item">
                <a class="page-link" :href="`/users/?page=${data.page - 1}`">&laquo; Previous</a>
              </li>
              <li class="page-item disabled">
                <span class="page-link">Page {{ data.page }} of {{ data.pages }} ({{ data.count }} users)</span>
              </li>
              <li v-if="data.page < data.pages" class="page-item">
                <a class="page-link" :href="`/users/?page=${data.page + 1}`">Next &raquo;</a>
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
.text-end { text-align: right; }
.text-muted { color: #6b7280; }
.fw-bold { font-weight: 700; }
.small { font-size: 0.85rem; }
.form-check-input { cursor: pointer; }
.btn-group { display: inline-flex; }
.btn-group-sm .btn { padding: 0.25rem 0.5rem; font-size: 0.85rem; }
.btn-outline-secondary {
  background: transparent;
  border: 1px solid #d1d5db;
  color: #374151;
}
.btn-success { background: #16a34a; color: white; }
.btn-primary { background: #2563eb; color: white; }
.badge {
  padding: 0.35rem 0.65rem;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 0.5rem;
}
.bg-danger { background: #fecaca; color: #991b1b; }
.bg-primary { background: #dbeafe; color: #1e40af; }
.bg-secondary { background: #e5e7eb; color: #374151; }
.form-select {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 0.4rem 0.6rem;
  font-size: 0.85rem;
}
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
</style>