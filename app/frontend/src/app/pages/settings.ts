import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from '@openng/optimus-ui/button';
import { CardModule } from '@openng/optimus-ui/card';
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
    FormsModule, ButtonModule, CardModule, InputTextModule, MessageModule,
    SelectModule, TagModule, ToggleSwitchModule,
  ],
  template: `
    <div class="page">
      <h2>Settings</h2>

      <!-- General -->
      <p-card>
        <ng-template #title>General</ng-template>
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
        <div class="setting-row">
          <div class="setting-info">
            <div class="setting-label">Keyboard shortcuts</div>
            <div class="setting-desc">Enable keyboard shortcuts on the project page
              ({{ isMac ? '⌘' : 'Ctrl' }}+S save, {{ isMac ? '⌘' : 'Ctrl' }}+R render, etc.).
              Off by default.</div>
          </div>
          <div class="setting-control">
            <p-toggleswitch [(ngModel)]="keyboardShortcuts" (ngModelChange)="saveKeyboard()" />
          </div>
        </div>
      </p-card>

      <!-- Feature flags -->
      <p-card>
        <ng-template #title>Features</ng-template>
        <div class="setting-row">
          <div class="setting-info">
            <div class="setting-label">Push history page</div>
            <div class="setting-desc">Shows the "Push history" page in the sidebar.
              A timeline of every push operation: who pushed what, when, from which
              file, and to which database. Data is always recorded; this only
              controls whether the page is visible.</div>
          </div>
          <div class="setting-control">
            <p-toggleswitch [(ngModel)]="flags.auditLog" (ngModelChange)="saveFlags()" />
          </div>
        </div>

        <div class="setting-row">
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
        <div class="setting-row">
          <div class="setting-info">
            <div class="setting-label">Database load tracking</div>
            <div class="setting-desc">When enabled, a <code>load_config_audit</code> table
              is created in the target database to record every load: which file,
              which config, which tables, and when. Also enables duplicate file
              detection. Turn off for a leaner database. Data tables always keep
              file_name, file_sha256, and source_ref on every row regardless.</div>
          </div>
          <div class="setting-control">
            <p-toggleswitch [(ngModel)]="flags.loadTracking" (ngModelChange)="saveFlags()" />
          </div>
        </div>
      </p-card>

      <!-- Google Drive -->
      <p-card>
        <ng-template #title>Google Drive</ng-template>

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
          <div class="setting-row">
            <div class="setting-info">
              <div class="setting-label">Not connected</div>
              <div class="setting-desc">
                Connect your Google account to browse and select files from Drive.
                Only read-only access is requested.
              </div>
            </div>
            <div class="setting-control">
              <p-button label="Connect Google Drive" icon="pi pi-google" size="small"
                        [loading]="connecting()" (onClick)="connect()" />
            </div>
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
      </p-card>

      <!-- About -->
      <p-card>
        <ng-template #title>About</ng-template>
        <div class="about">
          <div class="setting-row">
            <span class="muted">Application</span>
            <span>Excel Parser</span>
          </div>
          <div class="setting-row">
            <span class="muted">Version</span>
            <span>1.0.0</span>
          </div>
          <div class="setting-row">
            <span class="muted">Backend</span>
            <span>{{ backendVersion() }}</span>
          </div>
        </div>
      </p-card>
    </div>
  `,
  styles: `
    .page { display: grid; gap: 1rem; padding: 1.25rem; max-width: 44rem; margin: 0 auto; }
    h2 { margin: 0; font-size: 1.1rem; }

    .setting-row { display: flex; gap: 1rem; align-items: start;
                   justify-content: space-between; }
    .setting-info { flex: 1; min-width: 0; }
    .setting-label { font-weight: 600; font-size: .85rem; }
    .setting-desc { font-size: .75rem; color: var(--text-secondary); margin-top: .2rem;
                    line-height: 1.5; }
    .setting-control { display: flex; gap: .4rem; align-items: center; flex-shrink: 0; }

    .about .setting-row { padding: .3rem 0; font-size: .8rem; }
    .about code { font-size: .72rem; }
    .muted { color: var(--text-secondary); }
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
