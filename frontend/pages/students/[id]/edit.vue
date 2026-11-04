<script setup lang="ts">
interface Option {
  id: number;
  name: string;
}

interface StudentRecord {
  id: number;
  student_number: string;
  first_name: string;
  last_name: string;
  national_id: string;
  date_of_birth: string | null;
  gender: string;
  guardian_name: string;
  guardian_phone: string;
  student_phone: string;
  address: string;
  status: string;
  program: { id: number; name: string; code: string } | null;
  intake_year_id: number;
}

interface LookupResponse<T> {
  count: number;
  results: T[];
}

interface StudentForm {
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
}

const route = useRoute();
const router = useRouter();
const api = useApi();
const { user } = useAuth();
const submitting = ref(false);
const submitError = ref('');
const fieldErrors = ref<Record<string, string[]>>({});

const { data: initialData, pending, error } = await useAsyncData(
  `student-edit-${route.params.id}`,
  async () => {
    const [student, programs, years] = await Promise.all([
      api.get<StudentRecord>(`/api/students/${route.params.id}/`),
      api.get<LookupResponse<Option & { code: string }>>('/api/programs/'),
      api.get<LookupResponse<Option>>('/api/academic-years/'),
    ]);

    return { student, programs: programs.results, years: years.results };
  },
  { watch: [() => route.params.id] },
);

const form = reactive<StudentForm>({
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
});

watch(
  initialData,
  (value) => {
    if (!value) return;
    Object.assign(form, {
      student_number: value.student.student_number,
      first_name: value.student.first_name,
      last_name: value.student.last_name,
      national_id: value.student.national_id,
      date_of_birth: value.student.date_of_birth ?? '',
      gender: value.student.gender,
      guardian_name: value.student.guardian_name,
      guardian_phone: value.student.guardian_phone,
      student_phone: value.student.student_phone,
      address: value.student.address,
      program: String(value.student.program?.id ?? ''),
      intake_year: String(value.student.intake_year_id),
      status: value.student.status,
    });
  },
  { immediate: true },
);

const canEdit = computed(() => Boolean(user.value?.permissions.change_student));
useHead({ title: 'Edit Student | BSoft' });

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function parseErrors(errorValue: unknown) {
  if (!isRecord(errorValue)) return { summary: 'Unable to save changes. Please try again.', fields: {} };
  const body = isRecord(errorValue.data) ? errorValue.data : {};
  const errors = isRecord(body.errors) ? body.errors : {};
  const fields: Record<string, string[]> = {};

  for (const [field, value] of Object.entries(errors)) {
    const messages = Array.isArray(value)
      ? value.map((item) => {
          if (typeof item === 'string') return item;
          if (isRecord(item) && typeof item.message === 'string') return item.message;
          return '';
        }).filter(Boolean)
      : typeof value === 'string' ? [value] : [];
    if (messages.length) fields[field] = messages;
  }

  const summary = typeof body.detail === 'string'
    ? body.detail
    : typeof errorValue.message === 'string' ? errorValue.message : 'Please check the highlighted details.';
  return { summary, fields };
}

