<script setup lang="ts">
interface DashboardStudent {
  id: number;
  name: string;
  student_number: string;
  program: string;
  balance: number;
  balance_percent: number;
}

interface DashboardData {
  total_students: number;
  today: string;
  current_year: string | null;
  current_semester: string | null;
  semester: {
    name: string;
    start_date: string;
    end_date: string;
    is_upcoming: boolean;
    days_until: number;
    week: number;
    weeks: number;
    progress_percent: number;
  } | null;
  can_view_financials: boolean;
  can_view_outstanding: boolean;
  today_total: number;
  today_count: number;
  financials: {
    charged: number;
    paid: number;
    outstanding: number;
    collection_rate: number;
    expected_revenue_year: number;
  } | null;
  recent_payments: Array<{
    id: number;
    student_id: number;
    student_name: string;
    student_number: string;
    program: string;
    method: string;
    payment_date: string;
    amount: number;
    student_active: boolean;
  }>;
  outstanding: {
    total: number;
    students_count: number;
    has_charges: boolean;
    students: DashboardStudent[];
  } | null;
}

const api = useApi();
const { data, pending, error } = await useAsyncData(
  'dashboard',
  () => api.get<DashboardData>('/api/dashboard/'),
);

const dateLabel = computed(() => {
  if (!data.value?.today) return '';
  return new Date(`${data.value.today}T12:00:00`).toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
});

function currency(value: number | null | undefined): string {
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value ?? 0);
}

function paymentDate(value: string): string {
  if (value === data.value?.today) return 'Today';
  return new Date(`${value}T12:00:00`).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}
</script>

