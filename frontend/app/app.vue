<template>
  <div class="ui bsoft-app">
    <NuxtRouteAnnouncer />

    <template v-if="isAuthenticated">
      <a class="skip-link" href="#main-content">Skip to content</a>

      <nav class="navbar navbar-dark fixed-top app-navbar" aria-label="Quick actions">
        <div class="nav-shell">
          <button
            class="sidebar-menu-toggle"
            type="button"
            aria-label="Open main navigation"
            :aria-expanded="mobileNavigationOpen"
            @click="mobileNavigationOpen = true"
          >
            <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          </button>

          <NuxtLink class="navbar-brand nav-brand" to="/" aria-label="BSoft Student Management dashboard">
            <svg class="nav-brand-mark" viewBox="0 0 32 32" fill="none" aria-hidden="true">
              <path d="M3 22C8 22 8 12 14 12C20 12 19 21 29 21" stroke="#8AD4CE" stroke-width="1.7" stroke-linecap="round" />
              <path d="M3 26C10 26 11 17 17 17C22 17 23 25 29 25" stroke="#DDF4F1" stroke-width="1.4" stroke-linecap="round" />
              <path d="M4 17C8 17 9 7 15 7C21 7 22 16 28 16" stroke="#55B7BB" stroke-width="1.2" stroke-linecap="round" />
            </svg>
            <span class="nav-brand-name">BSoft</span>
            <span class="nav-brand-product">Student Management</span>
          </NuxtLink>

          <div v-if="user?.permissions.view_student" class="nav-search" :class="{ 'is-expanded': searchExpanded }">
            <div class="nav-search-box">
              <svg class="nav-search-icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <circle cx="8.5" cy="8.5" r="5" stroke="currentColor" stroke-width="1.6" />
                <path d="m12.5 12.5 4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
              </svg>
              <input
                v-model="searchQuery"
                class="nav-search-input"
                type="search"
                placeholder="Find a student: name or number"
                autocomplete="off"
                role="combobox"
                aria-label="Find a student by name or number"
                aria-autocomplete="list"
                :aria-expanded="searchOpen"
                aria-controls="bsoft-search-results"
                @input="searchStudents"
                @focus="searchExpanded = true"
                @keydown.esc="closeSearch"
              >
              <kbd class="nav-search-shortcut">Ctrl K</kbd>
            </div>
            <div v-if="searchOpen" class="nav-search-panel">
              <div id="bsoft-search-results" class="nav-search-results" role="listbox" aria-label="Student search results">
                <p v-if="searchLoading" class="nav-search-empty">Searching…</p>
                <p v-else-if="searchError" class="nav-search-error" role="alert">{{ searchError }}</p>
                <p v-else-if="searchQuery.trim().length < 2" class="nav-search-empty">Type at least 2 characters.</p>
                <p v-else-if="searchResults.length === 0" class="nav-search-empty">No active students found.</p>
                <NuxtLink
                  v-for="student in searchResults"
                  :key="student.id"
                  :to="`/students/${student.id}`"
                  class="nav-search-result"
                  role="option"
                  @click="closeSearch"
                >
                  <span>
                    <strong class="nav-search-name">{{ student.first_name }} {{ student.last_name }}</strong>
                    <span class="nav-search-number">{{ student.student_number }}</span>
                  </span>
                  <span class="nav-search-action">Open</span>
                </NuxtLink>
              </div>
              <NuxtLink to="/students" class="nav-search-archive" @click="closeSearch">Browse all students</NuxtLink>
            </div>
          </div>
          <button v-if="user?.permissions.view_student" class="nav-search-toggle" type="button" aria-label="Find a student" @click="searchExpanded = !searchExpanded">
            <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <circle cx="8.5" cy="8.5" r="5" stroke="currentColor" stroke-width="1.6" />
              <path d="m12.5 12.5 4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
            </svg>
          </button>

          <div class="nav-actions">
            <NuxtLink v-if="user?.permissions.can_record_payments" class="nav-action nav-action--primary" to="/payments/new" title="Record payment">
              <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path d="M3 5.5h14v9H3zM3 8h14M6 12h3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
              <span class="nav-action-label">Record payment</span>
            </NuxtLink>
            <NuxtLink v-if="user?.permissions.view_student" class="nav-action nav-action--secondary" to="/students" title="Open students">
              <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <circle cx="8" cy="6" r="3" stroke="currentColor" stroke-width="1.5" />
                <path d="M2.5 16c.4-3 2.2-4.5 5.5-4.5 1.2 0 2.2.2 3 .7M14 10v6M11 13h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
              </svg>
              <span class="nav-action-label">Students</span>
            </NuxtLink>

            <div class="dropdown">
              <button
                class="nav-user-button"
                type="button"
                aria-label="User menu"
                :aria-expanded="userMenuOpen"
                @click="userMenuOpen = !userMenuOpen"
              >
                <span class="nav-avatar" aria-hidden="true">{{ userInitials }}</span>
                <span class="nav-user-name">{{ user?.username }}</span>
                <svg class="nav-user-chevron" width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                  <path d="m3 4.5 3 3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </button>
              <div v-if="userMenuOpen" class="dropdown-menu dropdown-menu-end nav-dropdown show">
                <div class="nav-user-identity">
                  <strong>{{ user?.first_name || user?.last_name ? `${user.first_name} ${user.last_name}`.trim() : user?.username }}</strong>
                  <span>{{ user?.is_superuser ? 'Administrator' : user?.is_staff ? 'Staff' : 'User' }}</span>
                </div>
                <NuxtLink v-if="user?.is_staff" class="dropdown-item" to="/admin/" @click="userMenuOpen = false">Administration</NuxtLink>
                <button class="dropdown-item nav-logout" type="button" @click="handleLogout">Sign out</button>
              </div>
            </div>
          </div>
        </div>
      </nav>

      <svg class="sidebar-sprite" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
        <defs>
          <symbol id="side-icon-dashboard" viewBox="0 0 20 20"><path d="M3 3h6v6H3zM12 3h5v4h-5zM3 12h6v5H3zM12 10h5v7h-5z" /></symbol>
          <symbol id="side-icon-students" viewBox="0 0 20 20"><circle cx="7.5" cy="6" r="3" /><path d="M2 17v-1a5.5 5.5 0 0 1 11 0v1M13 3.5a3 3 0 0 1 0 5.5M15 11.5a4.5 4.5 0 0 1 3 4.5v1" /></symbol>
          <symbol id="side-icon-enrollment" viewBox="0 0 20 20"><path d="M5 3H3v14h14V3h-2M7 2h6v4H7zM6 10l1.5 1.5L10 9M12 10h2M6 14h8" /></symbol>
          <symbol id="side-icon-history" viewBox="0 0 20 20"><path d="M3 8a7 7 0 1 1 1 7M3 3v5h5M10 6v4l3 2" /></symbol>
          <symbol id="side-icon-ledger" viewBox="0 0 20 20"><path d="M4 2.5h12v15H4zM7 2.5v15M10 6h3M10 10h3M10 14h3" /></symbol>
          <symbol id="side-icon-outstanding" viewBox="0 0 20 20"><circle cx="10" cy="10" r="7" /><path d="M10 6v5M10 14h.01" /></symbol>
          <symbol id="side-icon-collections" viewBox="0 0 20 20"><path d="M3 10v7h14v-7M7 12l3 3 3-3M10 3v11M3 6h3M14 6h3" /></symbol>
          <symbol id="side-icon-payment" viewBox="0 0 20 20"><rect x="2.5" y="4" width="15" height="12" rx="2" /><path d="M3 8h14M6 12h3" /></symbol>
          <symbol id="side-icon-revenue" viewBox="0 0 20 20"><path d="M3 3v14h14M6 12l4-4 3 2 4-6M13 4h4v4" /></symbol>
          <symbol id="side-icon-calendar" viewBox="0 0 20 20"><rect x="3" y="4" width="14" height="13" rx="2" /><path d="M6 2v4M14 2v4M3 8h14M6 11h2M12 11h2M6 14h2M12 14h2" /></symbol>
          <symbol id="side-icon-semester" viewBox="0 0 20 20"><rect x="3" y="4" width="14" height="13" rx="2" /><path d="M6 2v4M14 2v4M3 8h14M7 12h6M10 10v4" /></symbol>
          <symbol id="side-icon-fees" viewBox="0 0 20 20"><path d="M4 2.5h12v15l-3-1.5-3 1.5-3-1.5-3 1.5zM12 6H9a1.5 1.5 0 0 0 0 3h2a1.5 1.5 0 0 1 0 3H8M10 4.5v9" /></symbol>
          <symbol id="side-icon-trade" viewBox="0 0 20 20"><path d="M12 3a4 4 0 0 0-5 5l-4.5 4.5a2.1 2.1 0 0 0 3 3L10 11a4 4 0 0 0 5-5l-2.5 2.5L10 6z" /></symbol>
          <symbol id="side-icon-users" viewBox="0 0 20 20"><circle cx="10" cy="6" r="3" /><path d="M4 17v-1a6 6 0 0 1 12 0v1M2 4v4M18 4v4" /></symbol>
          <symbol id="side-icon-audit" viewBox="0 0 20 20"><path d="M4 2.5h9l3 3V17H4zM12 3v4h4M7 10h6M7 13h6" /></symbol>
          <symbol id="side-icon-backup" viewBox="0 0 20 20"><ellipse cx="10" cy="4.5" rx="6.5" ry="2.5" /><path d="M3.5 4.5v10c0 1.4 2.9 2.5 6.5 2.5s6.5-1.1 6.5-2.5v-10M3.5 9.5C3.5 11 6.4 12 10 12s6.5-1 6.5-2.5" /></symbol>
          <symbol id="side-icon-clock" viewBox="0 0 20 20"><circle cx="10" cy="11" r="6.5" /><path d="M8 2h4M10 2v2M10 7v4l2 2M15 5l1.5-1.5" /></symbol>
          <symbol id="side-icon-reports" viewBox="0 0 20 20"><path d="M3 5h10v12H3zM7 5V2h10v12h-4M6 9h4M6 12h4" /></symbol>
          <symbol id="side-icon-chevron" viewBox="0 0 20 20"><path d="m8 5 5 5-5 5" /></symbol>
          <symbol id="side-icon-collapse" viewBox="0 0 20 20"><path d="M4 3v14M13 5l-5 5 5 5" /></symbol>
          <symbol id="side-icon-close" viewBox="0 0 20 20"><path d="m5 5 10 10M15 5 5 15" /></symbol>
        </defs>
      </svg>

      <aside
        id="main-sidebar"
        class="ui sidebar-fixed offcanvas offcanvas-start"
        :class="{ show: mobileNavigationOpen }"
        aria-label="Main navigation"
      >
        <div class="offcanvas-header sidebar-header">
          <h2>Main navigation</h2>
          <button class="sidebar-close" type="button" aria-label="Close navigation" @click="mobileNavigationOpen = false">
            <svg class="sidebar-icon" aria-hidden="true"><use href="#side-icon-close" /></svg>
          </button>
        </div>
        <nav class="sidebar-nav">
          <NuxtLink v-if="user?.permissions.view_student" class="sidebar-link" :class="{ active: route.path === '/' }" to="/" @click="closeNavigation">
            <svg class="sidebar-icon" aria-hidden="true"><use href="#side-icon-dashboard" /></svg><span class="sidebar-label">Dashboard</span>
          </NuxtLink>
          <details v-for="group in visibleNavigationGroups" :key="group.id" class="sidebar-group" :open="group.items.some(item => isActive(item.to))">
            <summary class="sidebar-heading">
              <span>{{ group.label }}</span><svg class="sidebar-icon sidebar-chevron" aria-hidden="true"><use href="#side-icon-chevron" /></svg>
            </summary>
            <div class="sidebar-items">
              <NuxtLink
                v-for="item in group.items"
                :key="item.to"
                class="sidebar-link"
                :class="{ active: isActive(item.to) }"
                :to="item.to"
                @click="closeNavigation"
              >
                <svg class="sidebar-icon" aria-hidden="true"><use :href="`#side-icon-${item.icon}`" /></svg>
                <span class="sidebar-label">{{ item.label }}</span>
              </NuxtLink>
            </div>
          </details>
          <div class="sidebar-reports">
            <NuxtLink class="sidebar-link" :class="{ active: isActive('/reports') }" to="/reports" @click="closeNavigation">
              <svg class="sidebar-icon" aria-hidden="true"><use href="#side-icon-reports" /></svg><span class="sidebar-label">Reports</span>
            </NuxtLink>
          </div>
        </nav>
        <div class="sidebar-footer">
          <button class="sidebar-rail-toggle" type="button" :aria-expanded="!sidebarCollapsed" @click="toggleSidebar">
            <svg class="sidebar-icon" aria-hidden="true"><use href="#side-icon-collapse" /></svg>
            <span class="sidebar-label">{{ sidebarCollapsed ? 'Expand navigation' : 'Collapse navigation' }}</span>
          </button>
        </div>
      </aside>
      <button v-if="mobileNavigationOpen" class="offcanvas-backdrop show" type="button" aria-label="Close navigation" @click="mobileNavigationOpen = false" />

      <main id="main-content" class="main-content" tabindex="-1">
        <p v-if="logoutError" class="alert alert-danger" role="alert">{{ logoutError }}</p>
        <NuxtPage />
      </main>
    </template>
    <main v-else class="auth-content"><NuxtPage /></main>
  </div>
