<script setup lang="ts">
interface Option {
  id: number;
  name: string;
}

interface Semester extends Option {
  academic_year_id: number;
  status: string;
}

interface LookupResponse<T> {
  count: number;
  results: T[];
}

interface ImportRow {
  row_number: number;
  student_number: string;
  first_name: string;
  last_name: string;
  program_code: string;
  program_name?: string;
  program_id?: number;
  errors?: string[];
}

interface ImportPreview {
  preview_id: string;
  valid_rows: ImportRow[];
  invalid_rows: ImportRow[];
  valid_count: number;
  invalid_count: number;
  intake_year: string;
  semester: string;
  year_level: number;
  default_status: string;
}

const api = useApi();
const { user } = useAuth();
const fileInput = ref<HTMLInputElement | null>(null);
const file = ref<File | null>(null);
const preview = ref<ImportPreview | null>(null);
const previewError = ref('');
const confirming = ref(false);
const resultMessage = ref('');
const form = reactive({
  intake_year: '',
  semester: '',
  year_level: '1',
  default_status: 'ACTIVE',
});

const { data: options, pending: optionsPending, error: optionsError } = await useAsyncData(
  'student-import-options',
  async () => {
    const [years, semesters] = await Promise.all([
      api.get<LookupResponse<Option>>('/api/academic-years/'),
      api.get<LookupResponse<Semester>>('/api/semesters/'),
    ]);
    return { years: years.results, semesters: semesters.results };
  },
);

const availableSemesters = computed(() => options.value?.semesters
  .filter(semester => !form.intake_year || String(semester.academic_year_id) === form.intake_year) ?? []);
const canImport = computed(() => Boolean(user.value?.permissions.add_student));
const yearLevels = Array.from({ length: 6 }, (_, index) => String(index + 1));

watch(
  availableSemesters,
  (semesters) => {
    if (!semesters.some(semester => String(semester.id) === form.semester)) {
      form.semester = semesters[0] ? String(semesters[0].id) : '';
    }
  },
  { immediate: true },
);

useHead({ title: 'Import Students | BSoft' });

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function responseMessage(error: unknown): string {
  if (!isRecord(error)) return 'The request could not be completed.';
  if (isRecord(error.data)) {
    if (typeof error.data.detail === 'string') return error.data.detail;
    if (isRecord(error.data.errors)) {
      const messages = Object.values(error.data.errors).flatMap((value) => {
        if (!Array.isArray(value)) return [];
        return value.map((item) => {
          if (typeof item === 'string') return item;
          if (isRecord(item) && typeof item.message === 'string') return item.message;
          return '';
        }).filter(Boolean);
      });
      if (messages.length) return messages.join(' ');
    }
  }
  return typeof error.message === 'string' ? error.message : 'The request could not be completed.';
}

function selectFile(event: Event) {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) return;
  file.value = target.files?.[0] ?? null;
  preview.value = null;
  resultMessage.value = '';
  previewError.value = '';
}

async function requestPreview() {
  previewError.value = '';
  resultMessage.value = '';
  if (!file.value) {
    previewError.value = 'Choose a .csv or .xlsx spreadsheet first.';
    return;
  }

  const body = new FormData();
  body.set('file', file.value);
  body.set('intake_year', form.intake_year);
  body.set('semester', form.semester);
  body.set('year_level', form.year_level);
  body.set('default_status', form.default_status);

  try {
    preview.value = await api.post<ImportPreview>('/api/students/import/preview/', body);
  } catch (error: unknown) {
    previewError.value = responseMessage(error);
  }
}

