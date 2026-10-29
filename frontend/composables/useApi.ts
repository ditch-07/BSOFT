export function useApi() {
  const config = useRuntimeConfig();
  const baseUrl = config.public.apiBaseUrl || 'http://127.0.0.1:8000';

  const request = async <T>(path: string, options: Record<string, any> = {}): Promise<T> => {
    const headers = new Headers(options.headers || {});
    if (!headers.has('Accept')) {
      headers.set('Accept', 'application/json');
    }
    if (options.body && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }

    return await $fetch<T>(`${baseUrl}${path}`, {
      ...options,
      body: options.body && typeof options.body !== 'string' && !(options.body instanceof FormData)
        ? JSON.stringify(options.body)
        : options.body,
      credentials: 'include',
      headers,
    });
  };

  return {
    async get<T>(path: string): Promise<T> {
      return await request<T>(path, { method: 'GET' });
    },
    async post<T>(path: string, body: Record<string, any>): Promise<T> {
      return await request<T>(path, { method: 'POST', body });
    },
    async patch<T>(path: string, body: Record<string, any>): Promise<T> {
      return await request<T>(path, { method: 'PATCH', body });
    },
    async put<T>(path: string, body: Record<string, any>): Promise<T> {
      return await request<T>(path, { method: 'PUT', body });
    },
  };
}
