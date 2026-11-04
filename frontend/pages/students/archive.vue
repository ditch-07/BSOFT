<script setup lang="ts">
interface ArchiveStudent {
  id: number;
  student_number: string;
  name: string;
  status: string;
  status_display: string;
  program: string | null;
  intake_year: string | null;
}

interface ArchiveResponse {
  count: number;
  total: number;
  page: number;
  pages: number;
  status_counts: Record<string, number>;
  programs: Array<{ id: number; name: string; count: number }>;
  intake_years: string[];
  results: ArchiveStudent[];
}

const route = useRoute();
const router = useRouter();
const api = useApi();
const { user } = useAuth();

function queryValue(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

const filters = reactive({
  q: queryValue(route.query.q),
  program: queryValue(route.query.program),
  intake: queryValue(route.query.intake),
});

watch(
  () => route.query,
  (query) => {
    filters.q = queryValue(query.q);
    filters.program = queryValue(query.program);
    filters.intake = queryValue(query.intake);
  },
);

const { data, pending, error } = await useAsyncData(
  'student-archive',
  () => {
    const params = new URLSearchParams();
    for (const key of ['q', 'status', 'program', 'intake', 'page'] as const) {
      const value = queryValue(route.query[key]);
      if (value) params.set(key, value);
    }
    return api.get<ArchiveResponse>(`/api/archive/students/?${params.toString()}`);
  },
  { watch: [() => route.query] },
);

const activeStatus = computed(() => queryValue(route.query.status));
const hasFilters = computed(() => Boolean(filters.q || filters.program || filters.intake || activeStatus.value));
const canRegister = computed(() => Boolean(user.value?.permissions.add_student));
const statusOptions = [
  { value: '', label: 'All students' },
  { value: 'ACTIVE', label: 'Active' },
  { value: 'DEFERRED', label: 'Deferred' },
  { value: 'WITHDRAWN', label: 'Withdrawn' },
  { value: 'COMPLETED', label: 'Completed' },
];

useHead({ title: 'Student Archive | BSoft' });

async function applyFilters() {
  const query: Record<string, string> = {};
  if (filters.q.trim()) query.q = filters.q.trim();
  if (filters.program) query.program = filters.program;
  if (filters.intake) query.intake = filters.intake;
  if (activeStatus.value) query.status = activeStatus.value;
  await router.push({ path: '/students/archive', query });
}

async function selectStatus(status: string) {
  const query: Record<string, string> = {};
  if (filters.q.trim()) query.q = filters.q.trim();
  if (filters.program) query.program = filters.program;
  if (filters.intake) query.intake = filters.intake;
  if (status) query.status = status;
  await router.push({ path: '/students/archive', query });
}

async function clearFilters() {
  filters.q = '';
  filters.program = '';
  filters.intake = '';
  await router.push('/students/archive');
}

async function goToPage(page: number) {
  await router.push({ path: '/students/archive', query: { ...route.query, page: String(page) } });
}

function statusClass(status: string): string {
  return `status-${status.toLowerCase()}`;
}
</script>

<template>
  <div class="archive-page">
    <header class="archive-heading">
      <div>
        <p class="eyebrow">People / Students</p>
        <h1>Student archive</h1>
        <p class="intro">
          <strong>{{ data?.count ?? 0 }}</strong> student file{{ data?.count === 1 ? '' : 's' }} shown
          <span v-if="data && data.count !== data.total">from {{ data.total }} on record</span>.
          Files remain here after students complete, defer, or withdraw.
        </p>
      </div>
      <div class="heading-actions">
        <NuxtLink to="/students" class="btn btn-outline-secondary">Active students</NuxtLink>
        <NuxtLink v-if="canRegister" to="/students/import" class="btn btn-outline-primary">Import students</NuxtLink>
        <NuxtLink v-if="canRegister" to="/students/new" class="btn btn-outline-primary">Register student</NuxtLink>
      </div>
    </header>

    <div v-if="error" class="alert alert-danger" role="alert">Unable to load the student archive. {{ error.message }}</div>
    <section class="filter-card" aria-labelledby="archive-filter-heading">
      <div class="filter-heading">
        <h2 id="archive-filter-heading">Find a file</h2>
        <button v-if="hasFilters" type="button" class="clear-link" @click="clearFilters">Clear filters</button>
      </div>
      <form class="filter-grid" @submit.prevent="applyFilters">
        <label class="filter-field filter-search">
          <span>Name or student number</span>
          <input v-model="filters.q" class="form-control" type="search" placeholder="Start typing a name or number">
        </label>
        <label class="filter-field">
          <span>Trade</span>
          <select v-model="filters.program" class="form-select" @change="applyFilters">
            <option value="">All trades</option>
            <option v-for="program in data?.programs ?? []" :key="program.id" :value="String(program.id)">
              {{ program.name }} ({{ program.count }})
            </option>
          </select>
        </label>
        <label class="filter-field">
          <span>Intake year</span>
          <select v-model="filters.intake" class="form-select" @change="applyFilters">
            <option value="">All intakes</option>
            <option v-for="year in data?.intake_years ?? []" :key="year" :value="year">{{ year }}</option>
          </select>
        </label>
      </form>
    </section>

    <nav class="status-filters" aria-label="Filter by student status">
      <button
        v-for="status in statusOptions"
        :key="status.value"
        type="button"
        class="status-pill"
        :class="{ active: activeStatus === status.value }"
        :aria-current="activeStatus === status.value ? 'page' : undefined"
        @click="selectStatus(status.value)"
      >
        {{ status.label }} <span>{{ status.value ? data?.status_counts[status.value] ?? 0 : data?.total ?? 0 }}</span>
      </button>
    </nav>

    <section class="archive-card" aria-labelledby="archive-list-heading">
      <div class="list-heading">
        <h2 id="archive-list-heading">Student files</h2>
        <span v-if="data && data.pages > 1">Page {{ data.page }} of {{ data.pages }}</span>
      </div>
      <div v-if="pending" class="empty-state" role="status">Loading student files…</div>
      <div v-else-if="!error" class="table-wrap">
        <table class="archive-table">
          <thead><tr><th>Student</th><th>Trade</th><th>Intake</th><th>Status</th><th><span class="visually-hidden">Actions</span></th></tr></thead>
          <tbody>
            <tr v-for="student in data?.results ?? []" :key="student.id">
              <td data-label="Student"><NuxtLink class="student-link" :to="`/students/${student.id}`">{{ student.name }}</NuxtLink><span class="student-number">{{ student.student_number }}</span></td>
              <td data-label="Trade">{{ student.program ?? 'Not assigned' }}</td>
              <td data-label="Intake">{{ student.intake_year ?? 'Not assigned' }}</td>
              <td data-label="Status"><span class="student-status" :class="statusClass(student.status)">{{ student.status_display }}</span></td>
              <td data-label="File"><NuxtLink class="btn btn-sm btn-outline-secondary" :to="`/students/${student.id}`">Open file</NuxtLink></td>
            </tr>
            <tr v-if="!data?.results.length"><td colspan="5" class="empty-state"><strong>No files match these filters.</strong><button v-if="hasFilters" class="clear-link" type="button" @click="clearFilters">Clear filters</button><span v-else>Students appear here as soon as they are registered.</span></td></tr>
          </tbody>
        </table>
      </div>
      <nav v-if="data && data.pages > 1" class="pagination" aria-label="Archive pages">
        <button class="btn btn-outline-secondary" type="button" :disabled="data.page <= 1" @click="goToPage(data.page - 1)">Previous</button>
        <span>Page {{ data.page }} of {{ data.pages }} · {{ data.count }} files</span>
        <button class="btn btn-outline-secondary" type="button" :disabled="data.page >= data.pages" @click="goToPage(data.page + 1)">Next</button>
      </nav>
    </section>
  </div>
</template>

<style scoped>
.archive-page { --ink:#1e2b33; --muted:#4e5c66; --grey:#7d878e; --line:#d6dad5; --paper:#fff; --wash:#f5f6f3; --rail:#1f4f7a; max-width:1180px; margin:0 auto; padding:1.25rem 1.5rem 2.5rem; color:var(--ink); }
.archive-heading,.heading-actions,.filter-heading,.list-heading,.pagination { display:flex; align-items:center; justify-content:space-between; gap:1rem; }
.archive-heading { align-items:flex-start; margin-bottom:1.5rem; }
.eyebrow { margin:0 0 .4rem; color:var(--muted); font-size:.75rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase; }
h1 { margin:0; font-size:clamp(2rem,1.3rem + 2.2vw,3rem); font-weight:800; letter-spacing:-.02em; }
.intro { margin:.55rem 0 0; color:var(--muted); }
.intro strong { color:var(--ink); font-variant-numeric:tabular-nums; }
.heading-actions { flex-wrap:wrap; }
.filter-card,.archive-card { margin-bottom:1rem; padding:1rem 1.15rem; border:1px solid var(--line); border-radius:10px; background:var(--paper); }
.filter-heading { margin-bottom:.75rem; }
.filter-heading h2,.list-heading h2 { margin:0; font-size:.95rem; font-weight:750; }
.clear-link { padding:0; border:0; background:none; color:var(--muted); font:inherit; font-size:.82rem; font-weight:650; text-decoration:underline; cursor:pointer; }
.filter-grid { display:grid; grid-template-columns:minmax(240px,1.4fr) minmax(160px,.8fr) minmax(140px,.6fr); gap:.75rem 1rem; align-items:end; }
.filter-field { display:flex; min-width:0; flex-direction:column; gap:.3rem; font-size:.7rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; }
.filter-field input,.filter-field select { min-height:44px; font-size:.875rem; font-weight:400; letter-spacing:normal; text-transform:none; }
.status-filters { display:flex; flex-wrap:wrap; gap:.4rem; margin-bottom:1.15rem; }
.status-pill { display:inline-flex; align-items:center; gap:.4rem; min-height:36px; padding:.45rem .75rem; border:1px solid var(--line); border-radius:999px; background:#fff; color:var(--muted); font:inherit; font-size:.8125rem; font-weight:650; cursor:pointer; }
.status-pill.active { border-color:var(--rail); background:#e5edf4; color:var(--rail); }
.status-pill span { color:var(--grey); font-size:.75rem; font-variant-numeric:tabular-nums; }
.list-heading { margin-bottom:.75rem; }
.list-heading > span,.pagination > span { color:var(--grey); font-size:.8125rem; }
.table-wrap { overflow-x:auto; }
.archive-table { width:100%; border-collapse:collapse; }
.archive-table th,.archive-table td { padding:.8rem .6rem; border-bottom:1px solid #e8ebe7; text-align:left; vertical-align:middle; }
.archive-table th { color:var(--muted); font-size:.6875rem; letter-spacing:.05em; text-transform:uppercase; }
.student-link { display:block; color:var(--rail); font-weight:700; text-decoration:none; }
.student-link:hover { text-decoration:underline; }
.student-number { color:var(--grey); font-size:.75rem; }
.student-status { display:inline-flex; padding:.3rem .6rem; border-radius:999px; background:#edf0ef; color:var(--muted); font-size:.76rem; font-weight:650; }
.status-active { background:#e7f2eb; color:#2f7d4f; }
.status-deferred { background:#fbf2df; color:#a86e06; }
.status-withdrawn { background:#edf0ef; color:#4e5c66; }
.status-completed { background:#e5edf4; color:#2c6fb0; }
.empty-state { padding:2rem 1rem !important; color:var(--muted); text-align:center !important; }
.empty-state strong,.empty-state span,.empty-state button { display:block; margin:.25rem auto; }
.pagination { margin-top:.9rem; }
@media(max-width:850px) { .filter-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.filter-search{grid-column:1/-1} }
@media(max-width:680px) { .archive-page{padding:1rem}.archive-heading{align-items:flex-start;flex-direction:column}.heading-actions{width:100%}.heading-actions>*{flex:1}.filter-grid{grid-template-columns:minmax(0,1fr)}.filter-search{grid-column:auto}.archive-table thead{display:none}.archive-table,.archive-table tbody,.archive-table tr{display:block}.archive-table tr{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.8rem 1rem;margin-bottom:.65rem;padding:1rem;border:1px solid var(--line);border-radius:10px}.archive-table td{display:block;padding:0;border:0}.archive-table td::before{content:attr(data-label);display:block;margin-bottom:.15rem;color:var(--grey);font-size:.68rem;font-weight:650;text-transform:uppercase}.archive-table td:first-child,.archive-table td:last-child{grid-column:1/-1}.archive-table td:first-child::before,.archive-table td:last-child::before{display:none}.archive-table td:first-child{padding-bottom:.55rem;border-bottom:1px solid var(--line)}.pagination{flex-wrap:wrap}.pagination span{order:3;width:100%;text-align:center} }
</style>
