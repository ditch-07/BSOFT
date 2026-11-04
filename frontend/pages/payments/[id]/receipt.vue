<script setup lang="ts">
const route = useRoute();
const api = useApi();

const receipt = ref<any>(null);
const loading = ref(true);
const error = ref<string | null>(null);

async function loadReceipt() {
  loading.value = true;
  error.value = null;
  try {
    const response = await api.get<any>(`/api/payments/${route.params.id}/receipt/`);
    receipt.value = response;
  } catch (e: any) {
    error.value = e.message || "Failed to load receipt";
  } finally {
    loading.value = false;
  }
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
}

function printReceipt() {
  window.print();
}

onMounted(() => {
  loadReceipt();
});
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Receipt</p>
        <h1>Payment Receipt</h1>
      </div>
      <div class="d-flex gap-2">
        <button class="primary-link" @click="printReceipt">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5"/><path d="M18 18h2a2 2 0 0 0 2-2v-5"/><rect x="6" y="14" width="12" height="8"/></svg>
          Print
        </button>
        <NuxtLink to="/payments" class="secondary-link">Back to Payments</NuxtLink>
      </div>
    </section>

    <div v-if="loading" class="state-card">Loading receipt…</div>
    <div v-else-if="error" class="state-card error">{{ error }}</div>
    <div v-else-if="receipt" class="receipt-container">
      <!-- Print-only header -->
      <div class="print-only text-center mb-4">
        <h2 class="fw-bold mb-1">BSoft Student Management</h2>
        <h3 class="text-muted mb-2">Official Payment Receipt</h3>
        <p class="text-muted small">Generated: {{ new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}</p>
        <hr>
      </div>

      <div class="card receipt-card">
        <div class="receipt-header">
          <div class="d-flex justify-content-between align-items-start mb-3">
            <div>
              <h4 class="mb-1">RECEIPT</h4>
              <p class="text-muted mb-0">{{ receipt.receipt_number }}</p>
            </div>
            <div class="text-end">
              <div class="text-muted small">Date</div>
              <div class="fw-bold">{{ formatDate(receipt.payment_date) }}</div>
            </div>
          </div>
          <hr>
        </div>

        <div class="receipt-body">
          <div class="row mb-3">
            <div class="col-md-6">
              <label class="form-label fw-semibold small">Student</label>
              <div class="fw-bold">{{ receipt.student.name }}</div>
              <div class="text-muted small">{{ receipt.student.student_number }}</div>
              <div class="text-muted small">{{ receipt.student.program }}</div>
            </div>
            <div class="col-md-6">
              <label class="form-label fw-semibold small">Semester</label>
              <div class="fw-bold">{{ receipt.semester.name }}</div>
              <div class="text-muted small">{{ receipt.semester.academic_year }}</div>
            </div>
          </div>

          <div class="row mb-3">
            <div class="col-md-4">
              <label class="form-label fw-semibold small">Payment Method</label>
              <div>{{ receipt.method_display }}</div>
            </div>
            <div class="col-md-4">
              <label class="form-label fw-semibold small">Reference</label>
              <div>{{ receipt.reference || "—" }}</div>
            </div>
            <div class="col-md-4 text-md-end">
              <label class="form-label fw-semibold small">Amount Paid</label>
              <div class="fw-bold fs-3 text-success">${{ formatCurrency(receipt.amount) }}</div>
            </div>
          </div>

          <hr>

          <div class="row mb-3">
            <div class="col-md-4">
              <label class="form-label fw-semibold small">Total Charged</label>
              <div class="fw-bold">${{ formatCurrency(receipt.financials.charged) }}</div>
            </div>
            <div class="col-md-4">
              <label class="form-label fw-semibold small">Total Paid</label>
              <div class="fw-bold text-success">${{ formatCurrency(receipt.financials.paid) }}</div>
            </div>
            <div class="col-md-4 text-md-end">
              <label class="form-label fw-semibold small">Outstanding Balance</label>
              <div class="fw-bold" :class="receipt.financials.balance > 0 ? 'text-danger' : (receipt.financials.balance < 0 ? 'text-primary' : 'text-success')">
                ${{ formatCurrency(Math.abs(receipt.financials.balance)) }}
                <span v-if="receipt.financials.balance > 0" class="text-danger"> (Outstanding)</span>
                <span v-else-if="receipt.financials.balance < 0" class="text-primary"> (Credit)</span>
                <span v-else class="text-success"> (Paid in Full)</span>
              </div>
            </div>
          </div>

          <div v-if="receipt.notes" class="mt-3 p-3 bg-light rounded">
            <label class="form-label fw-semibold small">Notes</label>
            <div>{{ receipt.notes }}</div>
          </div>
        </div>

        <div class="receipt-footer mt-4 pt-3 border-top">
          <div class="text-center text-muted small">
            <p class="mb-1">Thank you for your payment.</p>
            <p class="mb-0">This receipt is computer-generated and does not require a signature.</p>
          </div>
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
.primary-link, .secondary-link {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  text-decoration: none;
  border-radius: 10px;
  padding: 0.7rem 1rem;
  font-weight: 600;
}
.primary-link {
  color: white;
  background: #2563eb;
}
.secondary-link {
  color: #111827;
  background: #f3f4f6;
}
.icon { width: 18px; height: 18px; }
.card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.receipt-card {
  padding: 2rem;
  max-width: 600px;
  margin: 0 auto;
}
.receipt-header h4 {
  margin: 0;
  font-size: 1.5rem;
  letter-spacing: 0.1em;
}
.form-label {
  font-weight: 600;
  margin-bottom: 0.3rem;
  display: block;
}
.fw-bold { font-weight: 700; }
.fw-semibold { font-weight: 600; }
.text-muted { color: #6b7280; }
.text-success { color: #16a34a; }
.text-danger { color: #dc2626; }
.text-primary { color: #2563eb; }
.text-center { text-align: center; }
.text-end { text-align: right; }
.text-md-end { text-align: right; }
@media (max-width: 768px) {
  .text-md-end { text-align: left; }
}
.fs-3 { font-size: 1.75rem; }
.small { font-size: 0.85rem; }
.row { display: flex; flex-wrap: wrap; margin: 0 -0.5rem; }
.col-md-4, .col-md-6 {
  padding: 0 0.5rem;
}
.col-md-4 { flex: 0 0 33.333%; max-width: 33.333%; }
.col-md-6 { flex: 0 0 50%; max-width: 50%; }
@media (max-width: 768px) {
  .col-md-4, .col-md-6 { flex: 0 0 100%; max-width: 100%; }
}
.d-flex { display: flex; }
.justify-content-between { justify-content: space-between; }
.align-items-start { align-items: flex-start; }
.align-items-center { align-items: center; }
.gap-2 { gap: 0.5rem; }
.mb-1 { margin-bottom: 0.25rem; }
.mb-2 { margin-bottom: 0.5rem; }
.mb-3 { margin-bottom: 1rem; }
.mb-4 { margin-bottom: 1.5rem; }
.mt-3 { margin-top: 1rem; }
.mt-4 { margin-top: 1.5rem; }
.p-3 { padding: 1rem; }
.bg-light { background: #f9fafb; }
.rounded { border-radius: 8px; }
.hr { border: none; border-top: 1px solid #e5e7eb; margin: 1rem 0; }
.print-only { display: none; }
@media print {
  .hero, .btn, .secondary-link { display: none !important; }
  .page-shell { padding: 0; }
  .card { border: none; box-shadow: none; }
  .print-only { display: block !important; }
  .receipt-card { padding: 0; max-width: 100%; }
}
</style>