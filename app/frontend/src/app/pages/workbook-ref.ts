import { Component, OnDestroy, effect, inject, input, model, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from '@openng/optimus-ui/button';
import { DialogModule } from '@openng/optimus-ui/dialog';
import { InputTextModule } from '@openng/optimus-ui/inputtext';
import { MessageModule } from '@openng/optimus-ui/message';
import { SelectModule } from '@openng/optimus-ui/select';
import { TableModule } from '@openng/optimus-ui/table';
import { TagModule } from '@openng/optimus-ui/tag';
import { TooltipModule } from '@openng/optimus-ui/tooltip';
import { Api } from '../core/api';
import { GooglePicker } from '../core/picker';
import { DriveFile, DriveStatus, SourceKind, WorkbookDirItem } from '../core/models';

@Component({
  selector: 'app-workbook-ref',
  imports: [
    FormsModule, ButtonModule, DialogModule, InputTextModule, MessageModule,
    SelectModule, TableModule, TagModule, TooltipModule,
  ],
  template: `
    <!-- ─── Card view (when a file is set) ─── -->
    @if (value() && !editing) {
      <div class="card" [class.card-ok]="testResult()" [class.card-err]="testError()">
        <div class="card-icon">
          <i class="pi" [class.pi-file]="kindOf(value()) === 'local'"
             [class.pi-link]="kindOf(value()) === 'sheet'"
             [class.pi-google]="kindOf(value()) === 'drive'"></i>
        </div>
        <div class="card-body">
          <div class="card-name">{{ fileName() }}</div>
          <div class="card-path" [title]="value()">{{ value() }}</div>
          @if (testResult(); as r) {
            <div class="card-meta">
              {{ r.sheets.length }} sheet(s) · {{ (r.size / 1024).toFixed(0) }} KB
              · {{ r.sheets.join(', ') }}
            </div>
          }
          @if (testError()) {
            <div class="card-meta card-meta-err">{{ testError() }}</div>
          }
        </div>
        <div class="card-status">
          @if (testing()) {
            <i class="pi pi-spin pi-spinner"></i>
          } @else if (testResult()) {
            <i class="pi pi-check-circle status-ok"></i>
          } @else if (testError()) {
            <i class="pi pi-times-circle status-err"></i>
          }
        </div>
        <div class="card-actions">
          <p-button icon="pi pi-refresh" size="small" [text]="true"
                    pTooltip="Re-test" (onClick)="testAccess()" />
          @if (kindOf(value()) === 'drive') {
            <p-button icon="pi pi-sign-out" size="small" [text]="true" severity="danger"
                      pTooltip="Disconnect Google Drive" (onClick)="disconnect()" />
          }
          <p-button icon="pi pi-pencil" size="small" [text]="true"
                    pTooltip="Change" (onClick)="openEdit()" />
        </div>
      </div>
    } @else {
      <!-- ─── Edit view (no file yet, or user clicked Change) ─── -->
      <div class="edit-card">
        <div class="edit-header">
          <div class="mode-tabs">
            <button class="tab" [class.active]="mode() === 'local'"
                    (click)="setMode('local')">
              <i class="pi pi-file"></i> File
            </button>
            <button class="tab" [class.active]="mode() === 'sheet'"
                    (click)="setMode('sheet')">
              <i class="pi pi-link"></i> Link
            </button>
            <button class="tab" [class.active]="mode() === 'drive'"
                    (click)="setMode('drive')">
              <i class="pi pi-google"></i> Drive
            </button>
          </div>
          @if (value()) {
            <p-button label="Done" size="small" (onClick)="doneEditing()" />
          }
        </div>

        <div class="edit-body">
          @if (mode() === 'local') {
            <div class="input-row">
              <input pInputText [ngModel]="value()" (ngModelChange)="type($event)"
                     [placeholder]="placeholder()" />
              <p-button icon="pi pi-folder-open" size="small" [outlined]="true"
                        pTooltip="Browse" (onClick)="openBrowser()" />
            </div>
            <p-select appendTo="body" [options]="files()" [ngModel]="value()"
                      (ngModelChange)="type($event ?? '')" [filter]="true" [showClear]="true"
                      placeholder="…or pick from project" />
          }

          @if (mode() === 'sheet') {
            <input pInputText [ngModel]="value()" (ngModelChange)="type($event)"
                   placeholder="https://docs.google.com/spreadsheets/d/…" />
            <small class="hint">Share as "Anyone with the link: Viewer"</small>
          }

          @if (mode() === 'drive') {
            @if (!drive()?.configured) {
              <p-message severity="warn"
                text="Google Drive not configured: set GOOGLE_CLIENT_ID and GOOGLE_API_KEY in .env" />
            } @else if (!drive()?.connected) {
              <div class="drive-connect">
                <p-button label="Connect Google Drive" icon="pi pi-google" size="small"
                          [loading]="connecting()" (onClick)="connect()" />
                <small class="hint">Read-only access</small>
              </div>
            } @else {
              <div class="drive-bar">
                <p-tag [value]="drive()!.email ?? 'connected'" severity="success" />
                <p-button label="Pick from Drive" icon="pi pi-external-link" size="small"
                          [loading]="pickingDrive()" (onClick)="openDrivePicker()" />
                <p-button label="Disconnect" size="small" [text]="true" severity="danger"
                          (onClick)="disconnect()" />
              </div>
              @if (value().startsWith('drive:')) {
                <small class="hint">{{ chosenName() || value() }}</small>
              }
            }
            @if (driveError()) { <p-message severity="error" [text]="driveError()!" /> }
          }
        </div>
      </div>
    }

    <!-- ─── Browse dialog ─── -->
    <p-dialog header="Browse workbook directory" [(visible)]="browser" [modal]="true"
              [style]="{ width: '44rem', maxWidth: '94vw' }">
      <div class="picker">
        @if (!wdirRoot()) {
          <p-message severity="warn"
            text="No workbook directory configured: set WORKBOOK_DIR in .env and restart." />
        } @else {
          <div class="picker-bar">
            <small class="muted">{{ wdirRoot() }}</small>
            @if (wdirFolder()) {
              <small class="muted">/ {{ wdirFolder() }}</small>
              <p-button label="Back" icon="pi pi-arrow-left" size="small" [text]="true"
                        (onClick)="wdirUp()" />
            }
          </div>
          <p-table [value]="wdirItems()" [loading]="wdirLoading()" size="small" dataKey="path">
            <ng-template #header>
              <tr><th>Name</th><th>Type</th><th>Size</th><th></th></tr>
            </ng-template>
            <ng-template #body let-f>
              <tr>
                <td>{{ f.name }}</td>
                <td><p-tag [value]="f.kind" severity="secondary" /></td>
                <td>{{ f.kind === 'file' && f.size ? (f.size / 1024).toFixed(0) + ' KB' : '—' }}</td>
                <td>
                  @if (f.kind === 'folder') {
                    <p-button label="Open" size="small" [text]="true" (onClick)="wdirInto(f)" />
                  } @else {
                    <p-button label="Select" size="small" (onClick)="wdirChoose(f)" />
                  }
                </td>
              </tr>
            </ng-template>
            <ng-template #emptymessage>
              <tr><td colspan="4">No .xlsx files here.</td></tr>
            </ng-template>
          </p-table>
        }
        @if (wdirError()) { <p-message severity="error" [text]="wdirError()!" /> }
      </div>
    </p-dialog>


  `,
  styles: `
    :host { display: block; min-width: 0; }

    /* ─── Card (file is set) ─── */
    .card { display: flex; gap: .65rem; align-items: center; padding: .6rem .75rem;
            border: 1px solid var(--border); border-radius: var(--radius-sm);
            background: var(--surface); transition: border-color .15s; }
    .card:hover { border-color: var(--border-strong); }
    .card-ok { border-color: color-mix(in srgb, var(--success) 30%, var(--border)); }
    .card-err { border-color: color-mix(in srgb, var(--danger) 30%, var(--border)); }
    .card-icon { font-size: 1.2rem; color: var(--text-secondary); flex-shrink: 0; }
    .card-body { flex: 1; min-width: 0; }
    .card-name { font-weight: 600; font-size: .85rem; overflow: hidden;
                 text-overflow: ellipsis; white-space: nowrap; }
    .card-path { font-size: .7rem; color: var(--text-secondary); overflow: hidden;
                 text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
    .card-meta { font-size: .7rem; color: var(--text-secondary); margin-top: .15rem; }
    .card-meta-err { color: var(--danger); }
    .card-status { flex-shrink: 0; font-size: 1rem; }
    .status-ok { color: var(--success); }
    .status-err { color: var(--danger); }
    .card-actions { display: flex; gap: 0; flex-shrink: 0; }

    /* ─── Edit (choosing a file) ─── */
    .edit-card { border: 1px solid var(--border); border-radius: var(--radius-sm);
                 background: var(--surface); overflow: hidden; }
    .edit-header { display: flex; justify-content: space-between; align-items: center;
                   padding: .35rem .5rem; background: var(--surface-raised);
                   border-bottom: 1px solid var(--border); }
    .mode-tabs { display: flex; gap: 0; }
    .tab { display: flex; align-items: center; gap: .3rem; padding: .3rem .6rem;
           font-size: .75rem; background: transparent; border: none; color: var(--text-secondary);
           cursor: pointer; border-radius: var(--radius-sm); transition: all .15s; }
    .tab:hover { color: var(--text); background: var(--surface-hover); }
    .tab.active { color: var(--primary); font-weight: 600; background: var(--primary-soft); }
    .tab .pi { font-size: .7rem; }
    .edit-body { padding: .6rem .65rem; display: grid; gap: .4rem; }
    .edit-body input, .edit-body p-select { width: 100%; }
    .input-row { display: flex; gap: .35rem; align-items: center; }
    .input-row input { flex: 1; min-width: 0; font-size: .82rem; }
    .hint { font-size: .7rem; color: var(--text-secondary); }
    .drive-connect { display: flex; gap: .5rem; align-items: center; }
    .drive-bar { display: flex; gap: .4rem; align-items: center; flex-wrap: wrap; }
    .muted { color: var(--text-secondary); }

    /* ─── Dialogs ─── */
    .picker { display: grid; gap: .6rem; }
    .picker-bar { display: flex; gap: .4rem; align-items: center; flex-wrap: wrap; }
    .picker-bar input { flex: 1 1 14rem; }
    ::ng-deep :is(.p-message, .p-message-content, .p-message-text) {
      min-width: 0; max-width: 100%; overflow-wrap: anywhere; white-space: normal; }
  `,
})
export class WorkbookRefField implements OnDestroy {
  private api = inject(Api);
  private gPicker = inject(GooglePicker);

  value = model<string>('');
  files = input<string[]>([]);
  placeholder = input('examples/01_simple/sales_source.xlsx');
  role = input<'source' | 'config'>('source');

  mode = signal<SourceKind>('local');
  drive = signal<DriveStatus | null>(null);
  chosenName = signal('');
  driveError = signal<string | null>(null);
  connecting = signal(false);
  pickingDrive = signal(false);
  editing = false;

  testing = signal(false);
  testResult = signal<{ name: string; sheets: string[]; size: number } | null>(null);
  testError = signal<string | null>(null);

  wdirRoot = signal<string | null>(null);
  wdirFolder = signal('');
  wdirItems = signal<WorkbookDirItem[]>([]);
  wdirLoading = signal(false);
  wdirError = signal<string | null>(null);
  browser = false;

  private own = '';

  /** Extracted filename for display. */
  fileName = signal('');

  private storageHandler = (e: StorageEvent) => {
    if (e.key === 'drive-connected') this.loadStatus();
  };

  constructor() {
    // Pre-load Drive status so the Drive tab shows connected immediately
    this.loadStatus();
    // Listen for Drive connection from the consent tab
    window.addEventListener('storage', this.storageHandler);

    effect(() => {
      const value = this.value();
      if (value === this.own) return;
      this.own = value;
      this.mode.set(kindOf(value));
      if (value.startsWith('drive:') && !this.chosenName()) this.nameOf(value);
    });
    // Extract filename + auto-test only when value actually changes
    let lastTested = '';
    effect(() => {
      const value = this.value();
      this.fileName.set(this.extractName(value));
      if (value && value !== lastTested) {
        lastTested = value;
        this.testResult.set(null);
        this.testError.set(null);
        this.autoTest(value);
      }
    });
  }

  ngOnDestroy() {
    window.removeEventListener('storage', this.storageHandler);
  }

  private extractName(ref: string): string {
    if (!ref) return '';
    if (ref.startsWith('drive:')) return this.chosenName() || ref;
    if (ref.includes('docs.google.com')) {
      const match = ref.match(/\/d\/([^/]+)/);
      return match ? `Google Sheet (${match[1].slice(0, 8)}…)` : 'Google Sheet';
    }
    const parts = ref.replace(/\\/g, '/').split('/');
    return parts[parts.length - 1] || ref;
  }

  private autoTestTimer: ReturnType<typeof setTimeout> | null = null;
  private autoTest(ref: string) {
    if (this.autoTestTimer) clearTimeout(this.autoTestTimer);
    this.autoTestTimer = setTimeout(() => {
      if (this.value() === ref) this.testAccess();
    }, 800);
  }

  type(value: string) {
    this.own = value;
    this.value.set(value);
  }

  openEdit() {
    this.editing = true;
    if (this.mode() === 'drive') this.loadStatus();
  }

  doneEditing() {
    this.editing = false;
  }

  setMode(mode: SourceKind) {
    this.mode.set(mode);
    if (mode === 'drive' && !this.drive()) this.loadStatus();
  }

  kindOf = kindOf;

  // ── test access ──

  testAccess() {
    const ref = this.value();
    if (!ref) return;
    this.testing.set(true);
    this.testResult.set(null);
    this.testError.set(null);
    this.api.testRef(ref, this.role()).subscribe({
      next: (r) => {
        this.testing.set(false);
        this.testResult.set(r);
        this.fileName.set(r.name);
      },
      error: (e) => { this.testing.set(false); this.testError.set(e.message); },
    });
  }

  // ── workbook dir browser ──

  openBrowser() {
    this.browser = true;
    this.wdirFolder.set('');
    this.wdirError.set(null);
    this.loadDir('');
  }

  private loadDir(folder: string) {
    this.wdirLoading.set(true);
    this.wdirError.set(null);
    this.api.browseWorkbookDir(folder).subscribe({
      next: (r) => {
        this.wdirRoot.set(r.root);
        this.wdirFolder.set(r.folder);
        this.wdirItems.set(r.items);
        this.wdirLoading.set(false);
      },
      error: (e) => { this.wdirLoading.set(false); this.wdirError.set(e.message); },
    });
  }

  wdirInto(item: WorkbookDirItem) { this.loadDir(item.path); }

  wdirUp() {
    const parts = this.wdirFolder().split('/');
    parts.pop();
    this.loadDir(parts.join('/'));
  }

  wdirChoose(item: WorkbookDirItem) {
    this.type(item.path);
    this.browser = false;
    this.editing = false;
  }

  // ── google drive ──

  // Shared caches across all WorkbookRefField instances to avoid duplicate calls
  private static driveStatusCache: { data: any; ts: number } | null = null;
  private static driveNameCache = new Map<string, string>();

  private loadStatus() {
    const now = Date.now();
    if (WorkbookRefField.driveStatusCache && now - WorkbookRefField.driveStatusCache.ts < 10000) {
      this.drive.set(WorkbookRefField.driveStatusCache.data);
      return;
    }
    this.api.driveStatus().subscribe({
      next: (s) => {
        WorkbookRefField.driveStatusCache = { data: s, ts: Date.now() };
        this.drive.set(s);
      },
      error: (e) => this.driveError.set(e.message),
    });
  }

  private nameOf(ref: string) {
    const fileId = ref.slice('drive:'.length);
    const cached = WorkbookRefField.driveNameCache.get(fileId);
    if (cached) {
      this.chosenName.set(cached);
      this.fileName.set(cached);
      return;
    }
    this.api.driveFile(fileId).subscribe({
      next: (f) => {
        WorkbookRefField.driveNameCache.set(fileId, f.name);
        this.chosenName.set(f.name);
        this.fileName.set(f.name);
      },
      error: () => this.chosenName.set(''),
    });
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
  }

  disconnect() {
    this.api.driveDisconnect().subscribe({
      next: () => { this.drive.set(null); this.loadStatus(); },
      error: (e) => this.driveError.set(e.message),
    });
  }

  openDrivePicker() {
    this.pickingDrive.set(true);
    this.driveError.set(null);
    const title = this.role() === 'config' ? 'Select configuration workbook' : 'Select source workbook';
    this.gPicker.pick(title).subscribe({
      next: (file) => {
        this.pickingDrive.set(false);
        this.chosenName.set(file.name);
        this.type(file.ref);
        this.editing = false;
      },
      error: (e) => {
        this.pickingDrive.set(false);
        if (e.message !== 'cancelled') this.driveError.set(e.message);
      },
    });
  }

  refresh() { this.loadStatus(); }
}

export function kindOf(value: string): SourceKind {
  if (value.startsWith('drive:')) return 'drive';
  return value.startsWith('http') && value.includes('docs.google.com') ? 'sheet' : 'local';
}