</template>

<script setup lang="ts">
interface NavigationItem {
  label: string;
  to: string;
  icon: string;
}

const route = useRoute();
const { isAuthenticated, user, logout } = useAuth();
const router = useRouter();
const api = useApi();
const userMenuOpen = ref(false);
const mobileNavigationOpen = ref(false);
const sidebarCollapsed = ref(false);
const logoutError = ref('');
const searchQuery = ref('');
const searchResults = ref<Array<{ id: number; student_number: string; first_name: string; last_name: string }>>([]);
const searchLoading = ref(false);
const searchError = ref('');
const searchExpanded = ref(false);
const searchOpen = ref(false);
let searchTimer: ReturnType<typeof setTimeout> | undefined;

const navigationGroups: Array<{ id: string; label: string; items: Array<NavigationItem & { permission: string }> }> = [
  { id: 'people', label: 'People', items: [
    { label: 'Students', to: '/students', icon: 'students', permission: 'view_student' },
    { label: 'Student archive', to: '/students/archive', icon: 'history', permission: 'view_student' },
    { label: 'Import students', to: '/students/import', icon: 'backup', permission: 'add_student' },
    { label: 'Enrollment', to: '/reports/enrollment', icon: 'enrollment', permission: 'view_student' },
    { label: 'Status history', to: '/reports/status-history', icon: 'history', permission: 'view_studentstatuslog' },
  ] },
  { id: 'money', label: 'Money', items: [
    { label: 'Financial records', to: '/financial-records', icon: 'ledger', permission: 'can_view_financial_reports' },
    { label: 'Outstanding', to: '/reports/outstanding', icon: 'outstanding', permission: 'can_view_outstanding_reports' },
    { label: 'Daily collections', to: '/reports/daily-collections', icon: 'collections', permission: 'can_view_financial_reports' },
    { label: 'Payment methods', to: '/reports/payment-methods', icon: 'payment', permission: 'can_view_financial_reports' },
    { label: 'Program revenue', to: '/reports/program-revenue', icon: 'revenue', permission: 'can_view_financial_reports' },
  ] },
  { id: 'academics', label: 'Academics', items: [
    { label: 'Academic years', to: '/academic-years', icon: 'calendar', permission: 'view_academicyear' },
    { label: 'Semesters', to: '/semesters', icon: 'semester', permission: 'view_semester' },
    { label: 'Fee setup', to: '/fee-setup', icon: 'fees', permission: 'view_feestructure' },
    { label: 'Trades', to: '/programs', icon: 'trade', permission: 'view_program' },
    { label: 'Fee audit', to: '/reports/fee-audit', icon: 'audit', permission: 'view_feestructure' },
  ] },
  { id: 'system', label: 'System', items: [
    { label: 'Users', to: '/users', icon: 'users', permission: 'superuser' },
    { label: 'Audit trail', to: '/audit-logs', icon: 'audit', permission: 'view_auditlog' },
    { label: 'Backups', to: '/backups', icon: 'backup', permission: 'superuser' },
    { label: 'Time override', to: '/time-override', icon: 'clock', permission: 'time_override' },
  ] },
];

