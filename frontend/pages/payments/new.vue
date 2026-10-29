<script setup lang="ts">
const route = useRoute();
const router = useRouter();
const api = useApi();

const student = ref<any>(null);
const enrollments = ref<any[]>([]);
const selectedEnrollment = ref<any>(null);
const searchQuery = ref("");
const searchResults = ref<any[]>([]);
const searchDebounce = ref<ReturnType<typeof setTimeout> | null>(null);
const form = ref<Record<string, any>>({
  semester: "",
  amount: "",
  payment_date: new Date().toISOString().split("T")[0],
  method: "CASH",
  reference: "",
  notes: "",
});
const errors = ref<Record<string, string[]>>({});
const submitting = ref(false);
const charged = ref(0);
const paid = ref(0);
const balance = ref(0);
const paymentMethods = [
  { value: "CASH", label: "Cash" },
  { value: "BANK", label: "Bank" },
  { value: "ECOCASH", label: "EcoCash" },
  { value: "OTHER", label: "Other" },
];

const today = new Date().toISOString().split("T")[0];

async function searchStudents(query: string) {
  if (query.length < 2) {
    searchResults.value = [];
    return;
  }
  try {
    const response = await api.get<{ students: any[] }>(`/api/students/search/?q=${encodeURIComponent(query)}`);
    searchResults.value = response.students ?? [];
  } catch (e: any) {
    searchResults.value = [];
    console.error("Student search error:", e);
  }
}

async function selectStudent(s: any) {
  student.value = s;
  searchQuery.value = `${s.first_name} ${s.last_name} (${s.student_number})`;
  searchResults.value = [];
  await loadEnrollments(s.id);
}

async function loadEnrollments(studentId: number) {
  try {
    const response = await api.get<{ enrollments: any[] }>(`/api/students/${studentId}/enrollments-for-payment/`);
    enrollments.value = response.enrollments ?? [];
    if (enrollments.value.length > 0) {
      const defaultEnrollment = enrollments.value.find(e => e.is_current) || enrollments.value[0];
      selectedEnrollment.value = defaultEnrollment;
      form.value.semester = defaultEnrollment.semester.id;
      await loadBalance(studentId, defaultEnrollment.semester.id);
    }
  } catch (e: any) {
    enrollments.value = [];
    console.error("Load enrollments error:", e);
  }
}

async function loadBalance(studentId: number, semesterId: number) {
  try {
    const response = await api.get<{ charged: number; paid: number; balance: number }>(`/api/students/${studentId}/balance/${semesterId}/`);
    charged.value = response.charged;
    paid.value = response.paid;
    balance.value = response.balance;
  } catch (e: any) {
    charged.value = 0;
    paid.value = 0;
    balance.value = 0;
    console.error("Load balance error:", e);
  }
}

function onSemesterChange() {
  const enrollment = enrollments.value.find(e => e.semester.id === form.value.semester);
  if (enrollment) {
    selectedEnrollment.value = enrollment;
    if (student.value) {
      loadBalance(student.value.id, enrollment.semester.id);
    }
  }
}

function validateForm(): boolean {
  const newErrors: Record<string, string[]> = {};
  if (!student.value) newErrors.student = ["Please select a student."];
  if (!form.value.semester) newErrors.semester = ["Please select a semester."];
  if (!form.value.amount) newErrors.amount = ["Amount is required."];
  else if (parseFloat(form.value.amount) <= 0) newErrors.amount = ["Amount must be greater than zero."];
  if (!form.value.payment_date) newErrors.payment_date = ["Payment date is required."];
  if (!form.value.method) newErrors.method = ["Payment method is required."];
  errors.value = newErrors;
  return Object.keys(newErrors).length === 0;
}

