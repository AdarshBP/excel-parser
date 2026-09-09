import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ButtonModule } from '@openng/optimus-ui/button';
import { InputTextModule } from '@openng/optimus-ui/inputtext';
import { MessageModule } from '@openng/optimus-ui/message';
import { Auth } from '../core/auth';

@Component({
  selector: 'app-login',
  imports: [FormsModule, ButtonModule, InputTextModule, MessageModule],
  template: `
    <div class="landing">
      <!-- Left: Hero -->
      <div class="hero">
        <div class="hero-content">
          <div class="logo">
            <div class="logo-icon">
              <i class="pi pi-th-large"></i>
            </div>
            <span class="logo-text">Excel Parser</span>
          </div>

          <h1>Turn spreadsheets into<br /><span class="accent">structured data.</span></h1>
          <p class="tagline">Upload Excel or CSV files, map columns to a schema,
            validate, preview, and push clean data into PostgreSQL. No code required.</p>

          <!-- Features -->
          <div class="features">
            <div class="feat">
              <div class="feat-icon"><i class="pi pi-file-excel"></i></div>
              <div>
                <div class="feat-title">Excel & CSV</div>
                <div class="feat-desc">Parse .xlsx, .xlsm, and .csv files natively. No conversion, no data loss.</div>
              </div>
            </div>
            <div class="feat">
              <div class="feat-icon"><i class="pi pi-cog"></i></div>
              <div>
                <div class="feat-title">Config-driven</div>
                <div class="feat-desc">Define schema, types, and transformations in a config workbook. Auto-generate from CSV headers.</div>
              </div>
            </div>
            <div class="feat">
              <div class="feat-icon"><i class="pi pi-database"></i></div>
              <div>
                <div class="feat-title">Push to PostgreSQL</div>
                <div class="feat-desc">Schema + data pushed in one step. Full lineage: every row traced to its source file and row.</div>
              </div>
            </div>
            <div class="feat">
              <div class="feat-icon"><i class="pi pi-sitemap"></i></div>
              <div>
                <div class="feat-title">ER Diagram</div>
                <div class="feat-desc">Interactive schema visualization with relationships, zoom, and drag-and-drop layout.</div>
              </div>
            </div>
            <div class="feat">
              <div class="feat-icon"><i class="pi pi-bolt"></i></div>
              <div>
                <div class="feat-title">Cell Scripts</div>
                <div class="feat-desc">Predefined transformations: trim, uppercase, round, abs. Chained and validated before push.</div>
              </div>
            </div>
            <div class="feat">
              <div class="feat-icon"><i class="pi pi-upload"></i></div>
              <div>
                <div class="feat-title">Batch Processing</div>
                <div class="feat-desc">Load multiple monthly files at once. Validate all, push all. Each gets its own file_id.</div>
              </div>
            </div>
          </div>

          <div class="footer-note">
            Supports Google Drive & Google Sheets integration.
          </div>
        </div>
      </div>

      <!-- Right: Login -->
      <div class="login-side">
        <div class="login-card">
          <h2>Sign in</h2>
          <p class="login-sub">Enter your credentials to access your workspace.</p>

          <form (ngSubmit)="submit()">
            <label for="u">Username</label>
            <input pInputText id="u" name="username" autocomplete="username"
                   [(ngModel)]="username" required placeholder="admin" />

            <label for="p">Password</label>
            <input pInputText id="p" name="password" type="password"
                   autocomplete="current-password" [(ngModel)]="password"
                   required placeholder="Enter password" />

            @if (error()) {
              <p-message severity="error" [text]="error()!" />
            }

            <p-button type="submit" label="Sign in" [loading]="busy()" [fluid]="true" />
          </form>

          <p class="hint">Accounts are created by an administrator.<br />
            <code>python users.py add &lt;name&gt;</code></p>
        </div>
      </div>
    </div>
  `,
  styles: `
    .landing { display: flex; height: 100vh; overflow: hidden; }

    /* ── Hero (left) ── */
    .hero { flex: 1.2; display: flex; align-items: center; justify-content: center;
            background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 50%, #3b82f6 100%);
            color: white; padding: 2.5rem; overflow-y: auto; }

    .hero-content { max-width: 34rem; }

    .logo { display: flex; align-items: center; gap: .6rem; margin-bottom: 1.5rem; }
    .logo-icon { width: 2.5rem; height: 2.5rem; border-radius: .6rem;
                 background: rgba(255,255,255,.15); display: flex; align-items: center;
                 justify-content: center; backdrop-filter: blur(8px); }
    .logo-icon .pi { font-size: 1.1rem; }
    .logo-text { font-size: 1rem; font-weight: 700; letter-spacing: .02em; }

    h1 { font-size: 2rem; font-weight: 800; line-height: 1.2; margin: 0 0 1rem; }
    .accent { color: #93c5fd; }

    .tagline { font-size: .9rem; line-height: 1.6; opacity: .85; margin: 0 0 2rem; }

    /* Features grid */
    .features { display: grid; grid-template-columns: 1fr 1fr; gap: .75rem 1.25rem; }
    .feat { display: flex; gap: .6rem; align-items: start; }
    .feat-icon { width: 2rem; height: 2rem; border-radius: .4rem;
                 background: rgba(255,255,255,.12); display: flex; align-items: center;
                 justify-content: center; flex-shrink: 0; }
    .feat-icon .pi { font-size: .8rem; opacity: .9; }
    .feat-title { font-weight: 600; font-size: .78rem; margin-bottom: .1rem; }
    .feat-desc { font-size: .68rem; line-height: 1.4; opacity: .7; }

    .footer-note { margin-top: 2rem; font-size: .72rem; opacity: .5; }

    /* ── Login (right) ── */
    .login-side { flex: 0 0 26rem; display: flex; align-items: center; justify-content: center;
                  background: var(--bg); padding: 2rem; }

    .login-card { width: 100%; max-width: 20rem; }
    .login-card h2 { margin: 0 0 .25rem; font-size: 1.3rem; font-weight: 700;
                     color: var(--text); }
    .login-sub { font-size: .82rem; color: var(--text-secondary); margin: 0 0 1.5rem; }

    form { display: grid; gap: .65rem; }
    label { font-size: .72rem; font-weight: 600; color: var(--text-secondary);
            text-transform: uppercase; letter-spacing: 0.05em; }
    input { width: 100%; }
    p-button { margin-top: .5rem; }

    .hint { font-size: .68rem; color: var(--text-secondary); text-align: center;
            margin-top: 1.5rem; line-height: 1.5; }
    .hint code { font-size: .64rem; background: var(--surface-hover); padding: .15rem .35rem;
                 border-radius: 3px; }

    /* ── Responsive: tablet landscape ── */
    @media (max-width: 1024px) {
      .hero { padding: 1.5rem; }
      .hero-content { max-width: 28rem; }
      h1 { font-size: 1.5rem; }
      .features { grid-template-columns: 1fr; }
      .login-side { flex: 0 0 22rem; }
    }
  `,
})
export class Login {
  private auth = inject(Auth);
  private router = inject(Router);
  username = '';
  password = '';
  busy = signal(false);
  error = signal<string | null>(null);

  submit() {
    if (!this.username || !this.password) {
      this.error.set('enter a username and password');
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.auth.login(this.username, this.password).subscribe({
      next: () => this.router.navigate(['/work']),
      error: (e) => {
        this.busy.set(false);
        this.error.set(e.message);
      },
    });
  }
}
