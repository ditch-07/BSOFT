export default defineNuxtRouteMiddleware(async (to) => {
  const { checkAuth, isAuthenticated } = useAuth();
  await checkAuth();

  if (!isAuthenticated.value && to.path !== '/login') {
    return navigateTo({
      path: '/login',
      query: { redirect: to.fullPath },
    });
  }

  if (isAuthenticated.value && to.path === '/login') {
    return navigateTo('/');
  }
});