async function saveStudent() {
  if (!initialData.value) return;
  submitting.value = true;
  submitError.value = '';
  fieldErrors.value = {};

  try {
    await api.patch<StudentRecord>(`/api/students/${route.params.id}/patch/`, {
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
    });
    await router.push(`/students/${route.params.id}`);
  } catch (requestError: unknown) {
    const result = parseErrors(requestError);
    submitError.value = result.summary;
    fieldErrors.value = result.fields;
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="edit-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">People / Students / Edit</p>
        <h1>Edit student</h1>
        <p v-if="initialData" class="intro">
          Update {{ initialData.student.first_name }} {{ initialData.student.last_name }}.
          Starting enrolment is managed separately.
        </p>
      </div>
      <NuxtLink :to="`/students/${route.params.id}`" class="btn btn-outline-secondary">Back to student</NuxtLink>
    </header>

    <div v-if="!canEdit" class="alert alert-danger" role="alert">Your account does not have permission to edit students.</div>
    <div v-else-if="pending" class="form-card" role="status">Loading student details…</div>
    <div v-else-if="error" class="alert alert-danger" role="alert">Unable to load student details. {{ error.message }}</div>
    <form v-else class="edit-form" @submit.prevent="saveStudent">
      <div v-if="submitError" class="alert alert-danger" role="alert">
        <strong>{{ submitError }}</strong>
        <ul v-if="Object.keys(fieldErrors).length" class="mb-0 mt-2">
          <li v-for="(messages, field) in fieldErrors" :key="field">{{ field.replaceAll('_', ' ') }}: {{ messages.join(', ') }}</li>
        </ul>
      </div>

      <section class="form-card">
        <div class="section-title"><div><h2>Personal details</h2><p>Keep these consistent with the student’s records.</p></div><span>1</span></div>
        <div class="field-grid">
          <label class="field"><span>Student number *</span><input v-model="form.student_number" class="form-control" required maxlength="30"><small v-if="fieldErrors.student_number" class="field-error">{{ fieldErrors.student_number.join(', ') }}</small></label>
          <label class="field"><span>First names *</span><input v-model="form.first_name" class="form-control" required maxlength="100"><small v-if="fieldErrors.first_name" class="field-error">{{ fieldErrors.first_name.join(', ') }}</small></label>
          <label class="field"><span>Last name *</span><input v-model="form.last_name" class="form-control" required maxlength="100"><small v-if="fieldErrors.last_name" class="field-error">{{ fieldErrors.last_name.join(', ') }}</small></label>
          <label class="field"><span>National ID</span><input v-model="form.national_id" class="form-control" maxlength="100"><small v-if="fieldErrors.national_id" class="field-error">{{ fieldErrors.national_id.join(', ') }}</small></label>
          <label class="field"><span>Date of birth</span><input v-model="form.date_of_birth" class="form-control" type="date" min="1900-01-01" :max="new Date().toISOString().slice(0, 10)"><small v-if="fieldErrors.date_of_birth" class="field-error">{{ fieldErrors.date_of_birth.join(', ') }}</small></label>
          <label class="field"><span>Gender</span><select v-model="form.gender" class="form-select"><option value="">Not specified</option><option value="MALE">Male</option><option value="FEMALE">Female</option></select><small v-if="fieldErrors.gender" class="field-error">{{ fieldErrors.gender.join(', ') }}</small></label>
        </div>
      </section>

      <section class="form-card">
        <div class="section-title"><div><h2>Contact and guardian</h2><p>Contact details for the student file.</p></div><span>2</span></div>
        <div class="field-grid">
          <label class="field"><span>Student phone</span><input v-model="form.student_phone" class="form-control" type="tel" maxlength="30"><small v-if="fieldErrors.student_phone" class="field-error">{{ fieldErrors.student_phone.join(', ') }}</small></label>
          <label class="field"><span>Guardian name</span><input v-model="form.guardian_name" class="form-control" maxlength="150"><small v-if="fieldErrors.guardian_name" class="field-error">{{ fieldErrors.guardian_name.join(', ') }}</small></label>
          <label class="field"><span>Guardian phone</span><input v-model="form.guardian_phone" class="form-control" type="tel" maxlength="30"><small v-if="fieldErrors.guardian_phone" class="field-error">{{ fieldErrors.guardian_phone.join(', ') }}</small></label>
          <label class="field field-wide"><span>Home address</span><textarea v-model="form.address" class="form-control" rows="3" /><small v-if="fieldErrors.address" class="field-error">{{ fieldErrors.address.join(', ') }}</small></label>
        </div>
      </section>

      <section class="form-card">
        <div class="section-title"><div><h2>Trade and status</h2><p>Changing these details does not alter existing enrolments.</p></div><span>3</span></div>
        <div class="field-grid">
          <label class="field"><span>Trade *</span><select v-model="form.program" class="form-select" required><option value="">Choose a trade</option><option v-for="program in initialData?.programs ?? []" :key="program.id" :value="String(program.id)">{{ program.name }} ({{ program.code }})</option></select><small v-if="fieldErrors.program" class="field-error">{{ fieldErrors.program.join(', ') }}</small></label>
          <label class="field"><span>Intake year *</span><select v-model="form.intake_year" class="form-select" required><option value="">Choose an academic year</option><option v-for="year in initialData?.years ?? []" :key="year.id" :value="String(year.id)">{{ year.name }}</option></select><small v-if="fieldErrors.intake_year" class="field-error">{{ fieldErrors.intake_year.join(', ') }}</small></label>
          <label class="field"><span>Status</span><select v-model="form.status" class="form-select"><option value="ACTIVE">Active</option><option value="DEFERRED">Deferred</option><option value="WITHDRAWN">Withdrawn</option><option value="COMPLETED">Completed</option></select><small v-if="fieldErrors.status" class="field-error">{{ fieldErrors.status.join(', ') }}</small></label>
        </div>
      </section>

      <footer class="action-bar">
        <p><strong>Review the student record before saving.</strong><span>Starting enrolment is managed separately.</span></p>
        <div class="actions"><NuxtLink :to="`/students/${route.params.id}`" class="btn btn-outline-secondary">Cancel</NuxtLink><button type="submit" class="btn btn-primary" :disabled="submitting">{{ submitting ? 'Saving…' : 'Save changes' }}</button></div>
      </footer>
    </form>
  </div>
</template>

<style scoped>
.edit-page { --ink:#1e2b33; --muted:#4e5c66; --line:#d6dad5; --rail:#1f4f7a; max-width:1180px; margin:0 auto; padding:1.25rem 1.5rem 2rem; color:var(--ink); }
.page-heading,.section-title,.action-bar,.actions { display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; }
.page-heading { margin-bottom:1.5rem; }
.eyebrow { margin:0 0 .35rem; color:var(--muted); font-size:.75rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase; }
h1 { margin:0; font-size:clamp(1.6rem,3vw,2rem); font-weight:800; text-transform:uppercase; }
.intro,.section-title p { margin:.45rem 0 0; color:var(--muted); }
.edit-form { display:grid; gap:1rem; }
.form-card { padding:1.15rem; border:1px solid var(--line); border-radius:10px; background:#fff; }
.section-title { align-items:center; margin-bottom:1rem; }
.section-title h2 { margin:0; font-size:1.08rem; font-weight:750; }
.section-title > span { display:grid; width:2rem; height:2rem; flex:0 0 auto; place-items:center; border-radius:50%; background:#e5edf4; color:var(--rail); font-weight:750; }
.field-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:1rem; }
.field { display:flex; min-width:0; flex-direction:column; gap:.35rem; margin:0; font-size:.875rem; font-weight:650; }
.field-wide { grid-column:1/-1; }
.field small { font-weight:400; }
.field-error { color:#b8372b; }
.action-bar { position:sticky; bottom:0; align-items:center; padding:1rem; border:1px solid var(--line); border-radius:10px; background:rgb(255 255 255 / 96%); box-shadow:0 -4px 18px rgb(30 43 51 / 8%); }
.action-bar p { display:grid; gap:.25rem; margin:0; color:var(--muted); font-size:.85rem; }
.action-bar p strong { color:var(--ink); }
.actions { align-items:center; }
.btn-primary { border-color:var(--rail); background:var(--rail); }
.btn-primary:hover { border-color:#163b5c; background:#163b5c; }
@media(max-width:720px) { .edit-page{padding:1rem}.page-heading,.action-bar{flex-direction:column}.actions{width:100%}.actions>*{flex:1} }
@media(max-width:520px) { .field-grid{grid-template-columns:minmax(0,1fr)}.field-wide{grid-column:auto} }
</style>
