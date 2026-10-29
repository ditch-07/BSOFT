<script setup lang="ts">
const api = useApi();
const { data, pending, error } = await useAsyncData('fee-setup', async () => {
  const semesters = await api.get<{ count: number; results: Array<{ id: number; name: string; academic_year: string; number: number }> }>('/api/semesters/');
  const selectedSemester = semesters.results[0];

  if (!selectedSemester) {
    return { semesters: semesters.results, selectedSemester: null, feeStructures: [] };
  }

  const feeStructures = await api.get<{ count: number; results: Array<{ id: number; program: { id: number; name: string; code: string }; year_level: number; total: number; items: Array<{ name: string; amount: number; description: string | null }> }> }(`/api/semesters/${selectedSemester.id}/fee-structures/`);

  return {
    semesters: semesters.results,
    selectedSemester,
    feeStructures: feeStructures.results,
  };
});

const semesters = computed(() => data.value?.semesters ?? []);
const feeStructures = computed(() => data.value?.feeStructures ?? []);
const selectedSemester = computed({
  get: () => data.value?.selectedSemester ?? null,
  set: (value) => {
    if (!data.value) return;
    data.value.selectedSemester = value;
  },
});

const refresh = async () => {
  const next = await api.get<{ count: number; results: Array<{ id: number; name: string; academic_year: string; number: number }> }>('/api/semesters/');
  const chosen = next.results[0] ?? null;
  data.value = {
    semesters: next.results,
    selectedSemester: chosen,
    feeStructures: chosen ? ((await api.get<{ count: number; results: Array<{ id: number; program: { id: number; name: string; code: string }; year_level: number; total: number; items: Array<{ name: string; amount: number; description: string | null }> }> }(`/api/semesters/${chosen.id}/fee-structures/`)).results) : [],
  };
};

const loadSemester = async (semesterId: number) => {
  const chosen = semesters.value.find((semester) => semester.id === semesterId) ?? null;
  if (!chosen) return;

  const feeStructuresForSemester = await api.get<{ count: number; results: Array<{ id: number; program: { id: number; name: string; code: string }; year_level: number; total: number; items: Array<{ name: string; amount: number; description: string | null }> }> }(`/api/semesters/${chosen.id}/fee-structures/`);
  data.value = {
    semesters: semesters.value,
    selectedSemester: chosen,
    feeStructures: feeStructuresForSemester.results,
  };
};
</script>

<template>
  <div class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Fee setup</p>
        <h1>Semester fee configuration</h1>
      </div>
      <button class="primary-link" @click="refresh">Refresh</button>
    </section>

    <div v-if="pending" class="state-card">Loading fee setup…</div>
    <div v-else-if="error" class="state-card error">Unable to load fee setup. {{ error.message }}</div>

    <div v-else class="panel-grid">
      <div class="card">
        <h2>Semester</h2>
        <select :value="selectedSemester?.id ?? ''" @change="(event) => loadSemester(Number((event.target as HTMLSelectElement).value))">
          <option v-for="semester in semesters" :key="semester.id" :value="semester.id">
            {{ semester.name }}
          </option>
        </select>
      </div>

      <div class="card wide">
        <h2>Fee structures</h2>
        <div v-if="feeStructures.length === 0" class="empty-state">No fee structures configured for this semester.</div>
        <div v-else class="structure-list">
          <div v-for="structure in feeStructures" :key="structure.id" class="structure-item">
            <div class="structure-header">
              <strong>{{ structure.program.name }}</strong>
              <span>Year {{ structure.year_level }}</span>
            </div>
            <div class="total">Total: {{ structure.total.toFixed(2) }}</div>
            <ul>
              <li v-for="item in structure.items" :key="`${structure.id}-${item.name}`">
                {{ item.name }} — {{ item.amount.toFixed(2) }}
                <small v-if="item.description">({{ item.description }})</small>
              </li>
            </ul>
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
  border: none;
  border-radius: 10px;
  padding: 0.75rem 1rem;
  font-weight: 600;
  cursor: pointer;
}
.panel-grid {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  gap: 1rem;
}
.card,
.state-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 1.2rem;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.card h2 {
  margin-top: 0;
}
select {
  width: 100%;
  padding: 0.7rem 0.8rem;
  border: 1px solid #d1d5db;
  border-radius: 8px;
}
.structure-list {
  display: grid;
  gap: 1rem;
}
.structure-item {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 0.9rem 1rem;
  background: #f9fafb;
}
.structure-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}
.total {
  font-weight: 600;
  margin-bottom: 0.5rem;
}
ul {
  margin: 0;
  padding-left: 1.2rem;
}
.empty-state {
  color: #6b7280;
}
.error {
  color: #b91c1c;
}
@media (max-width: 760px) {
  .panel-grid {
    grid-template-columns: 1fr;
  }
}
</style>
