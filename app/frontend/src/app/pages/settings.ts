import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from '@openng/optimus-ui/button';
import { InputTextModule } from '@openng/optimus-ui/inputtext';
import { MessageModule } from '@openng/optimus-ui/message';
import { SelectModule } from '@openng/optimus-ui/select';
import { TagModule } from '@openng/optimus-ui/tag';
import { ToggleSwitchModule } from '@openng/optimus-ui/toggleswitch';
import { Api } from '../core/api';
import { Settings } from '../core/settings';
import { DriveStatus } from '../core/models';

@Component({
  selector: 'app-settings',
  imports: [
    FormsModule, ButtonModule, InputTextModule, MessageModule,
    SelectModule, TagModule, ToggleSwitchModule,
  ],
  template: `
    <div class="page">
      <div class="page-header">
        <div class="page-header-left">
          <h1 class="page-title">Settings</h1>
          <p class="page-subtitle">Configure application preferences and integrations.</p>
        </div>
      </div>

      <!-- General -->
      <div class="section-card">
        <div class="section-title">General</div>
        <div class="section-desc">Basic application settings.</div>
        <div class="setting-row">
          <div class="setting-info">
            <div class="setting-label">Poll interval</div>
            <div class="setting-desc">How often the app checks if workbooks have changed.
              Lower values detect changes faster but use more API quota (especially for Drive files).</div>
          </div>
          <div class="setting-control">
            <p-select appendTo="body" [options]="pollOptions" optionLabel="label" optionValue="value"
                      [(ngModel)]="pollInterval" (ngModelChange)="savePoll()" />
          </div>
        </div>
        <div class="setting-row setting-row-border">
          <div class="setting-info">
            <div class="setting-label">Keyboard shortcuts</div>
            <div class="setting-desc">Enable keyboard shortcuts on the project page
              ({{ isMac ? '\u2318' : 'Ctrl' }}+S save, {{ isMac ? '\u2318' : 'Ctrl' }}+R render, etc.).</div>
          </div>
          <div class="setting-control">
            <p-toggleswitch [(ngModel)]="keyboardShortcuts" (ngModelChange)="saveKeyboard()" />
          </div>
        </div>
      </div>

      <!-- Feature flags -->
      <div class="section-card">
        <div class="section-title">Features</div>
        <div class="section-desc">Enable or disable application features.</div>
        <div class="setting-row">
          <div class="setting-info">
            <div class="setting-label">Push history page</div>
            <div class="setting-desc">Shows the "Push history" page in the sidebar.
              A timeline of every push operation:
              who pushed what, when, from which file, and to which database.</div>
          </div>
          <div class="setting-control">
            <p-toggleswitch [(ngModel)]="flags.auditLog" (ngModelChange)="saveFlags()" />
          </div>
        </div>

        <div class="setting-row setting-row-border">
          <div class="setting-info">
            <div class="setting-label">Export CSV</div>
            <div class="setting-desc">Shows a download button on preview tables
              in the project page. Exports the currently selected table as a CSV
              file for sharing or analysis outside the app.</div>
          </div>
          <div class="setting-control">
            <p-toggleswitch [(ngModel)]="flags.exportCsv" (ngModelChange)="saveFlags()" />
          </div>
        </div>
        <div class="setting-row setting-row-border">
          <div class="setting-info">
            <div class="setting-label">Database load tracking</div>
            <div class="setting-desc">When enabled, a <code>load_config_audit</code> table
              is created in the target database to record every load: which file,
              which config, which tables, and when. Also enables duplicate file
              detection.</div>
          </div>
          <div class="setting-control">
            <p-toggleswitch [(ngModel)]="flags.loadTracking" (ngModelChange)="saveFlags()" />
          </div>
        </div>
      </div>

      <!-- Google Drive -->
      <div class="section-card">
        <div class="section-title">Google Drive</div>
        <div class="section-desc">Connect your Google account to browse and select files from Drive.</div>

        @if (!driveStatus()) {
          <p class="muted">Loading...</p>
        } @else if (!driveStatus()!.configured) {
          <div class="setting-row">
            <div class="setting-info">
              <div class="setting-label">Not configured</div>
              <div class="setting-desc">
                Google Drive integration requires <code>GOOGLE_CLIENT_ID</code>,
                <code>GOOGLE_CLIENT_SECRET</code>, and <code>GOOGLE_API_KEY</code>
                in the server's <code>.env</code> file. File path and direct link
                sources work without it.
              </div>
            </div>
            <p-tag value="not configured" severity="warn" />
          </div>
        } @else if (!driveStatus()!.connected) {
          <div class="drive-connect-row">
            <div class="drive-status">
              <img src="https://www.gstatic.com/images/branding/product/1x/drive_2020q4_48dp.png"
                   alt="Google Drive" class="drive-icon" />
              <div class="drive-info">
                <div class="setting-label">Not connected</div>
                <div class="setting-desc">Only read-only access is requested.</div>
              </div>
            </div>
            <p-button label="Connect Google Drive" icon="pi pi-google" size="small"
                      [loading]="connecting()" (onClick)="connect()" />
          </div>
        } @else {
          <div class="setting-row">
            <div class="setting-info">
              <div class="setting-label">Connected</div>
              <div class="setting-desc">
                Signed in as <strong>{{ driveStatus()!.email }}</strong>.
                @if (driveStatus()!.connected_at) {
                  Connected {{ driveStatus()!.connected_at }}.
                }
                The app has read-only access to your Google Drive.
              </div>
            </div>
            <div class="setting-control">
              <p-tag [value]="driveStatus()!.email ?? 'connected'" severity="success" />
              <p-button label="Disconnect" size="small" severity="danger" [outlined]="true"
                        (onClick)="disconnect()" />
            </div>
          </div>
        }

        @if (driveError()) {
          <p-message severity="error" [text]="driveError()!" />
        }
        @if (driveMsg()) {
          <p-message [severity]="driveMsg()!.includes('Disconnected') ? 'info' : 'success'"
                     [text]="driveMsg()!" />
        }
      </div>

      <!-- About -->
      <div class="section-card">
        <div class="section-title">About</div>
        <div class="section-desc">Application information.</div>
        <div class="about">
          <div class="about-row">
            <span class="about-label">Application</span>
            <span class="about-value">Excel Parser</span>
          </div>
          <div class="about-row">
            <span class="about-label">Version</span>
            <span class="about-value">1.0.0</span>
          </div>
          <div class="about-row">
            <span class="about-label">Backend</span>
            <span class="about-value">{{ backendVersion() }}</span>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: `
    .page { display: grid; gap: 1rem; padding: 1.5rem 2rem; max-width: 48rem; }

    .setting-row { display: flex; gap: 1rem; align-items: start;
                   justify-content: space-between; padding: .65rem 0; }
    .setting-row-border { border-top: 1px solid var(--border); }
    .setting-info { flex: 1; min-width: 0; }
    .setting-label { font-weight: 600; font-size: .85rem; }
    .setting-desc { font-size: .75rem; color: var(--text-secondary); margin-top: .2rem;
                    line-height: 1.5; }
    .setting-control { display: flex; gap: .4rem; align-items: center; flex-shrink: 0; }

    .drive-connect-row { display: flex; align-items: center; justify-content: space-between;
                         gap: 1rem; }
    .drive-status { display: flex; align-items: center; gap: .75rem; }
    .drive-icon { width: 2rem; height: 2rem; flex-shrink: 0; }
    .drive-info { min-width: 0; }

    .about { display: grid; gap: 0; }
    .about-row { display: flex; justify-content: space-between; align-items: center;
                 padding: .35rem 0; font-size: .82rem; }
    .about-label { color: var(--text-secondary); }
    .about-value { font-weight: 500; }

    .muted { color: var(--text-secondary); font-size: .8rem; }
  `,
})
export class SettingsPage {
  private api = inject(Api);
  private http = inject(HttpClient);
  private settings = inject(Settings);

  isMac = navigator.platform.toUpperCase().includes('MAC');
  pollInterval = this.settings.pollInterval();
  keyboardShortcuts = this.settings.keyboardShortcuts();
  flags = {
    auditLog: this.settings.auditLog(),
    exportCsv: this.settings.exportCsv(),
    loadTracking: this.settings.loadTracking(),
  };
  pollOptions = [
    { label: '5 seconds', value: 5 },
    { label: '10 seconds', value: 10 },
    { label: '15 seconds', value: 15 },
    { label: '30 seconds', value: 30 },
    { label: '60 seconds', value: 60 },
  ];

  driveStatus = signal<DriveStatus | null>(null);
  driveError = signal<string | null>(null);
  driveMsg = signal<string | null>(null);
  connecting = signal(false);
  backendVersion = signal('—');

  constructor() {
    this.api.driveStatus().subscribe({
      next: (s) => this.driveStatus.set(s),
      error: (e) => this.driveError.set(e.message),
    });
    this.http.get<{ version: string }>('/api/health').subscribe({
      next: (r) => this.backendVersion.set(r.version),
    });
  }

  savePoll() {
    this.settings.update({ pollInterval: this.pollInterval });
  }

  saveKeyboard() {
    this.settings.update({ keyboardShortcuts: this.keyboardShortcuts });
  }

  saveFlags() {
    this.settings.update(this.flags);
  }

  connect() {
    this.connecting.set(true);
    this.driveError.set(null);
    this.api.driveConnect().subscribe({
      next: ({ url }) => {
        this.connecting.set(false);
        window.open(url, '_blank', 'noopener');
      },
      error: (e) => { this.connecting.set(false); this.driveError.set(e.message); },
    });
    // Listen for callback from the consent tab
    const handler = (e: StorageEvent) => {
      if (e.key === 'drive-connected') {
        window.removeEventListener('storage', handler);
        this.api.driveStatus().subscribe({
          next: (s) => { this.driveStatus.set(s); this.driveMsg.set('Connected successfully'); },
        });
      }
    };
    window.addEventListener('storage', handler);
  }

  disconnect() {
    this.driveError.set(null);
    this.driveMsg.set(null);
    this.api.driveDisconnect().subscribe({
      next: () => {
        this.driveMsg.set('Disconnected from Google Drive');
        this.api.driveStatus().subscribe({
          next: (s) => this.driveStatus.set(s),
        });
      },
      error: (e) => this.driveError.set(e.message),
    });
  }
}
