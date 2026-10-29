<script setup lang="ts">
const api = useApi();
const { data, pending, error } = await useAsyncData('semesters', () => api.get<{
  count: number;
  results: Array<{ id: number; name: string; academic_year: string; number: number; start_date: string | null; end_date: string | null; status: string }>;
}>('/api/semesters/'));
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Academic setup</p>
        <h1>Semesters</h1>
      </div>
      <NuxtLink to="/programs" class="primary-link">Manage programs</NuxtLink>
    </section>

    <div v-if="pending" class="state-card">Loading semesters…</div>
    <div v-else-if="error" class="state-card error">Unable to load semesters. {{ error.message }}</div>

    <div v-else class="table-card">
      <div class="table-header">
        <h2>Semester schedule</h2>
        <span>{{ data?.count ?? 0 }} records</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Year</th>
            <th>Number</th>
            <th>Dates</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="semester in data?.results ?? []" :key="semester.id">
            <td>{{ semester.name }}</td>
            <td>{{ semester.academic_year }}</td>
            <td>{{ semester.number }}</td>
            <td>{{ semester.start_date ?? '—' }} → {{ semester.end_date ?? '—' }}</td>
            <td>{{ semester.status }}</td>
          </tr>
        </tbody>
      </table>
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
.table-card,
.state-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 1.2rem;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th, td {
  border-bottom: 1px solid #e5e7eb;
  padding: 0.75rem 0.5rem;
  text-align: left;
}
.error {
  color: #b91c1c;
}
</style>
