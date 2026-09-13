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
            <span class="brand-icon">EP</span>
            <span class="brand-text">Excel Parser</span>
          </div>

          <div class="nav-links">
            <a class="nav-item" routerLink="/work" routerLinkActive="active"
               [routerLinkActiveOptions]="{ exact: true }">
              <i class="pi pi-briefcase"></i>
              <span>Configurations</span>
            </a>
            <a class="nav-item" routerLink="/batch" routerLinkActive="active">
              <i class="pi pi-upload"></i>
              <span>Batch run</span>
            </a>
            @if (settings.dataViewer()) {
              <a class="nav-item" routerLink="/data-viewer" routerLinkActive="active">
                <i class="pi pi-database"></i>
                <span>Data Viewer</span>
              </a>
            }
            @if (settings.auditLog()) {
              <a class="nav-item" routerLink="/history" routerLinkActive="active">
                <i class="pi pi-clock"></i>
                <span>Push history</span>
              </a>
            }
          </div>

          <div class="nav-spacer"></div>

          <div class="nav-footer">
            <a class="nav-item" routerLink="/help" routerLinkActive="active">
              <i class="pi pi-question-circle"></i>
              <span>Help</span>
            </a>
            <a class="nav-item" routerLink="/settings" routerLinkActive="active">
              <i class="pi pi-cog"></i>
              <span>Settings</span>
            </a>
            <div class="nav-item" (click)="toggleTheme()">
              <i class="pi" [class.pi-moon]="!dark()" [class.pi-sun]="dark()"></i>
              <span>{{ dark() ? 'Light' : 'Dark' }}</span>
            </div>
            <div class="nav-user" (click)="signOut()" pTooltip="Sign out" tooltipPosition="right">
              <span class="user-avatar">{{ user.username.charAt(0).toUpperCase() }}</span>
              <span class="user-name">{{ user.username }}</span>
              <i class="pi pi-chevron-right user-chevron"></i>
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

    /* ── side nav: always expanded ── */
    .sidenav { width: 12.5rem; display: flex; flex-direction: column; flex-shrink: 0;
               background: var(--sidebar-bg); border-right: 1px solid var(--sidebar-border);
               overflow: hidden; z-index: 10; }

    .nav-brand { display: flex; align-items: center; gap: .55rem; padding: .85rem .75rem;
                 font-weight: 700; font-size: .9rem; cursor: pointer; white-space: nowrap; }
    .brand-icon { display: flex; align-items: center; justify-content: center;
                  width: 1.75rem; height: 1.75rem; background: var(--primary);
                  border-radius: 6px; color: #fff; font-size: .65rem; font-weight: 800;
                  flex-shrink: 0; letter-spacing: .02em; }
    .brand-text { font-size: .88rem; }

    .nav-links { display: flex; flex-direction: column; gap: .15rem; padding: .5rem .5rem; }

    .nav-item { display: flex; align-items: center; gap: .55rem; padding: .5rem .6rem;
                font-size: .8rem; color: var(--text-secondary); cursor: pointer;
                border-radius: var(--radius-sm); transition: all .15s;
                white-space: nowrap; text-decoration: none; }
    .nav-item:hover { color: var(--text); background: var(--surface-hover);
                      text-decoration: none; }
    .nav-item.active { color: #fff; background: var(--primary); font-weight: 600; }
    .nav-item .pi { font-size: .82rem; flex-shrink: 0; width: 1.25rem; text-align: center; }

    .nav-spacer { flex: 1; }

    .nav-footer { display: flex; flex-direction: column; gap: .15rem;
                  padding: .5rem .5rem; border-top: 1px solid var(--border); }

    .nav-user { display: flex; align-items: center; gap: .5rem; padding: .55rem .6rem;
                cursor: pointer; border-radius: var(--radius-sm); transition: all .15s;
                margin-top: .15rem; }
    .nav-user:hover { background: var(--surface-hover); }
    .user-avatar { display: flex; align-items: center; justify-content: center;
                   width: 1.6rem; height: 1.6rem; background: var(--primary);
                   border-radius: 50%; color: #fff; font-size: .65rem; font-weight: 700;
                   flex-shrink: 0; }
    .user-name { font-size: .8rem; font-weight: 500; color: var(--text); flex: 1; }
    .user-chevron { font-size: .6rem; color: var(--text-secondary); }

    /* ── content area ── */
    .content { flex: 1; overflow-y: auto; min-width: 0; }

    /* ── tablet: collapse sidenav to icons ── */
    @media (max-width: 1024px) {
      .sidenav { width: 3rem; }
      .sidenav span:not(.brand-icon):not(.user-avatar) { display: none; }
      .nav-brand { padding: .65rem .55rem; justify-content: center; }
      .nav-links { padding: .5rem .3rem; }
      .nav-item { padding: .5rem; justify-content: center; }
      .nav-item .pi { width: auto; }
      .nav-footer { padding: .5rem .3rem; }
      .nav-user { justify-content: center; padding: .5rem; }
      .user-chevron { display: none; }
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
