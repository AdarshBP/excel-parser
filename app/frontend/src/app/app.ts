import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MessageService } from '@openng/optimus-ui/api';
import { ButtonModule } from '@openng/optimus-ui/button';
import { ToastModule } from '@openng/optimus-ui/toast';
import { TooltipModule } from '@openng/optimus-ui/tooltip';
import { Auth } from './core/auth';
import { Settings } from './core/settings';

@Component({
  imports: [RouterOutlet, RouterLink, RouterLinkActive, ButtonModule, ToastModule, TooltipModule],
  providers: [MessageService],
  selector: 'app-root',
  template: `
    <p-toast position="top-right" />
    <div class="rotate-notice">
      <i class="pi pi-sync"></i>
      <h2>Please rotate your device</h2>
      <p>This application is designed for landscape orientation.
         Rotate your tablet to horizontal mode for the best experience.</p>
    </div>
    @if (auth.user(); as user) {
      <div class="shell">
        <nav class="sidenav">
          <div class="nav-brand" routerLink="/work">
            <i class="pi pi-th-large"></i>
            <span class="nav-text">Excel Parser</span>
          </div>

          <div class="nav-links">
            <a class="nav-item" routerLink="/work" routerLinkActive="active"
               [routerLinkActiveOptions]="{ exact: true }">
              <i class="pi pi-briefcase"></i>
              <span class="nav-text">My work</span>
            </a>
            <a class="nav-item" routerLink="/batch" routerLinkActive="active">
              <i class="pi pi-upload"></i>
              <span class="nav-text">Batch run</span>
            </a>
            @if (settings.auditLog()) {
              <a class="nav-item" routerLink="/history" routerLinkActive="active">
                <i class="pi pi-clock"></i>
                <span class="nav-text">Push history</span>
              </a>
            }
          </div>

          <div class="nav-spacer"></div>

          <div class="nav-footer">
            <a class="nav-item" routerLink="/help" routerLinkActive="active">
              <i class="pi pi-question-circle"></i>
              <span class="nav-text">Help</span>
            </a>
            <a class="nav-item" routerLink="/settings" routerLinkActive="active">
              <i class="pi pi-cog"></i>
              <span class="nav-text">Settings</span>
            </a>
            <div class="nav-item" (click)="toggleTheme()">
              <i class="pi" [class.pi-moon]="!dark()" [class.pi-sun]="dark()"></i>
              <span class="nav-text">{{ dark() ? 'Light' : 'Dark' }}</span>
            </div>
            <div class="nav-item nav-user">
              <i class="pi pi-user"></i>
              <span class="nav-text">{{ user.username }}</span>
            </div>
            <div class="nav-item" (click)="signOut()">
              <i class="pi pi-sign-out"></i>
              <span class="nav-text">Sign out</span>
            </div>
          </div>
        </nav>

        <main class="content">
          <router-outlet />
        </main>
      </div>
    } @else {
      <router-outlet />
    }
  `,
  styles: `
    .shell { display: flex; height: 100vh; overflow: hidden; }

    /* ── side nav: collapsed by default, expands on hover ── */
    .sidenav { width: 3.25rem; display: flex; flex-direction: column; flex-shrink: 0;
               background: var(--surface); border-right: 1px solid var(--border);
               box-shadow: 2px 0 8px rgba(0,0,0,.04);
               transition: width .2s ease; overflow: hidden; z-index: 10; }
    .sidenav:hover { width: 13rem; }

    .nav-text { opacity: 0; white-space: nowrap; transition: opacity .15s ease;
                overflow: hidden; }
    .sidenav:hover .nav-text { opacity: 1; }

    .nav-brand { display: flex; align-items: center; gap: .6rem; padding: .85rem .75rem;
                 font-weight: 700; font-size: .9rem; cursor: pointer;
                 border-bottom: 1px solid var(--border); white-space: nowrap; }
    .nav-brand .pi { font-size: 1rem; flex-shrink: 0; width: 1.5rem; text-align: center; }

    .nav-links { display: flex; flex-direction: column; gap: .15rem; padding: .5rem .4rem; }

    .nav-item { display: flex; align-items: center; gap: .6rem; padding: .5rem .6rem;
                font-size: .8rem; color: var(--text-secondary); cursor: pointer;
                border-radius: var(--radius-sm); transition: all .15s;
                white-space: nowrap; text-decoration: none; }
    .nav-item:hover { color: var(--text); background: var(--surface-hover); }
    .nav-item.active { color: var(--primary); background: var(--primary-soft);
                       font-weight: 600; }
    .nav-item .pi { font-size: .85rem; flex-shrink: 0; width: 1.5rem; text-align: center; }

    .nav-spacer { flex: 1; }

    .nav-footer { display: flex; flex-direction: column; gap: .15rem;
                  padding: .5rem .4rem; border-top: 1px solid var(--border); }
    .nav-user { font-weight: 500; }

    /* ── content area ── */
    .content { flex: 1; overflow-y: auto; min-width: 0; }

    /* ── tablet landscape: narrower sidenav ── */
    @media (max-width: 1024px) and (orientation: landscape) {
      .sidenav { width: 2.75rem; }
      .sidenav:hover { width: 11rem; }
      .nav-brand { padding: .65rem .55rem; font-size: .82rem; }
      .nav-item { padding: .4rem .5rem; font-size: .75rem; }
    }
  `,
})
export class App {
  protected auth = inject(Auth);
  settings = inject(Settings);
  private router = inject(Router);
  dark = signal(localStorage.getItem('theme') === 'dark');

  constructor() {
    this.applyTheme();
  }

  toggleTheme() {
    this.dark.update((v) => !v);
    localStorage.setItem('theme', this.dark() ? 'dark' : 'light');
    this.applyTheme();
  }

  private applyTheme() {
    document.documentElement.classList.toggle('dark', this.dark());
  }

  signOut() {
    this.auth.logout().subscribe({ next: () => this.router.navigate(['/login']) });
  }
}
