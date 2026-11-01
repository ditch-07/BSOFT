export function useApi() {
  const config = useRuntimeConfig();
  const baseUrl = String(config.public.apiBaseUrl || '').replace(/\/$/, '');

  const request = async <T>(path: string, options: Record<string, any> = {}): Promise<T> => {
    const headers = new Headers(options.headers || {});
    const body = options.body;
    const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;

    if (!headers.has('Accept')) {
      headers.set('Accept', 'application/json');
    }
    if (body != null && !isFormData && typeof body !== 'string' && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }

    if (typeof document !== 'undefined' && !['GET', 'HEAD', 'OPTIONS'].includes(options.method || 'GET')) {
      const csrfCookie = document.cookie
        .split('; ')
        .find((cookie) => cookie.startsWith('csrftoken='));
      if (csrfCookie && !headers.has('X-CSRFToken')) {
        headers.set('X-CSRFToken', decodeURIComponent(csrfCookie.slice('csrftoken='.length)));
      }
    }

    return await $fetch<T>(`${baseUrl}${path}`, {
      ...options,
      body: body != null && !isFormData && typeof body !== 'string'
        ? JSON.stringify(body)
        : body,
      credentials: 'include',
      headers,
    });
  };

  return {
    async get<T>(path: string): Promise<T> {
      return await request<T>(path, { method: 'GET' });
    },
    async post<T>(path: string, body: Record<string, any> | FormData): Promise<T> {
      return await request<T>(path, { method: 'POST', body });
    },
    async patch<T>(path: string, body: Record<string, any> | FormData): Promise<T> {
      return await request<T>(path, { method: 'PATCH', body });
    },
    async put<T>(path: string, body: Record<string, any> | FormData): Promise<T> {
      return await request<T>(path, { method: 'PUT', body });
    },
  };
}
