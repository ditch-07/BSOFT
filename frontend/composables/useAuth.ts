interface User {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  is_staff: boolean;
  is_superuser: boolean;
  permissions: Record<string, boolean>;
}

export function useAuth() {
  const api = useApi();
  const isAuthenticated = useState('auth:isAuthenticated', () => false);
  const user = useState<User | null>('auth:user', () => null);
  const checked = useState('auth:checked', () => false);

  async function checkAuth() {
    if (checked.value) return isAuthenticated.value;
    const response = await api.get<{ authenticated: boolean; user: User | null }>('/api/auth/check/');
    isAuthenticated.value = response.authenticated;
    user.value = response.user;
    checked.value = true;
    return isAuthenticated.value;
  }

  async function login(username: string, password: string) {
    await api.post('/api/auth/login/', { username, password });
    checked.value = false;
    await checkAuth();
  }

  async function logout() {
    await api.post('/api/auth/logout/', {});
    isAuthenticated.value = false;
    user.value = null;
    checked.value = true;
  }

  return {
    isAuthenticated,
    user,
    checkAuth,
    login,
    logout,
  };
}