async function submitPayment() {
  if (!validateForm()) return;

  submitting.value = true;
  errors.value = {};

  try {
    await api.post("/api/payments/create/", {
      student: student.value.id,
      semester: form.value.semester,
      amount: parseFloat(form.value.amount),
      payment_date: form.value.payment_date,
      method: form.value.method,
      reference: form.value.reference,
      notes: form.value.notes,
    });
    // Redirect to student detail page
    if (student.value) {
      router.push(`/students/${student.value.id}`);
    }
  } catch (e: any) {
    if (e.response?._data?.errors) {
      errors.value = e.response._data.errors;
    } else {
      errors.value = { detail: [e.message || "Failed to record payment."] };
    }
  } finally {
    submitting.value = false;
  }
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function getBalanceClass(bal: number): string {
  if (bal > 0) return "text-red-600";
  if (bal < 0) return "text-blue-600";
  return "text-green-600";
}
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Payments</p>
        <h1>Record Payment</h1>
      </div>
      <NuxtLink to="/students" class="primary-link">Back to Students</NuxtLink>
    </section>

    <div v-if="submitting" class="state-card">Recording payment…</div>
    <div v-else-if="Object.keys(errors).length && errors.detail" class="state-card error">{{ errors.detail[0] }}</div>

    <!-- Student Search -->
    <div class="card">
      <label for="studentSearch" class="form-label fw-semibold">Find Student</label>
      <input
        type="text"
        id="studentSearch"
        class="form-control"
        placeholder="Type student number or name..."
        autocomplete="off"
        v-model="searchQuery"
        @input="onSearchInput"
        @focus="onSearchInput"
      >
      <div
        v-if="searchResults.length > 0"
        class="list-group mt-2 shadow-sm"
        style="position: relative; z-index: 10;"
      >
        <a
          v-for="s in searchResults"
          :key="s.id"
          class="list-group-item list-group-item-action"
          @click.prevent="selectStudent(s)"
        >
          <strong>{{ s.name }}</strong>
          <span class="text-muted small ms-2">— {{ s.student_number }}</span>
          <div class="text-muted small">{{ s.program }} · {{ s.current_semester || 'No active semester' }}</div>
        </a>
      </div>
      <div
        v-else-if="searchQuery.length >= 2 && !pending && searchResults.length === 0"
        class="list-group-item text-muted mt-2"
      >
        No matches found.
      </div>
    </div>

    <template v-if="student">
      <!-- Student Information -->
      <div class="card mb-4">
        <div class="d-flex justify-content-between align-items-start mb-3">
          <div>
            <h5 class="mb-1">
              {{ student.first_name }} {{ student.last_name }}
              <span class="text-muted small">({{ student.student_number }})</span>
            </h5>
            <div class="text-muted small">{{ student.program }}</div>
          </div>
          <NuxtLink :to="`/students/${student.id}`" class="btn btn-sm btn-outline-secondary">Full Profile</NuxtLink>
        </div>

        <!-- Form Validation Summary -->
        <div v-if="errors.student || errors.semester" class="alert alert-danger mb-4" role="alert">
          <div class="fw-semibold">Unable to record payment.</div>
          <div class="small mt-1" v-for="(msgs, field) in errors" :key="field">
            {{ msgs.join(", ") }}
          </div>
        </div>

        <!-- Enrollment Info & Balance -->
        <div v-if="selectedEnrollment" class="row mb-3">
          <div class="col-md-4">
            <label class="form-label fw-semibold">Payment For</label>
            <div class="form-control-plaintext fw-bold">{{ selectedEnrollment.semester.name }}</div>
          </div>
          <div class="col-md-4">
            <label class="form-label fw-semibold">Program / Year</label>
            <div class="form-control-plaintext">{{ selectedEnrollment.program.code }} — Year {{ selectedEnrollment.year_level }}</div>
          </div>
          <div class="col-md-4">
            <label class="form-label fw-semibold">Outstanding Balance</label>
            <div class="form-control-plaintext fw-bold fs-5" :class="getBalanceClass(balance)">
              {{ balance > 0 ? '$' + formatCurrency(balance) : (balance === 0 ? 'Paid in full' : 'Credit $' + formatCurrency(Math.abs(balance))) }}
            </div>
          </div>
        </div>

        <div v-if="selectedEnrollment" class="row mb-3">
          <div class="col-md-4">
            <label class="form-label fw-semibold">Charged</label>
            <div class="form-control-plaintext fw-bold">${{ formatCurrency(charged) }}</div>
          </div>
          <div class="col-md-4">
            <label class="form-label fw-semibold">Paid</label>
            <div class="form-control-plaintext fw-bold text-success">${{ formatCurrency(paid) }}</div>
          </div>
        </div>
      </div>

      <!-- Semester Selection -->
      <div v-if="enrollments.length > 0" class="card mb-4">
        <label for="semesterSelect" class="form-label fw-semibold">
          Payment For <span class="text-danger">*</span>
        </label>
        <select
          id="semesterSelect"
          v-model="form.semester"
          class="form-select"
          @change="onSemesterChange"
          required
        >
          <option value="" disabled>Select semester...</option>
          <option v-for="e in enrollments" :key="e.id" :value="e.semester.id">
            {{ e.semester.name }} ({{ e.program.code }} — Year {{ e.year_level }}) — Balance: ${{ formatCurrency(e.balance) }}
          </option>
        </select>
        <div class="form-text mt-1">
          Select the semester this payment belongs to. You can record payments for past, current, or upcoming terms.
        </div>
        <div v-if="errors.semester" class="invalid-feedback d-block mt-1">
          {{ errors.semester.join(", ") }}
        </div>
      </div>

      <!-- Payment Form -->
      <form @submit.prevent="submitPayment" v-if="selectedEnrollment">
        <input type="hidden" name="student_id" :value="student.id">

        <div class="card mb-4">
          <div class="card-body">
            <h5 class="mb-3">Payment Details</h5>
            <div class="row">
              <div class="col-md-6 mb-3">
                <label for="amount" class="form-label fw-semibold">Amount <span class="text-danger">*</span></label>
                <input
                  type="number"
                  id="amount"
                  v-model="form.amount"
                  class="form-control"
                  step="0.01"
                  min="0.01"
                  placeholder="0.00"
                  required
                >
                <div v-if="errors.amount" class="invalid-feedback d-block">{{ errors.amount.join(", ") }}</div>
              </div>

              <div class="col-md-6 mb-3">
                <label for="payment_date" class="form-label fw-semibold">Payment Date <span class="text-danger">*</span></label>
                <input
                  type="date"
                  id="payment_date"
                  v-model="form.payment_date"
                  class="form-control"
                  :max="today"
                  required
                >
                <div v-if="errors.payment_date" class="invalid-feedback d-block">{{ errors.payment_date.join(", ") }}</div>
              </div>

              <div class="col-md-6 mb-3">
                <label for="method" class="form-label fw-semibold">Payment Method <span class="text-danger">*</span></label>
                <select
                  id="method"
                  v-model="form.method"
                  class="form-select"
                  required
                >
                  <option v-for="m in paymentMethods" :key="m.value" :value="m.value">{{ m.label }}</option>
                </select>
                <div v-if="errors.method" class="invalid-feedback d-block">{{ errors.method.join(", ") }}</div>
              </div>

              <div class="col-md-6 mb-3">
                <label for="reference" class="form-label fw-semibold">Reference</label>
                <input
                  type="text"
                  id="reference"
                  v-model="form.reference"
                  class="form-control"
                  placeholder="Optional reference (check #, transaction ID, etc.)"
                >
              </div>

              <div class="col-12 mb-3">
                <label for="notes" class="form-label fw-semibold">Notes</label>
                <textarea
                  id="notes"
                  v-model="form.notes"
                  class="form-control"
                  rows="3"
                  placeholder="Optional notes"
                ></textarea>
              </div>
            </div>
          </div>
        </div>

        <div class="d-flex justify-content-end gap-2">
          <NuxtLink :to="`/students/${student.id}`" class="btn btn-secondary">Cancel</NuxtLink>
          <button type="submit" class="btn btn-success px-4" :disabled="submitting">
            <span v-if="submitting">Recording...</span>
            <span v-else>Record Payment</span>
          </button>
        </div>
      </form>
    </template>

    <div v-else class="text-center text-muted py-5">
      Search for a student above to record their payment.
    </div>
  </div>
</template>

<style scoped>
.page-shell {
  display: grid;
  gap: 1.25rem;
  padding: 1.5rem;
  max-width: 900px;
  margin: 0 auto;
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
  padding: 1.2rem;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
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
.form-control, .form-select {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 0.6rem 0.8rem;
  width: 100%;
}
.form-control-plaintext {
  padding: 0.6rem 0;
  font-size: 1rem;
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
.btn {
  padding: 0.6rem 1.2rem;
  border-radius: 8px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  text-decoration: none;
  display: inline-block;
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-secondary {
  background: #e5e7eb;
  color: #111827;
}
.btn-success {
  background: #16a34a;
  color: white;
}
.btn-outline-secondary {
  background: transparent;
  border: 1px solid #d1d5db;
  color: #374151;
}
.btn-sm {
  padding: 0.4rem 0.8rem;
  font-size: 0.85rem;
}
.alert {
  padding: 0.8rem 1rem;
  border-radius: 8px;
}
.alert-danger {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
}
.row {
  display: flex;
  flex-wrap: wrap;
  margin: 0 -0.5rem;
}
.col-md-4, .col-md-6, .col-12 {
  padding: 0 0.5rem;
}
.col-md-4 { flex: 0 0 33.333%; max-width: 33.333%; }
.col-md-6 { flex: 0 0 50%; max-width: 50%; }
.col-12 { flex: 0 0 100%; max-width: 100%; }
@media (max-width: 768px) {
  .col-md-4, .col-md-6 { flex: 0 0 100%; max-width: 100%; }
}
.d-flex { display: flex; }
.justify-content-between { justify-content: space-between; }
.justify-content-end { justify-content: flex-end; }
.align-items-start { align-items: flex-start; }
.align-items-center { align-items: center; }
.gap-2 { gap: 0.5rem; }
.gap-1 { gap: 0.25rem; }
.mb-3 { margin-bottom: 1rem; }
.mb-4 { margin-bottom: 1.5rem; }
.mt-1 { margin-top: 0.25rem; }
.mt-2 { margin-top: 0.5rem; }
.mt-3 { margin-top: 1rem; }
.text-muted { color: #6b7280; }
.text-danger { color: #dc2626; }
.text-success { color: #16a34a; }
.text-red-600 { color: #dc2626; }
.text-blue-600 { color: #2563eb; }
.text-green-600 { color: #16a34a; }
.fw-bold { font-weight: 700; }
.fw-semibold { font-weight: 600; }
.fs-5 { font-size: 1.25rem; }
.small { font-size: 0.85rem; }
.list-group { border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; background: white; }
.list-group-item { padding: 0.75rem 1rem; border-bottom: 1px solid #e5e7eb; cursor: pointer; }
.list-group-item:last-child { border-bottom: none; }
.list-group-item:hover { background: #f9fafb; }
.list-group-item-action { text-decoration: none; color: inherit; display: block; }
</style>