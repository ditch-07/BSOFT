<script setup lang="ts">
const api = useApi();
const router = useRouter();

const form = reactive({
  username: "",
  password: "",
  group: "",
  is_staff: false,
});

const errors = ref<Record<string, string[]>>({});
const submitting = ref(false);
const groups = ref<any[]>([]);

async function loadGroups() {
  try {
    const response = await api.get<{ all_groups: any[] }>("/api/users/");
    groups.value = response.all_groups ?? [];
  } catch (e) {
    console.error("Failed to load groups:", e);
  }
}

function validateForm(): boolean {
  const newErrors: Record<string, string[]> = {};
  if (!form.username.trim()) newErrors.username = ["Username is required."];
  if (!form.password) newErrors.password = ["Password is required."];
  else if (form.password.length < 8) newErrors.password = ["Password must be at least 8 characters."];
  errors.value = newErrors;
  return Object.keys(newErrors).length === 0;
}

async function submitForm() {
  if (!validateForm()) return;

  submitting.value = true;
  errors.value = {};

  try {
    await api.post("/api/users/create/", {
      username: form.username,
      password: form.password,
      group: form.group || null,
      is_staff: form.is_staff,
    });
    router.push("/users");
  } catch (e: any) {
    if (e.response?._data?.errors) {
      errors.value = e.response._data.errors;
    } else {
      errors.value = { detail: [e.message || "Failed to create user."] };
    }
  } finally {
    submitting.value = false;
  }
}

onMounted(() => {
  loadGroups();
});
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Administration</p>
        <h1>Create User</h1>
      </div>
      <NuxtLink to="/users" class="secondary-link">← Back to Users</NuxtLink>
    </section>

    <div v-if="submitting" class="state-card">Creating user…</div>
    <div v-else-if="errors.detail" class="state-card error">{{ errors.detail[0] }}</div>

    <div class="card border-0 shadow-sm">
      <div class="card-body">
        <form @submit.prevent="submitForm" novalidate>
          <div class="mb-3">
            <label for="username" class="form-label fw-semibold required">Username</label>
            <input
              type="text"
              id="username"
              v-model="form.username"
              class="form-control"
              placeholder="e.g. jdoe"
              :class="{ 'is-invalid': errors.username }"
              required
            >
            <div v-if="errors.username" class="invalid-feedback d-block">{{ errors.username[0] }}</div>
          </div>

          <div class="mb-3">
            <label for="password" class="form-label fw-semibold required">Password</label>
            <input
              type="password"
              id="password"
              v-model="form.password"
              class="form-control"
              placeholder="Enter temporary password"
              :class="{ 'is-invalid': errors.password }"
              required
            >
            <div class="form-text">Temporary password - user should change on first login. Minimum 8 characters.</div>
            <div v-if="errors.password" class="invalid-feedback d-block">{{ errors.password[0] }}</div>
          </div>

          <div class="mb-3">
            <label for="group" class="form-label fw-semibold">Role Group</label>
            <select
              id="group"
              v-model="form.group"
              class="form-select"
            >
              <option value="">— No Role —</option>
              <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
            </select>
            <div class="form-text">Assign to a role group (Registrar, Finance, Academic)</div>
          </div>

          <div class="mb-3 form-check">
            <input
              type="checkbox"
              id="is_staff"
              v-model="form.is_staff"
              class="form-check-input"
            >
            <label class="form-check-label" for="is_staff">Can access Django admin</label>
            <div class="form-text">Staff users can access the Django admin interface.</div>
          </div>

          <div class="d-flex gap-2">
            <button type="submit" class="btn btn-primary" :disabled="submitting">
              <span v-if="submitting">Creating…</span>
              <span v-else>Create User</span>
            </button>
            <NuxtLink to="/users" class="btn btn-outline-secondary">Cancel</NuxtLink>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-shell {
  display: grid;
  gap: 1.25rem;
  padding: 1.5rem;
  max-width: 600px;
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
.form-label.required::after {
  content: " *";
  color: #dc2626;
}
.form-control, .form-select {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 0.6rem 0.8rem;
  width: 100%;
}
.form-control.is-invalid, .form-select.is-invalid {
  border-color: #dc2626;
}
.form-text {
  font-size: 0.8rem;
  color: #6b7280;
  margin-top: 0.3rem;
}
.invalid-feedback {
  color: #dc2626;
  font-size: 0.85rem;
}
.form-check {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.form-check-input {
  width: 1.125rem;
  height: 1.125rem;
  cursor: pointer;
}
.form-check-label {
  cursor: pointer;
  font-weight: 500;
}
.d-flex { display: flex; }
.gap-2 { gap: 0.5rem; }
.mb-3 { margin-bottom: 1rem; }
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
.btn-outline-secondary {
  background: transparent;
  border: 1px solid #d1d5db;
  color: #374151;
}
</style>