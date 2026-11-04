<script setup lang="ts">
const api = useApi();
const { user } = useAuth();
const { data, pending, error } = await useAsyncData('students', () => api.get<{ count: number; results: Array<{ id: number; name: string; student_number: string; program: string | null; current_semester: string | null }> }>('/api/students/'));
</script>

<template>
  <div class="page-shell">
    <div class="heading-row">
      <div>
        <p class="eyebrow">People</p>
        <h1>Students</h1>
      </div>
      <div class="heading-actions">
        <NuxtLink to="/students/archive" class="btn btn-outline-secondary">Student archive</NuxtLink>
        <NuxtLink v-if="user?.permissions.add_student" to="/students/import" class="btn btn-outline-primary">Import students</NuxtLink>
        <NuxtLink v-if="user?.permissions.add_student" to="/students/new" class="btn btn-primary">Register student</NuxtLink>
        <NuxtLink to="/" class="secondary-link">Back to dashboard</NuxtLink>
      </div>
    </div>

    <div v-if="pending" class="card">Loading students…</div>
    <div v-else-if="error" class="card error">Unable to load students. {{ error.message }}</div>
    <div v-else class="card table-wrap">
      <table>
        <thead>
          <tr>
            <th>Student</th>
            <th>Number</th>
            <th>Program</th>
            <th>Semester</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="student in data?.results ?? []" :key="student.id">
            <td><NuxtLink :to="`/students/${student.id}`">{{ student.name }}</NuxtLink></td>
            <td>{{ student.student_number }}</td>
            <td>{{ student.program ?? 'Not assigned' }}</td>
            <td>{{ student.current_semester ?? 'No active semester' }}</td>
          </tr>
        </tbody>
      </table>
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
.heading-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
}
.eyebrow {
  margin: 0 0 0.4rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 0.7rem;
  color: #6b7280;
}
h1 {
  margin: 0;
}
.card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 1rem;
}
.secondary-link {
  text-decoration: none;
  color: #111827;
  background: #f3f4f6;
  border-radius: 10px;
  padding: 0.7rem 1rem;
  font-weight: 600;
}
.table-wrap {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th, td {
  text-align: left;
  padding: 0.8rem 0.6rem;
  border-bottom: 1px solid #e5e7eb;
}
.error {
  color: #b91c1c;
}
</style>
