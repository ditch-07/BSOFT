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
      title: 'BSoft Student Management',
      meta: [{ name: 'viewport', content: 'width=device-width, initial-scale=1' }],
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/static/img/favicon.svg' },
        { rel: 'stylesheet', href: '/static/vendor/bootstrap/bootstrap.min.css' },
        { rel: 'stylesheet', href: '/static/css/bootstrap-icons-offline.css' },
        { rel: 'stylesheet', href: '/static/css/app.css' },
        { rel: 'stylesheet', href: '/static/css/ui.css' },
        { rel: 'stylesheet', href: '/static/css/navbar.css' },
        { rel: 'stylesheet', href: '/static/css/sidebar.css' },
        { rel: 'stylesheet', href: '/static/css/dashboard.css' },
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