const visibleNavigationGroups = computed(() => navigationGroups
  .map(group => ({
    ...group,
    items: group.items.filter(item => {
      if (item.permission === 'superuser') return Boolean(user.value?.is_superuser);
      if (item.permission === 'time_override') return Boolean(user.value?.is_superuser && user.value.permissions.time_override);
      return Boolean(user.value?.permissions[item.permission]);
    }),
  }))
  .filter(group => group.items.length > 0));

const userInitials = computed(() => {
  const first = user.value?.first_name?.[0] || '';
  const last = user.value?.last_name?.[0] || '';
  return `${first}${last}` || user.value?.username?.slice(0, 2) || 'BS';
});

function isActive(path: string): boolean {
  return route.path === path || (path !== '/reports' && route.path.startsWith(`${path}/`));
}

function closeNavigation() {
  mobileNavigationOpen.value = false;
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value;
  document.documentElement.classList.toggle('sidebar-collapsed', sidebarCollapsed.value);
  localStorage.setItem('school:sidebar:collapsed', String(sidebarCollapsed.value));
}

function closeSearch() {
  searchOpen.value = false;
  searchExpanded.value = false;
}

function searchStudents() {
  searchOpen.value = true;
  searchError.value = '';
  if (searchTimer) clearTimeout(searchTimer);

  const query = searchQuery.value.trim();
  if (query.length < 2) {
    searchResults.value = [];
    searchLoading.value = false;
    return;
  }

  searchLoading.value = true;
  searchTimer = setTimeout(async () => {
    try {
      const response = await api.get<{ students: typeof searchResults.value }>(
        `/api/students/search/?q=${encodeURIComponent(query)}`,
      );
      searchResults.value = response.students;
    } catch (error) {
      searchError.value = error instanceof Error ? error.message : 'Student search failed.';
    } finally {
      searchLoading.value = false;
    }
  }, 250);
}

