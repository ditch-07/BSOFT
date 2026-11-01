export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },
  ssr: false,
  runtimeConfig: {
    public: {
      apiBaseUrl: '',
    },
  },
  app: {
    head: {
      title: 'NRZ Student Management',
      meta: [{ name: 'viewport', content: 'width=device-width, initial-scale=1' }],
      link: [
        { rel: 'icon', type: 'image/x-icon', href: '/static/favicon.ico' },
      ],
    },
    baseURL: '/',
    buildAssetsDir: '/static/nuxt/_nuxt/',
  },
  nitro: {
    prerender: {
      crawlLinks: false,
      routes: ['/'],
    },
    devProxy: {
      '/api': { target: 'http://localhost:8000/api', changeOrigin: true },
      '/admin': { target: 'http://localhost:8000/admin', changeOrigin: true },
      '/static': { target: 'http://localhost:8000/static', changeOrigin: true },
    },
  },
})