import { Injectable, inject, signal } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of, tap } from 'rxjs';
import { Api } from './api';
import { Me } from './models';

@Injectable({ providedIn: 'root' })
export class Auth {
  private api = inject(Api);
  readonly user = signal<Me | null>(null);

  /** Ask the backend who we are; the cookie is the only source of truth. */
  refresh() {
    return this.api.me().pipe(
      tap((me) => this.user.set(me)),
      map(() => true),
      catchError(() => {
        this.user.set(null);
        return of(false);
      }),
    );
  }

  login(username: string, password: string) {
    return this.api.login(username, password).pipe(tap((me) => this.user.set(me)));
  }

  logout() {
    return this.api.logout().pipe(tap(() => this.user.set(null)));
  }
}

export const authGuard: CanActivateFn = () => {
  const auth = inject(Auth);
  const router = inject(Router);
  if (auth.user()) return true;
  return auth.refresh().pipe(
    map((ok) => ok || router.createUrlTree(['/login'])),
  );
};