<template>
  <div class="db ui">
    <header class="db-head">
      <div class="db-title-group">
        <h1>Dashboard</h1>
        <p>{{ dateLabel }}<template v-if="data?.current_year"> · {{ data.current_year }} academic year</template></p>
      </div>
      <div v-if="data?.semester" class="db-period">
        <div class="db-period-name">
          <strong>{{ data.semester.name }}</strong>
          <span class="db-status">
            <span class="ui-lamp" :class="data.semester.is_upcoming ? 'ui-lamp--amber' : 'ui-lamp--green'" aria-hidden="true" />
            {{ data.semester.is_upcoming ? 'Upcoming' : 'Active' }}
          </span>
        </div>
        <span class="db-period-dates">
          {{ new Date(`${data.semester.start_date}T12:00:00`).toLocaleDateString() }}
          – {{ new Date(`${data.semester.end_date}T12:00:00`).toLocaleDateString() }}
        </span>
        <div class="db-term-rail" aria-hidden="true">
          <span :style="{ left: `${data.semester.progress_percent}%` }" />
        </div>
        <span class="db-period-timing">
          <template v-if="data.semester.is_upcoming">
            Starts in {{ data.semester.days_until }} day{{ data.semester.days_until === 1 ? '' : 's' }}
          </template>
          <template v-else>Today · Week {{ data.semester.week }} of {{ data.semester.weeks }}</template>
        </span>
      </div>
      <p v-if="!data?.semester" class="db-context">
        No semester is active or scheduled.
      </p>
      <p v-else-if="data.semester.is_upcoming" class="db-context">
        No semester is active. Figures are for the upcoming {{ data.semester.name }}.
      </p>
      <div v-if="error" class="ui-banner db-banner" role="alert">
        <span class="ui-lamp ui-lamp--red" aria-hidden="true" />
        <div>Unable to load dashboard data. {{ error.message }}</div>
      </div>
    </header>

    <div v-if="pending" class="ui-card db-empty" role="status">Loading dashboard…</div>
    <template v-else-if="data">
      <section
        class="db-kpis"
        :class="{
          'db-kpis--people': !data.can_view_financials && !data.can_view_outstanding,
          'db-kpis--three': data.can_view_financials && !data.can_view_outstanding,
          'db-kpis--two': !data.can_view_financials && data.can_view_outstanding,
        }"
        aria-label="Headline figures"
      >
        <article class="ui-card db-kpi" data-kpi="students">
          <h2><NuxtLink to="/students">Active students <span aria-hidden="true">↗</span></NuxtLink></h2>
          <div class="ui-fig db-kpi-value">{{ data.total_students }}</div>
          <p>Currently active across all trades</p>
        </article>
        <template v-if="data.can_view_financials">
          <article class="ui-card db-kpi" data-kpi="billed">
            <h2><NuxtLink to="/financial-records">Billed <span aria-hidden="true">↗</span></NuxtLink></h2>
            <div v-if="data.semester && data.financials" class="ui-fig db-kpi-value">${{ currency(data.financials.charged) }}</div>
            <div v-else class="db-kpi-empty">No semester</div>
            <p v-if="data.financials">${{ currency(data.financials.expected_revenue_year) }} for the full academic year</p>
            <p v-else>Charges will appear when a semester is set up.</p>
          </article>
          <article class="ui-card db-kpi" data-kpi="collected">
            <h2><NuxtLink to="/reports/daily-collections">Collected <span aria-hidden="true">↗</span></NuxtLink></h2>
            <div v-if="data.financials" class="ui-fig db-kpi-value db-positive">${{ currency(data.financials.paid) }}</div>
            <div v-else class="db-kpi-empty">No semester</div>
            <div v-if="data.financials" class="db-collection">
              <div class="db-rail" aria-hidden="true"><span :style="{ width: `${Math.min(data.financials.collection_rate, 100)}%` }" /></div>
              <span>{{ data.financials.collection_rate.toFixed(0) }}%</span>
            </div>
            <p>Today: <span class="ui-fig">${{ currency(data.today_total) }}</span> · {{ data.today_count }} payment{{ data.today_count === 1 ? '' : 's' }}</p>
          </article>
        </template>
        <article v-if="data.can_view_outstanding" class="ui-card db-kpi" data-kpi="owed">
          <h2><NuxtLink to="/reports/outstanding">Still owed <span aria-hidden="true">↗</span></NuxtLink></h2>
          <div v-if="data.outstanding" class="ui-fig db-kpi-value" :class="{ 'db-negative': data.outstanding.total > 0 }">${{ currency(data.outstanding.total) }}</div>
          <div v-else class="db-kpi-empty">No semester</div>
          <p v-if="data.outstanding">{{ data.outstanding.students_count }} student{{ data.outstanding.students_count === 1 ? '' : 's' }} owing</p>
        </article>
      </section>

      <div v-if="data.can_view_financials || data.can_view_outstanding" class="db-columns">
        <section v-if="data.can_view_financials" class="ui-card db-payments" aria-labelledby="recent-title">
          <div class="ui-section-head db-card-head">
            <h2 id="recent-title">Recent payments</h2>
            <p>Latest receipts · all semesters</p>
          </div>
          <div v-if="data.recent_payments.length" class="db-table-scroll" tabindex="0" role="region" aria-label="Recent payments">
            <table class="ui-table">
              <thead>
                <tr><th>Student</th><th>Trade</th><th>Method</th><th>Date</th><th class="ui-num">Amount</th><th><span class="visually-hidden">Actions</span></th></tr>
              </thead>
              <tbody>
                <tr v-for="payment in data.recent_payments" :key="payment.id">
                  <td>
                    <NuxtLink class="db-student" :to="`/students/${payment.student_id}`">{{ payment.student_name }}</NuxtLink>
                    <span class="db-student-number">{{ payment.student_number }}</span>
                  </td>
                  <td class="db-trade">{{ payment.program || '—' }}</td>
                  <td><span class="ui-chip">{{ payment.method }}</span></td>
                  <td class="db-date">{{ paymentDate(payment.payment_date) }}</td>
                  <td class="ui-num ui-fig">${{ currency(payment.amount) }}</td>
                  <td>
                    <NuxtLink
                      v-if="payment.student_active"
                      class="ui-btn ui-btn--quiet db-small-action"
                      :to="`/payments/new?student=${payment.student_id}`"
                      :aria-label="`Record payment for ${payment.student_name}`"
                    >Pay</NuxtLink>
                    <span v-else class="ui-btn db-small-action" aria-disabled="true" title="Payments are available only for active students">Pay</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="db-empty"><strong>No payments recorded yet.</strong><p>New receipts will appear here as payments are recorded.</p></div>
          <footer class="db-card-foot"><NuxtLink to="/financial-records">All payments <span aria-hidden="true">→</span></NuxtLink></footer>
        </section>

        <section v-if="data.can_view_outstanding" class="ui-card db-balances" aria-labelledby="balances-title">
          <div class="ui-section-head db-card-head">
            <h2 id="balances-title">Highest balances</h2>
            <p>{{ data.semester?.is_upcoming ? 'Upcoming semester' : 'This semester' }}</p>
          </div>
          <ul v-if="data.outstanding?.students.length" class="db-balance-list">
            <li v-for="student in data.outstanding.students" :key="student.id">
              <div class="db-balance-top">
                <div>
                  <NuxtLink class="db-student" :to="`/students/${student.id}`">{{ student.name }}</NuxtLink>
                  <span class="db-student-number">{{ student.student_number }}</span>
                </div>
                <span class="ui-fig db-negative">${{ currency(student.balance) }}</span>
              </div>
              <div class="db-balance-meta">{{ student.program }}</div>
              <div class="db-balance-bottom">
                <div class="db-rail" aria-hidden="true"><span :style="{ width: `${student.balance_percent}%` }" /></div>
                <div class="db-row-actions">
                  <NuxtLink class="ui-btn ui-btn--ghost db-small-action" :to="`/students/${student.id}`">Open</NuxtLink>
                  <NuxtLink class="ui-btn ui-btn--quiet db-small-action" :to="`/payments/new?student=${student.id}`">Pay</NuxtLink>
                </div>
              </div>
            </li>
          </ul>
          <div v-else-if="!data.semester" class="db-empty"><strong>No semester to report on.</strong><p>Balances appear once a semester is active or scheduled.</p></div>
          <div v-else-if="!data.outstanding?.has_charges" class="db-empty"><strong>No charges recorded yet.</strong><p>Balances are not available until students have been billed.</p></div>
          <div v-else class="db-empty db-all-clear"><span class="ui-lamp ui-lamp--green" aria-hidden="true" /><strong>Everyone is up to date.</strong></div>
          <footer v-if="data.outstanding?.students_count" class="db-card-foot">
            <NuxtLink to="/reports/outstanding">Outstanding report <span aria-hidden="true">→</span></NuxtLink>
          </footer>
        </section>
      </div>
    </template>
  </div>
</template>