async function handleLogout() {
  logoutError.value = '';
  try {
    await logout();
    await router.push('/login');
  } catch (error) {
    logoutError.value = error instanceof Error ? error.message : 'Sign out failed.';
  }
}

onMounted(() => {
  sidebarCollapsed.value = localStorage.getItem('school:sidebar:collapsed') === 'true';
  document.documentElement.classList.toggle('sidebar-collapsed', sidebarCollapsed.value);
  window.addEventListener('keydown', onGlobalKeydown);
});

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onGlobalKeydown);
  if (searchTimer) clearTimeout(searchTimer);
  document.documentElement.classList.remove('sidebar-collapsed');
});

function onGlobalKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    searchExpanded.value = true;
    searchOpen.value = true;
    document.querySelector<HTMLInputElement>('.nav-search-input')?.focus();
  } else if (event.key === 'Escape') {
    closeSearch();
    closeNavigation();
    userMenuOpen.value = false;
  }
}
</script>

<style>
:root {
  --nav-h: 60px;
  --side-w: 232px;
}
html, body, #__nuxt {
  min-height: 100%;
  margin: 0;
}
body {
  background: #f8f9fa;
}
.bsoft-app {
  min-height: 100vh;
  background: #f8f9fa;
}
.main-content {
  margin-left: var(--side-w);
  margin-top: var(--nav-h);
  min-height: calc(100vh - var(--nav-h));
  height: calc(100vh - var(--nav-h));
  overflow-y: auto;
  padding: 0.8rem 1.2rem;
}
.auth-content {
  min-height: 100vh;
}
.sidebar-sprite {
  position: absolute;
  width: 0;
  height: 0;
  overflow: hidden;
  pointer-events: none;
}
.sidebar-backdrop {
  display: none;
}
@media (max-width: 768px) {
  .main-content {
    margin-left: 0;
    padding: 0.8rem;
  }
  .sidebar-backdrop.show {
    position: fixed;
    inset: 0;
    z-index: 1010;
    display: block;
    border: 0;
    background: rgb(0 0 0 / 45%);
  }
  .ui.sidebar-fixed.show {
    visibility: visible;
    transform: translateX(0);
  }
}
@media print {
  .main-content {
    height: auto;
    min-height: 0;
    margin: 0;
    overflow: visible;
  }
}
</style>