async function confirmImport() {
  if (!preview.value) return;
  confirming.value = true;
  previewError.value = '';
  try {
    const result = await api.post<{
      created_count: number;
      skipped: string[];
      skipped_count: number;
    }>('/api/students/import/confirm/', { preview_id: preview.value.preview_id });
    resultMessage.value = result.skipped_count
      ? `Imported ${result.created_count} student(s). Skipped ${result.skipped_count} duplicate or no-longer-valid row(s): ${result.skipped.join(', ')}.`
      : `Imported ${result.created_count} student(s) successfully.`;
    preview.value = null;
    file.value = null;
    if (fileInput.value) fileInput.value.value = '';
  } catch (error: unknown) {
    previewError.value = responseMessage(error);
  } finally {
    confirming.value = false;
  }
}

function startOver() {
  preview.value = null;
  previewError.value = '';
  if (fileInput.value) fileInput.value.value = '';
  file.value = null;
}
</script>

<template>
  <div class="import-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">People / Students</p>
        <h1>Import students</h1>
        <p class="intro">Upload a spreadsheet with student number, surname, name, and trade. Other details can be added from each student’s edit page.</p>
      </div>
      <NuxtLink to="/students" class="btn btn-outline-secondary">Back to students</NuxtLink>
    </header>

    <div v-if="!canImport" class="alert alert-danger" role="alert">Your account does not have permission to import students.</div>
    <div v-else-if="optionsPending" class="import-card" role="status">Loading academic years and semesters…</div>
    <div v-else-if="optionsError" class="alert alert-danger" role="alert">Unable to load import options. {{ optionsError.message }}</div>
    <template v-else>
      <div v-if="previewError" class="alert alert-danger" role="alert">{{ previewError }}</div>
      <div v-if="resultMessage" class="alert alert-success" role="status">{{ resultMessage }}</div>

      <form v-if="!preview" class="import-card import-form" @submit.prevent="requestPreview">
        <label class="field field-wide">
          <span>Spreadsheet (.xlsx or .csv)</span>
          <input ref="fileInput" class="form-control" type="file" accept=".xlsx,.csv" required @change="selectFile">
          <small>Required columns are detected from the header row. The importer accepts common variations such as “Student No”, “Surname”, “Name”, and “Trade”.</small>
        </label>
        <div class="field-grid">
          <label class="field">
            <span>Intake year *</span>
            <select v-model="form.intake_year" class="form-select" required>
              <option value="">Choose an academic year</option>
              <option v-for="year in options?.years ?? []" :key="year.id" :value="String(year.id)">{{ year.name }}</option>
            </select>
          </label>
          <label class="field">
            <span>Starting semester *</span>
            <select v-model="form.semester" class="form-select" required :disabled="!availableSemesters.length">
              <option value="">Choose a semester</option>
              <option v-for="semester in availableSemesters" :key="semester.id" :value="String(semester.id)">{{ semester.name }}</option>
            </select>
          </label>
          <label class="field">
            <span>Starting year level *</span>
            <select v-model="form.year_level" class="form-select" required>
              <option v-for="level in yearLevels" :key="level" :value="level">Year {{ level }}</option>
            </select>
          </label>
          <label class="field">
            <span>Status to assign</span>
            <select v-model="form.default_status" class="form-select">
              <option value="ACTIVE">Active</option>
              <option value="DEFERRED">Deferred</option>
              <option value="WITHDRAWN">Withdrawn</option>
              <option value="COMPLETED">Completed</option>
            </select>
          </label>
        </div>
        <div v-if="form.intake_year && !availableSemesters.length" class="alert alert-warning mb-0">
          No semesters are available for this academic year.
        </div>
        <footer class="form-actions">
          <NuxtLink to="/students" class="btn btn-outline-secondary">Cancel</NuxtLink>
          <button type="submit" class="btn btn-primary" :disabled="!file || !form.intake_year || !form.semester">Preview import</button>
        </footer>
      </form>

      <template v-else>
        <div class="alert alert-info">
          Found <strong>{{ preview.valid_count }}</strong> row(s) ready to import into <strong>{{ preview.intake_year }}</strong>,
          <strong>{{ preview.semester }}</strong>, year level <strong>{{ preview.year_level }}</strong>.
          <span v-if="preview.invalid_count"><strong>{{ preview.invalid_count }}</strong> row(s) will be skipped; details are below.</span>
        </div>

        <section v-if="preview.valid_rows.length" class="import-card">
          <h2>Will be imported ({{ preview.valid_count }})</h2>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Row</th><th>Student No</th><th>Surname</th><th>Name</th><th>Trade</th></tr></thead>
              <tbody>
                <tr v-for="row in preview.valid_rows" :key="`${row.row_number}-${row.student_number}`">
                  <td>{{ row.row_number }}</td><td>{{ row.student_number }}</td><td>{{ row.last_name }}</td><td>{{ row.first_name }}</td>
                  <td>{{ row.program_code }} → {{ row.program_name }} ({{ row.program_code }})</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="preview.invalid_rows.length" class="import-card">
          <h2>Will be skipped ({{ preview.invalid_count }})</h2>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Row</th><th>Student No</th><th>Surname</th><th>Name</th><th>Trade</th><th>Reason</th></tr></thead>
              <tbody>
                <tr v-for="row in preview.invalid_rows" :key="`${row.row_number}-${row.student_number}`" class="invalid-row">
                  <td>{{ row.row_number }}</td><td>{{ row.student_number }}</td><td>{{ row.last_name }}</td><td>{{ row.first_name }}</td>
                  <td>{{ row.program_code }}</td><td>{{ row.errors?.join('; ') }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <footer class="form-actions import-card">
          <button type="button" class="btn btn-outline-secondary" :disabled="confirming" @click="startOver">Start over</button>
          <button v-if="preview.valid_count" type="button" class="btn btn-success" :disabled="confirming" @click="confirmImport">
            {{ confirming ? 'Importing…' : `Confirm — Import ${preview.valid_count} Student(s)` }}
          </button>
        </footer>
      </template>
    </template>
  </div>
</template>

<style scoped>
.import-page { --ink:#1e2b33; --muted:#4e5c66; --line:#d6dad5; --rail:#1f4f7a; max-width:1180px; margin:0 auto; padding:1.25rem 1.5rem 2rem; color:var(--ink); }
.page-heading,.form-actions { display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; }
.page-heading { margin-bottom:1.5rem; }
.eyebrow { margin:0 0 .35rem; color:var(--muted); font-size:.75rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase; }
h1 { margin:0; font-size:clamp(1.6rem,3vw,2rem); font-weight:800; text-transform:uppercase; }
.intro { max-width:720px; margin:.45rem 0 0; color:var(--muted); }
.import-form { display:grid; gap:1rem; }
.import-card { margin-bottom:1rem; padding:1.15rem; border:1px solid var(--line); border-radius:10px; background:#fff; }
.field-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:1rem; }
.field { display:flex; min-width:0; flex-direction:column; gap:.35rem; margin:0; font-size:.875rem; font-weight:650; }
.field-wide { grid-column:1/-1; }
.field small { color:var(--muted); font-size:.78rem; font-weight:400; }
.form-actions { align-items:center; }
.form-actions.import-card { margin-top:1rem; }
.btn-primary { border-color:var(--rail); background:var(--rail); }
.btn-primary:hover { border-color:#163b5c; background:#163b5c; }
h2 { margin:0 0 1rem; font-size:1.05rem; font-weight:750; }
.table-wrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; }
th,td { padding:.7rem .55rem; border-bottom:1px solid #e8ebe7; text-align:left; vertical-align:top; }
th { color:var(--muted); font-size:.7rem; letter-spacing:.04em; text-transform:uppercase; }
.invalid-row { background:#fbf2df; }
@media(max-width:850px) { .field-grid{grid-template-columns:repeat(2,minmax(0,1fr))} }
@media(max-width:650px) { .import-page{padding:1rem}.page-heading{flex-direction:column}.field-grid{grid-template-columns:minmax(0,1fr)}.field-wide{grid-column:auto}.form-actions{flex-wrap:wrap}.form-actions>*{flex:1} }
</style>
