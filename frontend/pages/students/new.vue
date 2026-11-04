<script setup lang="ts">
interface LookupItem {
  id: number;
  name: string;
}

interface Program extends LookupItem {
  code: string;
  duration_years: number;
}

interface Semester extends LookupItem {
  status: string;
}

interface LookupResponse<T> {
  count: number;
  results: T[];
}

interface StudentCreateForm {
  student_number: string;
  first_name: string;
  last_name: string;
  national_id: string;
  date_of_birth: string;
  gender: string;
  guardian_name: string;
  guardian_phone: string;
  student_phone: string;
  address: string;
  program: string;
  intake_year: string;
  status: string;
  semester: string;
  year_level: number;
}

const api = useApi();
const router = useRouter();
const { user } = useAuth();
const isSubmitting = ref(false);
const submitError = ref('');
const fieldErrors = ref<Record<string, string[]>>({});
const form = reactive<StudentCreateForm>({
  student_number: '',
  first_name: '',
  last_name: '',
  national_id: '',
  date_of_birth: '',
  gender: '',
  guardian_name: '',
  guardian_phone: '',
  student_phone: '',
  address: '',
  program: '',
  intake_year: '',
  status: 'ACTIVE',
  semester: '',
  year_level: 1,
});

const { data: options, pending: optionsPending, error: optionsError } = await useAsyncData(
  'student-registration-options',
  async () => {
    const [programs, years, semesters] = await Promise.all([
      api.get<LookupResponse<Program>>('/api/programs/'),
      api.get<LookupResponse<LookupItem>>('/api/academic-years/'),
      api.get<LookupResponse<Semester>>('/api/semesters/'),
    ]);

    return {
      programs: programs.results,
      years: years.results,
      semesters: semesters.results.filter(semester => ['ACTIVE', 'UPCOMING'].includes(semester.status)),
    };
  },
);

const selectedProgram = computed(() => options.value?.programs.find(program => String(program.id) === form.program));
const yearLevels = computed(() => Array.from(
  { length: selectedProgram.value?.duration_years ?? 0 },
  (_, index) => index + 1,
));

watch(
  () => options.value?.semesters,
  (semesters) => {
    if (!form.semester && semesters?.length) form.semester = String(semesters[0].id);
  },
  { immediate: true },
);

watch(selectedProgram, (program) => {
  if (program && form.year_level > program.duration_years) form.year_level = 1;
});

const canRegister = computed(() => Boolean(user.value?.permissions.add_student));
const canSubmit = computed(() => !isSubmitting.value && !optionsPending.value && Boolean(options.value?.semesters.length));

useHead({ title: 'Register Student | BSoft' });

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function readRequestError(error: unknown) {
  if (!isRecord(error)) return { summary: 'Unable to register this student. Please try again.', fields: {} };

  const body = isRecord(error.data) ? error.data : {};
  const rawErrors = isRecord(body.errors) ? body.errors : {};
  const fields: Record<string, string[]> = {};

  for (const [field, value] of Object.entries(rawErrors)) {
    const messages = Array.isArray(value)
      ? value.map((entry) => {
          if (typeof entry === 'string') return entry;
          if (isRecord(entry) && typeof entry.message === 'string') return entry.message;
          return '';
        }).filter(Boolean)
      : typeof value === 'string' ? [value] : [];
    if (messages.length) fields[field] = messages;
  }

  const summary = typeof body.detail === 'string'
    ? body.detail
    : typeof error.message === 'string' ? error.message : 'Please check the highlighted details.';
  return { summary, fields };
}

function resetForm() {
  Object.assign(form, {
    student_number: '',
    first_name: '',
    last_name: '',
    national_id: '',
    date_of_birth: '',
    gender: '',
    guardian_name: '',
    guardian_phone: '',
    student_phone: '',
    address: '',
    program: '',
    intake_year: '',
    status: 'ACTIVE',
    semester: options.value?.semesters[0] ? String(options.value.semesters[0].id) : '',
    year_level: 1,
  });
  fieldErrors.value = {};
  submitError.value = '';
}

