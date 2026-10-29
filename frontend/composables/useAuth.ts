import { ref } from 'vue';

interface User {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  is_staff: boolean;
  is_superuser: boolean;
}

const isAuthenticated = ref(false);
const user = ref<User | null>(null);
let checked = false;

export function useAuth() {
  const api = useApi();

  async function checkAuth() {
    if (checked) return isAuthenticated.value;
    checked = true;
    try {
      const response = await api.get<{ authenticated: boolean; user: User | null }>('/api/auth/check/');
      isAuthenticated.value = response.authenticated;
      user.value = response.user;
    } catch {
      isAuthenticated.value = false;
      user.value = null;
    }
    return isAuthenticated.value;
  }

  async function login(username: string, password: string) {
    await api.post('/api/auth/login/', { username, password });
    await checkAuth();
  }

  async function logout() {
    await api.post('/api/auth/logout/', {});
    isAuthenticated.value = false;
    user.value = null;
  }

  return {
    isAuthenticated,
    user,
    checkAuth,
    login,
    logout,
  };
}