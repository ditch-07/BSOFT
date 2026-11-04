<script setup lang="ts">
const route = useRoute();
const api = useApi();
const { user } = useAuth();

const { data, pending, error } = await useAsyncData(`student-${route.params.id}`, () => api.get<any>(`/api/students/${route.params.id}/payment-history/`));
const router = useRouter();
const statusDialogOpen = ref(false);
const statusSaving = ref(false);
const statusError = ref('');
const nextStatus = ref('');
const statusNote = ref('');

async function saveStatus() {
  statusSaving.value = true;
  statusError.value = '';
  try {
    const result = await api.post<{ status: string; status_display: string }>(
      `/api/students/${route.params.id}/status/`,
      { status: nextStatus.value, note: statusNote.value },
    );
    if (data.value?.student) {
      data.value.student.status = result.status;
      data.value.student.status_display = result.status_display;
    }
    statusDialogOpen.value = false;
    statusNote.value = '';
  } catch (requestError: unknown) {
    statusError.value = requestError instanceof Error ? requestError.message : 'Unable to update student status.';
  } finally {
    statusSaving.value = false;
  }
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

function getBalanceClass(bal: number): string {
  if (bal > 0) return "text-red-600";
  if (bal < 0) return "text-blue-600";
  return "text-green-600";
}

function getStatusBadgeClass(status: string): string {
  switch (status) {
    case "ACTIVE": return "bg-success";
    case "DEFERRED": return "bg-warning";
    case "WITHDRAWN": return "bg-secondary";
    case "COMPLETED": return "bg-primary";
    default: return "bg-light text-dark";
  }
}
</script>

<template>
  <div class="page-shell">
    <div class="heading-row">
      <div>
        <p class="eyebrow">Profile</p>
        <h1>{{ data?.student?.name ?? 'Student' }}</h1>
      </div>
      <div class="d-flex gap-2 flex-wrap">
        <NuxtLink v-if="user?.permissions.change_student" :to="`/students/${route.params.id}/edit`" class="btn btn-outline-primary">
          Edit student
        </NuxtLink>
        <button
          v-if="user?.permissions.change_student && data?.student"
          type="button"
          class="btn btn-outline-secondary"
          @click="nextStatus = data.student.status; statusDialogOpen = true"
        >
          Change status
        </button>
        <NuxtLink v-if="user?.permissions.can_record_payments" :to="`/payments/new?student=${data?.student?.id}`" class="btn btn-success">
          + Record Payment
        </NuxtLink>
        <NuxtLink to="/students" class="secondary-link">Back to students</NuxtLink>
      </div>
    </div>

    <div v-if="statusDialogOpen" class="status-backdrop" @click.self="statusDialogOpen = false">
      <section class="status-dialog" role="dialog" aria-modal="true" aria-labelledby="status-dialog-title">
        <h2 id="status-dialog-title">Change student status</h2>
        <p>Withdrawing a student also cancels their unpaid future charges.</p>
        <div v-if="statusError" class="alert alert-danger" role="alert">{{ statusError }}</div>
        <label class="status-field">
          <span>Status</span>
          <select v-model="nextStatus" class="form-select">
            <option value="ACTIVE">Active</option>
            <option value="DEFERRED">Deferred</option>
            <option value="WITHDRAWN">Withdrawn</option>
            <option value="COMPLETED">Completed</option>
          </select>
        </label>
        <label class="status-field">
          <span>Note (optional)</span>
          <textarea v-model="statusNote" class="form-control" rows="3" placeholder="Reason for this status change" />
        </label>
        <div class="status-actions">
          <button type="button" class="btn btn-outline-secondary" :disabled="statusSaving" @click="statusDialogOpen = false">Cancel</button>
          <button type="button" class="btn btn-primary" :disabled="statusSaving" @click="saveStatus">{{ statusSaving ? 'Saving…' : 'Save status' }}</button>
        </div>
      </section>
    </div>

    <div v-if="pending" class="card">Loading student details…</div>
    <div v-else-if="error" class="card error">Unable to load student. {{ error.message }}</div>
    <div v-else>
      <!-- Academic Year Balance Summary -->
      <div v-if="data?.student?.current_year && data?.semester_balances?.length" class="card mb-4">
        <div class="card-header bg-light">
          <h5 class="mb-0">
            {{ data.student.current_year }} — Academic Year Balance
          </h5>
        </div>
        <div class="card-body">
          <div class="row g-3 mb-3">
            <div v-for="sb in data.semester_balances" :key="sb.semester.id" class="col-md-6">
              <div class="card border h-100">
                <div class="card-body">
                  <div class="d-flex justify-content-between align-items-center mb-3">
                    <h6 class="mb-0 fw-bold">{{ sb.semester.name }}</h6>
                    <span class="badge" :class="getStatusBadgeClass(sb.balance > 0 ? 'OUTSTANDING' : (sb.balance < 0 ? 'CREDIT' : 'PAID'))">
                      {{ sb.balance > 0 ? 'Outstanding' : (sb.balance < 0 ? 'Credit' : 'Paid') }}
                    </span>
                  </div>
                  <div class="row text-center">
                    <div class="col-4">
                      <div class="small text-muted">Charged</div>
                      <div class="fw-bold">${{ formatCurrency(sb.charged) }}</div>
                    </div>
                    <div class="col-4">
                      <div class="small text-muted">Paid</div>
                      <div class="fw-bold text-success">${{ formatCurrency(sb.paid) }}</div>
                    </div>
                    <div class="col-4">
                      <div class="small text-muted">Balance</div>
                      <div class="fw-bold fs-5" :class="getBalanceClass(sb.balance)">
                        ${{ formatCurrency(Math.abs(sb.balance)) }}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <hr class="my-3">

          <div class="d-flex justify-content-between align-items-center">
            <div>
              <span class="text-muted">Total Academic Year Balance:</span>
            </div>
            <div class="fw-bold fs-3" :class="getBalanceClass(data.total_year_balance)">
              ${{ formatCurrency(Math.abs(data.total_year_balance)) }}
            </div>
          </div>

          <div class="mt-2 small" :class="data.total_year_balance > 0 ? 'text-danger' : (data.total_year_balance < 0 ? 'text-primary' : 'text-success')">
            <span v-if="data.total_year_balance > 0">Amount outstanding for {{ data.student.current_year }}</span>
            <span v-else-if="data.total_year_balance < 0">Credit balance of ${{ formatCurrency(Math.abs(data.total_year_balance)) }}</span>
            <span v-else>Fully paid for {{ data.student.current_year }}</span>
          </div>
        </div>
      </div>

      <div class="row g-4">
        <!-- Student Information -->
        <div class="col-lg-4">
          <div class="card">
            <div class="card-body">
              <h5>Student Information</h5>
              <hr>
              <dl>
                <div><dt>Student Number</dt><dd>{{ data?.student?.student_number }}</dd></div>
                <div><dt>Status</dt><dd>
                  <span class="badge" :class="getStatusBadgeClass(data?.student?.status)">
                    {{ data?.student?.status_display ?? data?.student?.status }}
                  </span>
                </dd></div>
                <div><dt>Program</dt><dd>{{ data?.student?.program?.name ?? 'Not assigned' }}</dd></div>
                <div><dt>Intake Year</dt><dd>{{ data?.student?.intake_year ?? 'N/A' }}</dd></div>
                <div><dt>Current Year Level</dt><dd>
                  {{ data?.student?.current_year_level ?? '—' }}
                  <span v-if="data?.student?.current_year_level" class="badge bg-info text-dark ms-1">
                    Year {{ data.student.current_year_level }}
                  </span>
                </dd></div>
              </dl>

              <h5 class="mt-3">Contact Details</h5>
              <hr>
              <dl>
                <div><dt>Guardian</dt><dd>{{ data?.student?.guardian_name || 'N/A' }}</dd></div>
                <div><dt>Guardian Phone</dt><dd>{{ data?.student?.guardian_phone || 'N/A' }}</dd></div>
                <div><dt>Student Phone</dt><dd>{{ data?.student?.student_phone || 'N/A' }}</dd></div>
                <div><dt>Address</dt><dd>{{ data?.student?.address || 'N/A' }}</dd></div>
                <div><dt>Date of Birth</dt><dd>{{ data?.student?.date_of_birth || 'N/A' }}</dd></div>
                <div><dt>Gender</dt><dd>{{ data?.student?.gender || 'N/A' }}</dd></div>
                <div><dt>National ID</dt><dd>{{ data?.student?.national_id || 'N/A' }}</dd></div>
              </dl>
            </div>
          </div>
        </div>

        <!-- Financial Information -->
        <div class="col-lg-8">
          <!-- All Semesters Balance -->
          <div class="card mb-4">
            <div class="card-body">
              <h5>All Semesters — Fee Tracking</h5>
              <div class="table-responsive">
                <table class="table table-hover">
                  <thead>
                    <tr>
                      <th>Semester</th>
                      <th>Charged</th>
                      <th>Paid</th>
                      <th>Balance</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in data?.balances ?? []" :key="item.semester.id">
                      <td class="fw-semibold">{{ item.semester.name }}</td>
                      <td>${{ formatCurrency(item.charged) }}</td>
                      <td class="text-success">${{ formatCurrency(item.paid) }}</td>
                      <td>
                        <span :class="getBalanceClass(item.balance)">
                          {{ item.balance > 0 ? '$' + formatCurrency(item.balance) : (item.balance === 0 ? 'PAID' : 'Credit $' + formatCurrency(Math.abs(item.balance))) }}
                        </span>
                      </td>
                    </tr>
                    <tr v-if="!data?.balances?.length">
                      <td colspan="4" class="text-center text-muted">No charges or payments recorded for this student yet.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- Payment History -->
          <div class="card">
            <div class="card-body">
              <div class="d-flex justify-content-between align-items-center mb-3">
                <h5>Payment History</h5>
                <NuxtLink :to="`/payments?student=${data?.student?.id}`" class="btn btn-sm btn-outline-primary">View All</NuxtLink>
              </div>
              <div class="table-responsive">
                <table class="table table-hover">
                  <thead>
                    <tr>
                      <th>Receipt</th>
                      <th>Date</th>
                      <th>Semester</th>
                      <th>Method</th>
                      <th>Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="p in data?.payments ?? []" :key="p.id">
                      <td class="fw-bold">
                        <NuxtLink :to="`/payments/${p.id}/receipt`">{{ p.receipt_number }}</NuxtLink>
                      </td>
                      <td>{{ formatDate(p.payment_date) }}</td>
                      <td>{{ p.semester.name }}</td>
                      <td>{{ p.method_display }}</td>
                      <td class="text-success fw-bold">${{ formatCurrency(p.amount) }}</td>
                    </tr>
                    <tr v-if="!data?.payments?.length">
                      <td colspan="5" class="text-center text-muted">No payments recorded.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-shell {
  display: grid;
  gap: 1rem;
  padding: 1.5rem;
}
.heading-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}
.eyebrow {
  margin: 0 0 0.4rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 0.7rem;
  color: #6b7280;
}
h1, h2, h5, h6 {
  margin: 0 0 0.75rem;
}
.card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 1rem;
}
.card-header {
  padding: 0.75rem 1rem;
  margin: -1rem -1rem 1rem;
  border-bottom: 1px solid #e5e7eb;
  background: white;
  border-radius: 12px 12px 0 0;
}
.card-header.bg-light { background: #f9fafb; }
.card-body { padding: 1rem; }
.grid-layout {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1rem;
}
dl {
  display: grid;
  gap: 0.6rem;
}
dl div {
  display: grid;
  gap: 0.2rem;
}
dt {
  color: #6b7280;
  font-size: 0.75rem;
  text-transform: uppercase;
}
dd {
  margin: 0;
  font-weight: 600;
}
.secondary-link {
  text-decoration: none;
  color: #111827;
  background: #f3f4f6;
  border-radius: 10px;
  padding: 0.7rem 1rem;
  font-weight: 600;
}
.error {
  color: #b91c1c;
}
.badge {
  padding: 0.35rem 0.65rem;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 0.5rem;
}
.bg-success { background: #dcfce7; color: #166534; }
.bg-warning { background: #fef9c3; color: #854d0e; }
.bg-secondary { background: #e5e7eb; color: #374151; }
.bg-primary { background: #dbeafe; color: #1e40af; }
.bg-info { background: #dbeafe; color: #1e40af; }
.bg-light { background: #f3f4f6; color: #111827; }
.text-danger { color: #dc2626; }
.text-primary { color: #2563eb; }
.text-success { color: #16a34a; }
.text-red-600 { color: #dc2626; }
.text-blue-600 { color: #2563eb; }
.text-green-600 { color: #16a34a; }
.text-muted { color: #6b7280; }
.fw-bold { font-weight: 700; }
.fw-semibold { font-weight: 600; }
.fs-3 { font-size: 1.75rem; }
.fs-5 { font-size: 1.25rem; }
.small { font-size: 0.85rem; }
.table-responsive { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 0.75rem 0.5rem; border-bottom: 1px solid #e5e7eb; text-align: left; }
th { background: #f9fafb; font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
.text-center { text-align: center; }
.text-md-end { text-align: right; }
.row { display: flex; flex-wrap: wrap; margin: 0 -0.5rem; }
.g-4 { gap: 1.5rem; }
.g-3 { gap: 1rem; }
.col-lg-4 { flex: 0 0 33.333%; max-width: 33.333%; }
.col-lg-8 { flex: 0 0 66.667%; max-width: 66.667%; }
.col-md-6 { flex: 0 0 50%; max-width: 50%; }
@media (max-width: 992px) {
  .col-lg-4, .col-lg-8 { flex: 0 0 100%; max-width: 100%; }
  .col-md-6 { flex: 0 0 100%; max-width: 100%; }
}
.d-flex { display: flex; }
.justify-content-between { justify-content: space-between; }
.justify-content-end { justify-content: flex-end; }
.align-items-center { align-items: center; }
.gap-2 { gap: 0.5rem; }
.gap-3 { gap: 1rem; }
.mb-3 { margin-bottom: 1rem; }
.mb-4 { margin-bottom: 1.5rem; }
.mt-2 { margin-top: 0.5rem; }
.mt-3 { margin-top: 1rem; }
.my-3 { margin-top: 1rem; margin-bottom: 1rem; }
.hr { border: none; border-top: 1px solid #e5e7eb; }
.btn {
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  text-decoration: none;
  display: inline-block;
}
.btn-sm { padding: 0.4rem 0.8rem; font-size: 0.85rem; }
.btn-success { background: #16a34a; color: white; }
.btn-outline-primary { background: transparent; border: 1px solid #2563eb; color: #2563eb; }
.status-backdrop { position:fixed; z-index:1080; inset:0; display:grid; place-items:center; padding:1rem; background:rgb(18 31 40 / 58%); }
.status-dialog { width:min(100%,520px); padding:1.35rem; border:1px solid #d6dad5; border-radius:12px; background:#fff; box-shadow:0 20px 60px rgb(0 0 0 / 22%); }
.status-dialog h2 { margin:0; font-size:1.25rem; }
.status-dialog > p { margin:.5rem 0 1rem; color:#4e5c66; }
.status-field { display:grid; gap:.35rem; margin:.9rem 0; font-weight:650; }
.status-actions { display:flex; justify-content:flex-end; gap:.6rem; margin-top:1.2rem; }
</style>