async function submitStudent(addAnother = false) {
  submitError.value = '';
  fieldErrors.value = {};
  isSubmitting.value = true;

  try {
    const student = await api.post<{ id: number }>('/api/students/create/', {
      student_number: form.student_number.trim(),
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      national_id: form.national_id.trim(),
      date_of_birth: form.date_of_birth || null,
      gender: form.gender,
      guardian_name: form.guardian_name.trim(),
      guardian_phone: form.guardian_phone.trim(),
      student_phone: form.student_phone.trim(),
      address: form.address.trim(),
      program: form.program,
      intake_year: form.intake_year,
      status: form.status,
      semester: form.semester,
      year_level: form.year_level,
    });

    if (addAnother) {
      resetForm();
    } else {
      await router.push(`/students/${student.id}`);
    }
  } catch (error: unknown) {
    const result = readRequestError(error);
    submitError.value = result.summary;
    fieldErrors.value = result.fields;
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<template>
  <div class="registration-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">People / Students</p>
        <h1>Register student</h1>
        <p class="intro">Enter the student’s details and starting enrolment.</p>
      </div>
      <NuxtLink to="/students" class="btn btn-outline-secondary">Back to students</NuxtLink>
    </header>

    <div v-if="!canRegister" class="alert alert-danger" role="alert">
      Your account does not have permission to register students.
    </div>
    <div v-else-if="optionsPending" class="registration-card" role="status">Loading registration options…</div>
    <div v-else-if="optionsError" class="alert alert-danger" role="alert">
      Unable to load programs, academic years, and semesters. {{ optionsError.message }}
    </div>
    <form v-else class="registration-form" @submit.prevent="submitStudent()">
      <div v-if="submitError" class="alert alert-danger" role="alert">
        <strong>{{ submitError }}</strong>
        <ul v-if="Object.keys(fieldErrors).length" class="mb-0 mt-2">
          <li v-for="(messages, field) in fieldErrors" :key="field">{{ field.replaceAll('_', ' ') }}: {{ messages.join(', ') }}</li>
        </ul>
      </div>

      <section class="registration-card" aria-labelledby="personal-heading">
        <div class="section-heading">
          <div><h2 id="personal-heading">Personal details</h2><p>Use the spelling shown on the student’s documents.</p></div>
          <span class="section-number">1</span>
        </div>
        <div class="field-grid">
          <label class="field">
            <span>Student number <b aria-hidden="true">*</b></span>
            <input v-model="form.student_number" class="form-control" required maxlength="30" placeholder="e.g. 002/ECS/2026">
            <small>Use the number printed on the student file.</small>
            <span v-if="fieldErrors.student_number" class="field-error">{{ fieldErrors.student_number.join(', ') }}</span>
          </label>
          <label class="field">
            <span>First names <b aria-hidden="true">*</b></span>
            <input v-model="form.first_name" class="form-control" required maxlength="100" autocomplete="given-name" placeholder="First and middle names">
            <span v-if="fieldErrors.first_name" class="field-error">{{ fieldErrors.first_name.join(', ') }}</span>
          </label>
          <label class="field">
            <span>Last name <b aria-hidden="true">*</b></span>
            <input v-model="form.last_name" class="form-control" required maxlength="100" autocomplete="family-name" placeholder="Surname">
            <span v-if="fieldErrors.last_name" class="field-error">{{ fieldErrors.last_name.join(', ') }}</span>
          </label>
          <label class="field">
            <span>National ID</span>
            <input v-model="form.national_id" class="form-control" maxlength="100" placeholder="63-123456 A 42">
            <span v-if="fieldErrors.national_id" class="field-error">{{ fieldErrors.national_id.join(', ') }}</span>
          </label>
          <label class="field">
            <span>Date of birth</span>
            <input v-model="form.date_of_birth" class="form-control" type="date" min="1900-01-01" :max="new Date().toISOString().slice(0, 10)">
            <span v-if="fieldErrors.date_of_birth" class="field-error">{{ fieldErrors.date_of_birth.join(', ') }}</span>
          </label>
          <label class="field">
            <span>Gender</span>
            <select v-model="form.gender" class="form-select">
              <option value="">Not specified</option>
              <option value="MALE">Male</option>
              <option value="FEMALE">Female</option>
            </select>
            <span v-if="fieldErrors.gender" class="field-error">{{ fieldErrors.gender.join(', ') }}</span>
          </label>
        </div>
      </section>

      <section class="registration-card" aria-labelledby="contact-heading">
        <div class="section-heading">
          <div><h2 id="contact-heading">Contact and guardian</h2><p>Phone numbers are saved in the same Zimbabwe format.</p></div>
          <span class="section-number">2</span>
        </div>
        <div class="field-grid">
          <label class="field">
            <span>Student phone</span>
            <input v-model="form.student_phone" class="form-control" type="tel" maxlength="30" placeholder="+263 77 123 4567">
            <span v-if="fieldErrors.student_phone" class="field-error">{{ fieldErrors.student_phone.join(', ') }}</span>
          </label>
          <label class="field">
            <span>Guardian name</span>
            <input v-model="form.guardian_name" class="form-control" maxlength="150" placeholder="Guardian’s full name">
            <span v-if="fieldErrors.guardian_name" class="field-error">{{ fieldErrors.guardian_name.join(', ') }}</span>
          </label>
          <label class="field">
            <span>Guardian phone</span>
            <input v-model="form.guardian_phone" class="form-control" type="tel" maxlength="30" placeholder="+263 77 123 4567">
            <span v-if="fieldErrors.guardian_phone" class="field-error">{{ fieldErrors.guardian_phone.join(', ') }}</span>
          </label>
          <label class="field field-wide">
            <span>Home address</span>
            <textarea v-model="form.address" class="form-control" rows="3" placeholder="Home address" />
            <span v-if="fieldErrors.address" class="field-error">{{ fieldErrors.address.join(', ') }}</span>
          </label>
        </div>
      </section>

      <section class="registration-card" aria-labelledby="enrolment-heading">
        <div class="section-heading">
          <div><h2 id="enrolment-heading">Trade and enrolment</h2><p>These choices determine the student’s enrolment and fees.</p></div>
          <span class="section-number">3</span>
        </div>
        <div class="field-grid">
          <label class="field">
            <span>Trade <b aria-hidden="true">*</b></span>
            <select v-model="form.program" class="form-select" required>
              <option value="">Choose a trade</option>
              <option v-for="program in options?.programs ?? []" :key="program.id" :value="String(program.id)">{{ program.name }} ({{ program.code }})</option>
            </select>
            <span v-if="fieldErrors.program" class="field-error">{{ fieldErrors.program.join(', ') }}</span>
          </label>
          <label class="field">
            <span>Intake year <b aria-hidden="true">*</b></span>
            <select v-model="form.intake_year" class="form-select" required>
              <option value="">Choose an academic year</option>
              <option v-for="year in options?.years ?? []" :key="year.id" :value="String(year.id)">{{ year.name }}</option>
            </select>
            <span v-if="fieldErrors.intake_year" class="field-error">{{ fieldErrors.intake_year.join(', ') }}</span>
          </label>
          <label class="field">
            <span>Status</span>
            <select v-model="form.status" class="form-select">
              <option value="ACTIVE">Active</option>
              <option value="DEFERRED">Deferred</option>
              <option value="WITHDRAWN">Withdrawn</option>
              <option value="COMPLETED">Completed</option>
            </select>
            <span v-if="fieldErrors.status" class="field-error">{{ fieldErrors.status.join(', ') }}</span>
          </label>
        </div>

        <div class="starting-enrolment">
          <div class="section-heading">
            <div><h3>Starting enrolment</h3><p>Defaults suit a new intake; change the year level for a transfer student.</p></div>
          </div>
          <div class="field-grid">
            <fieldset class="field">
              <legend>Starting year level <b aria-hidden="true">*</b></legend>
              <div v-if="yearLevels.length" class="year-options">
                <label v-for="level in yearLevels" :key="level" :class="{ selected: form.year_level === level }">
                  <input v-model="form.year_level" type="radio" name="year_level" :value="level" required>
                  <span>Year {{ level }}</span>
                </label>
              </div>
              <p v-else class="form-text">Choose a trade to see available year levels.</p>
              <span v-if="fieldErrors.year_level" class="field-error">{{ fieldErrors.year_level.join(', ') }}</span>
            </fieldset>
            <label class="field">
              <span>Starting semester <b aria-hidden="true">*</b></span>
              <select v-model="form.semester" class="form-select" required :disabled="!options?.semesters.length">
                <option value="">Choose a semester</option>
                <option v-for="semester in options?.semesters ?? []" :key="semester.id" :value="String(semester.id)">
                  {{ semester.name }} — {{ semester.status === 'ACTIVE' ? 'current' : 'upcoming' }}
                </option>
              </select>
              <small>The student’s first semester for enrolment and charges.</small>
              <span v-if="fieldErrors.semester" class="field-error">{{ fieldErrors.semester.join(', ') }}</span>
            </label>
          </div>
          <p v-if="options && !options.semesters.length" class="alert alert-warning mb-0">
            No current or upcoming semester exists. Add a semester before registering students.
          </p>
        </div>
      </section>

      <footer class="action-bar">
        <p><strong>Enter the student’s name, Trade, and starting enrolment.</strong><span>Ctrl / ⌘ + Enter saves</span></p>
        <div class="action-buttons">
          <NuxtLink to="/students" class="btn btn-outline-secondary">Cancel</NuxtLink>
          <button type="button" class="btn btn-outline-primary" :disabled="!canSubmit" @click="submitStudent(true)">
            {{ isSubmitting ? 'Saving…' : 'Register and add another' }}
          </button>
          <button type="submit" class="btn btn-primary" :disabled="!canSubmit">
            {{ isSubmitting ? 'Saving…' : 'Register student' }}
          </button>
        </div>
      </footer>
    </form>
  </div>
</template>

<style scoped>
.registration-page {
  --ink: #1e2b33;
  --muted: #4e5c66;
  --line: #d6dad5;
  --wash: #f5f6f3;
  --rail: #1f4f7a;
  max-width: 1180px;
  margin: 0 auto;
  padding: 1.25rem 1.5rem 2rem;
  color: var(--ink);
}
.page-heading, .section-heading, .action-bar, .action-buttons {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}
.page-heading { margin-bottom: 1.5rem; }
.eyebrow {
  margin: 0 0 0.35rem;
  color: var(--muted);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}
h1 { margin: 0; font-size: clamp(1.6rem, 3vw, 2rem); font-weight: 800; text-transform: uppercase; }
.intro, .section-heading p { margin: 0.45rem 0 0; color: var(--muted); }
.registration-form { display: grid; gap: 1rem; }
.registration-card {
  padding: 1.15rem;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
}
.section-heading { align-items: center; margin-bottom: 1rem; }
.section-heading h2, .section-heading h3 { margin: 0; font-size: 1.08rem; font-weight: 750; }
.section-heading h3 { font-size: 0.98rem; }
.section-number {
  display: grid;
  width: 2rem;
  height: 2rem;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 50%;
  background: #e5edf4;
  color: var(--rail);
  font-weight: 750;
}
.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.field { display: flex; min-width: 0; flex-direction: column; gap: 0.35rem; margin: 0; }
.field > span:first-child, .field legend { color: var(--ink); font-size: 0.875rem; font-weight: 650; }
.field b { color: #b8372b; }
.field small { color: var(--muted); font-size: 0.78rem; }
.field-wide { grid-column: 1 / -1; }
.field-error { color: #b8372b; font-size: 0.82rem; }
.starting-enrolment {
  display: grid;
  gap: 1rem;
  margin-top: 1.25rem;
  padding: 1rem;
  border: 1px solid #bfcedc;
  border-radius: 8px;
  background: var(--wash);
}
.year-options { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.year-options label {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.6rem 0.8rem;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: #fff;
  cursor: pointer;
}
.year-options label.selected { border-color: var(--rail); background: #e5edf4; color: var(--rail); }
.action-bar {
  position: sticky;
  bottom: 0;
  align-items: center;
  margin-top: 0.25rem;
  padding: 1rem;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: rgb(255 255 255 / 96%);
  box-shadow: 0 -4px 18px rgb(30 43 51 / 8%);
}
.action-bar p { display: grid; gap: 0.25rem; margin: 0; color: var(--muted); font-size: 0.85rem; }
.action-bar p strong { color: var(--ink); }
.action-bar p span { font-size: 0.75rem; }
.action-buttons { align-items: center; flex-wrap: wrap; }
.btn-primary { border-color: var(--rail); background: var(--rail); }
.btn-primary:hover { border-color: #163b5c; background: #163b5c; }
@media (max-width: 720px) {
  .registration-page { padding: 1rem; }
  .page-heading, .action-bar { flex-direction: column; }
  .page-heading > a { align-self: flex-start; }
  .action-buttons { width: 100%; }
  .action-buttons > * { flex: 1 1 100%; }
}
@media (max-width: 520px) {
  .field-grid { grid-template-columns: minmax(0, 1fr); }
  .field-wide { grid-column: auto; }
}
</style>
