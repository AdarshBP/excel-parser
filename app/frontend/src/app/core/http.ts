import { HttpInterceptorFn } from '@angular/common/http';

/** Send the session cookie, and echo the CSRF cookie back on writes. */
export const sessionInterceptor: HttpInterceptorFn = (request, next) => {
  const token = document.cookie
    .split('; ')
    .find((part) => part.startsWith('ep_csrf='))
    ?.split('=')[1];
  const write = !['GET', 'HEAD', 'OPTIONS'].includes(request.method);
  return next(
    request.clone({
      withCredentials: true,
      setHeaders: write && token ? { 'X-CSRF-Token': decodeURIComponent(token) } : {},
    }),
  );
};
