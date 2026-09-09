import { Component, inject, signal, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from '@openng/optimus-ui/button';
import { CardModule } from '@openng/optimus-ui/card';
import { DialogModule } from '@openng/optimus-ui/dialog';
import { InputTextModule } from '@openng/optimus-ui/inputtext';
import { MessageModule } from '@openng/optimus-ui/message';
import { TagModule } from '@openng/optimus-ui/tag';
import { TooltipModule } from '@openng/optimus-ui/tooltip';
import { Api } from '../core/api';
import { GooglePicker } from '../core/picker';
import {
  BatchFileResult, BatchPushResult, BatchValidateResult, WorkbookDirItem,
} from '../core/models';

@Component({
  selector: 'app-batch',
  imports: [
    FormsModule, ButtonModule, CardModule, DialogModule,
    InputTextModule, MessageModule, TagModule, TooltipModule,
  ],
  template: `
    <div class="page">
      <h2>Batch run</h2>
      <p class="subtitle">Validate and push multiple source files against one configuration.</p>

      <!-- Config selector -->
      <p-card class="setup">
        <ng-template #title>
          <div class="card-title-row">
            <span>Configuration</span>
            <p-button label="Download template" icon="pi pi-download" size="small"
                      [outlined]="true" (onClick)="downloadTemplate()" />
          </div>
        </ng-template>
        <div class="add-section">
          <div class="mode-tabs">
            <button class="tab" [class.active]="configMode === 'local'" (click)="configMode = 'local'">
              <i class="pi pi-file"></i> File
            </button>
            <button class="tab" [class.active]="configMode === 'link'" (click)="configMode = 'link'">
              <i class="pi pi-link"></i> Link
            </button>
            <button class="tab" [class.active]="configMode === 'drive'" (click)="configMode = 'drive'; loadDriveStatus()">
              <i class="pi pi-google"></i> Drive
            </button>
          </div>

          @if (configMode === 'local') {
            <div class="config-row">
              <input pInputText [(ngModel)]="configRef" placeholder="Path to configuration workbook" />
              <p-button icon="pi pi-folder-open" size="small" [outlined]="true"
                        pTooltip="Browse" (onClick)="browseFor = 'config'; browser = true; loadDir('')" />
            </div>
          }

          @if (configMode === 'link') {
            <div class="config-row">
              <input pInputText [(ngModel)]="configRef"
                     placeholder="https://docs.google.com/spreadsheets/d/..." />
            </div>
            <small class="hint">Share as "Anyone with the link: Viewer"</small>
          }

          @if (configMode === 'drive') {
            @if (!driveStatus()?.configured) {
              <p-message severity="warn" text="Google Drive not configured: set GOOGLE_CLIENT_ID in .env" />
            } @else if (!driveStatus()?.connected) {
              <div class="config-row">
                <p-button label="Connect Google Drive" icon="pi pi-google" size="small"
                          [loading]="driveConnecting()" (onClick)="connectDrive()" />
                <small class="hint">Read-only access</small>
              </div>
            } @else {
              <div class="config-row">
                <p-tag [value]="driveStatus()!.email ?? 'connected'" severity="success" />
                <p-button label="Pick from Drive" icon="pi pi-external-link" size="small"
                          [loading]="pickingDrive()" (onClick)="openDrivePicker('config')" />
              </div>
            }
          }

          @if (configRef) {
            <div class="config-result">
              <span class="file-name">{{ fileName(configRef) }}</span>
              <span class="file-path">{{ configRef }}</span>
              <p-button icon="pi pi-check-circle" size="small" [outlined]="true"
                        [loading]="testingConfig()" pTooltip="Test"
                        (onClick)="testConfig()" />
              @if (configOk()) { <i class="pi pi-check-circle status-ok"></i> }
              @if (configError()) { <i class="pi pi-times-circle status-err"
                                       [pTooltip]="configError()!"></i> }
            </div>
          }
        </div>
      </p-card>

      <!-- Source files -->
      <p-card class="setup">
        <ng-template #title>
          Source files
          @if (sourceRefs.length) {
            <span class="file-count">{{ sourceRefs.length }} file(s)</span>
          }
        </ng-template>

        <div class="add-section">
          <div class="mode-tabs">
            <button class="tab" [class.active]="addMode === 'local'" (click)="addMode = 'local'">
              <i class="pi pi-file"></i> File
            </button>
            <button class="tab" [class.active]="addMode === 'link'" (click)="addMode = 'link'">
              <i class="pi pi-link"></i> Link
            </button>
            <button class="tab" [class.active]="addMode === 'drive'" (click)="addMode = 'drive'; loadDriveStatus()">
              <i class="pi pi-google"></i> Drive
            </button>
          </div>

          @if (addMode === 'local') {
            <div class="add-row">
              <input pInputText [(ngModel)]="newRef" placeholder="Path to source workbook"
                     (keyup.enter)="addFile()" />
              <p-button icon="pi pi-folder-open" size="small" [outlined]="true"
                        pTooltip="Browse" (onClick)="browseFor = 'source'; browser = true; loadDir('')" />
              <p-button label="Add" icon="pi pi-plus" size="small" [outlined]="true"
                        [disabled]="!newRef.trim()" (onClick)="addFile()" />
            </div>
          }

          @if (addMode === 'link') {
            <div class="add-row">
              <input pInputText [(ngModel)]="newRef"
                     placeholder="https://docs.google.com/spreadsheets/d/..."
                     (keyup.enter)="addFile()" />
              <p-button label="Add" icon="pi pi-plus" size="small" [outlined]="true"
                        [disabled]="!newRef.trim()" (onClick)="addFile()" />
            </div>
            <small class="hint">Share as "Anyone with the link: Viewer"</small>
          }

          @if (addMode === 'drive') {
            @if (!driveStatus()?.configured) {
              <p-message severity="warn"
                text="Google Drive not configured: set GOOGLE_CLIENT_ID in .env" />
            } @else if (!driveStatus()?.connected) {
              <div class="add-row">
                <p-button label="Connect Google Drive" icon="pi pi-google" size="small"
                          [loading]="driveConnecting()" (onClick)="connectDrive()" />
                <small class="hint">Read-only access</small>
              </div>
            } @else {
              <div class="add-row">
                <p-tag [value]="driveStatus()!.email ?? 'connected'" severity="success" />
                <p-button label="Pick from Drive" icon="pi pi-external-link" size="small"
                          [loading]="pickingDrive()" (onClick)="openDrivePicker('source')" />
                <p-button label="Disconnect" size="small" [text]="true" severity="danger"
                          (onClick)="disconnectDrive()" />
              </div>
            }
            @if (driveError()) { <p-message severity="error" [text]="driveError()!" /> }
          }
        </div>

        @if (sourceRefs.length) {
          <div class="file-list">
            @for (ref of sourceRefs; track ref; let i = $index) {
              <div class="file-row" [class.file-ok]="fileStatus(ref) === 'valid' || fileStatus(ref) === 'pushed'"
                   [class.file-err]="fileStatus(ref) === 'error' || fileStatus(ref) === 'failed'">
                <i class="pi pi-file file-icon"></i>
                <div class="file-info">
                  <span class="file-name">{{ fileName(ref) }}</span>
                  <span class="file-path">{{ ref }}</span>
                  @if (fileResult(ref); as r) {
                    <span class="file-meta" [class.file-meta-err]="r.status === 'error' || r.status === 'failed'">
                      {{ r.message }}
                    </span>
                  }
                </div>
                <div class="file-status">
                  @if (fileStatus(ref) === 'valid' || fileStatus(ref) === 'pushed') {
                    <i class="pi pi-check-circle status-ok"></i>
                  } @else if (fileStatus(ref) === 'error' || fileStatus(ref) === 'failed') {
                    <i class="pi pi-times-circle status-err"></i>
                  }
                </div>
                <p-button icon="pi pi-times" size="small" [text]="true" severity="danger"
                          pTooltip="Remove" (onClick)="removeFile(i)" />
              </div>
            }
          </div>
        } @else {
          <p class="muted">No files added yet.</p>
        }
      </p-card>

      <!-- Validation results -->
      @if (validateResult()) {
        <p-card>
          <ng-template #title>Validation results</ng-template>

          <div class="batch-stats">
            <div class="push-stat">
              <span class="push-stat-value">{{ validateResult()!.total }}</span>
              <span class="push-stat-label">total</span>
            </div>
            <div class="push-stat" [class.push-stat-ok]="validateResult()!.valid > 0">
              <span class="push-stat-value">{{ validateResult()!.valid }}</span>
              <span class="push-stat-label">valid</span>
            </div>
            <div class="push-stat" [class.push-stat-err]="validateResult()!.errors > 0">
              <span class="push-stat-value">{{ validateResult()!.errors }}</span>
              <span class="push-stat-label">errors</span>
            </div>
          </div>

          @if (!validateResult()!.all_valid) {
            <p-message severity="error"
              text="Remove files with errors before pushing. All files must pass validation." />
          } @else {
            <p-message severity="success" text="All files are valid and ready to push." />
          }

          <!-- Per-file detail -->
          <div class="val-list">
            @for (r of validateResult()!.results; track r.ref) {
              <div class="val-file" [class.val-ok]="r.status === 'valid'"
                   [class.val-err]="r.status === 'error'">
                <div class="val-header" (click)="toggleExpand(r.ref)">
                  <i class="pi" [class.pi-check-circle]="r.status === 'valid'"
                     [class.pi-times-circle]="r.status === 'error'"
                     [class.status-ok]="r.status === 'valid'"
                     [class.status-err]="r.status === 'error'"></i>
                  <div class="val-info">
                    <span class="val-name">{{ r.name }}</span>
                    <span class="val-summary">{{ r.message }}</span>
                  </div>
                  @if (r.tables) {
                    <span class="val-badge">{{ r.tables }} tables · {{ r.rows }} rows</span>
                  }
                  @if (r.bad_cells) {
                    <p-tag [value]="r.bad_cells + ' type issue(s)'" severity="warn" />
                  }
                  @if (r.skipped) {
                    <p-tag [value]="r.skipped + ' skipped'" severity="warn" />
                  }
                  <i class="pi val-expand"
                     [class.pi-chevron-down]="!expanded[r.ref]"
                     [class.pi-chevron-up]="expanded[r.ref]"></i>
                </div>

                @if (expanded[r.ref] && r.issues?.length) {
                  <div class="val-details">
                    @for (issue of r.issues; track $index) {
                      <div class="val-issue">
                        <p-tag [value]="issue.severity"
                               [severity]="issue.severity === 'error' ? 'danger' : 'warn'" />
                        <span class="val-where">{{ issue.where }}</span>
                        <span>{{ issue.message }}</span>
                      </div>
                    }
                  </div>
                }
                @if (expanded[r.ref] && !r.issues?.length && r.status === 'error') {
                  <div class="val-details">
                    <span class="val-reason">{{ r.message }}</span>
                  </div>
                }
              </div>
            }
          </div>
        </p-card>
      }

      <!-- Push result -->
      @if (pushResult()) {
        <p-card>
          <ng-template #title>Push complete</ng-template>
          <div class="batch-stats">
            <div class="push-stat">
              <span class="push-stat-value">{{ pushResult()!.pushed }}</span>
              <span class="push-stat-label">pushed</span>
            </div>
            <div class="push-stat">
              <span class="push-stat-value">{{ pushResult()!.total_rows }}</span>
              <span class="push-stat-label">rows</span>
            </div>
            <div class="push-stat" [class.push-stat-err]="pushResult()!.failed > 0">
              <span class="push-stat-value">{{ pushResult()!.failed }}</span>
              <span class="push-stat-label">failed</span>
            </div>
          </div>
          <div class="file-list">
            @for (f of pushResult()!.files; track f.ref) {
              <div class="file-row" [class.file-ok]="f.status === 'pushed'"
                   [class.file-err]="f.status === 'failed' || f.status === 'skipped'">
                <i class="pi pi-file file-icon"></i>
                <div class="file-info">
                  <span class="file-name">{{ f.name }}</span>
                  <span class="file-meta">
                    @if (f.status === 'pushed') {
                      {{ f.rows }} rows · file_id {{ f.file_id }}
                    } @else {
                      {{ f.message }}
                    }
                  </span>
                </div>
                <p-tag [value]="f.status"
                       [severity]="f.status === 'pushed' ? 'success' : 'danger'" />
              </div>
            }
          </div>
        </p-card>
      }

      <!-- Error -->
      @if (error()) { <p-message severity="error" [text]="error()!" /> }

      <!-- Actions -->
      <div class="actions">
        <p-button label="Validate all" icon="pi pi-check" size="small"
                  [outlined]="true" [loading]="validating()"
                  [disabled]="!configRef || !sourceRefs.length"
                  pTooltip="Check all files against the configuration" tooltipPosition="top"
                  (onClick)="validate()" />
        <p-button label="Push all" icon="pi pi-database" size="small" severity="success"
                  [loading]="pushing()" [disabled]="!canPush()"
                  pTooltip="Push all valid files to the database" tooltipPosition="top"
                  (onClick)="push()" />
      </div>
    </div>

    <!-- Browse dialog -->
    <p-dialog header="Browse workbook directory" [(visible)]="browser" [modal]="true"
              [style]="{ width: '44rem', maxWidth: '94vw' }">
      <div class="picker">
        @if (!wdirRoot()) {
          <p-message severity="warn"
            text="No workbook directory configured: set WORKBOOK_DIR in .env." />
        } @else {
          <div class="picker-bar">
            <small class="muted">{{ wdirRoot() }}</small>
            @if (wdirFolder()) {
              <small class="muted">/ {{ wdirFolder() }}</small>
              <p-button label="Back" icon="pi pi-arrow-left" size="small" [text]="true"
                        (onClick)="wdirUp()" />
            }
          </div>
          <div class="file-list">
            @for (item of wdirItems(); track item.path) {
              <div class="file-row" (click)="pickItem(item)" style="cursor: pointer;">
                <i class="pi" [class.pi-folder]="item.kind === 'folder'"
                   [class.pi-file]="item.kind === 'file'" class="file-icon"></i>
                <div class="file-info">
                  <span class="file-name">{{ item.name }}</span>
                  @if (item.size) {
                    <span class="file-path">{{ (item.size / 1024).toFixed(0) }} KB</span>
                  }
                </div>
                @if (item.kind === 'file') {
                  <p-button label="Select" size="small" (onClick)="pickItem(item); $event.stopPropagation()" />
                }
              </div>
            }
            @if (!wdirItems().length) {
              <p class="muted">No .xlsx files here.</p>
            }
          </div>
        }
      </div>
    </p-dialog>


  `,
  styles: `
    .page { display: grid; gap: 1rem; padding: 1.25rem; margin: 0 auto; }
    .page > p-card.setup { max-width: 44rem; margin: 0 auto; width: 100%; }
    h2 { margin: 0; font-size: 1.1rem; }
    .subtitle { font-size: .8rem; color: var(--text-secondary); margin: 0; }

    .card-title-row { display: flex; align-items: center; justify-content: space-between; }
    .config-row, .add-row { display: flex; gap: .4rem; align-items: center; }
    .config-result { display: flex; gap: .5rem; align-items: center; padding: .4rem .5rem;
                     border: 1px solid var(--border); border-radius: var(--radius-sm);
                     margin-top: .25rem; }
    .config-result .file-name { font-weight: 600; font-size: .82rem; }
    .config-result .file-path { font-size: .68rem; color: var(--text-secondary);
                                flex: 1; overflow: hidden; text-overflow: ellipsis;
                                white-space: nowrap; }
    .add-section { display: grid; gap: .4rem; }
    .mode-tabs { display: flex; gap: 0; }
    .tab { display: flex; align-items: center; gap: .3rem; padding: .3rem .6rem;
           font-size: .75rem; background: transparent; border: none; color: var(--text-secondary);
           cursor: pointer; border-radius: var(--radius-sm); transition: all .15s; }
    .tab:hover { color: var(--text); background: var(--surface-hover); }
    .tab.active { color: var(--primary); font-weight: 600; background: var(--primary-soft); }
    .tab .pi { font-size: .7rem; }
    .hint { font-size: .7rem; color: var(--text-secondary); }
    .config-row input, .add-row input { flex: 1; min-width: 0; }

    .file-count { font-size: .75rem; font-weight: 400; color: var(--text-secondary);
                  margin-left: .5rem; }

    .file-list { display: grid; gap: .25rem; margin-top: .5rem; }
    .file-row { display: flex; gap: .5rem; align-items: center; padding: .45rem .6rem;
                border: 1px solid var(--border); border-radius: var(--radius-sm);
                transition: border-color .15s; }
    .file-row.file-ok { border-color: color-mix(in srgb, var(--success) 35%, var(--border)); }
    .file-row.file-err { border-color: color-mix(in srgb, var(--danger) 35%, var(--border)); }
    .file-icon { color: var(--text-secondary); flex-shrink: 0; }
    .file-info { flex: 1; min-width: 0; display: grid; gap: .1rem; }
    .file-name { font-weight: 600; font-size: .82rem; overflow: hidden;
                 text-overflow: ellipsis; white-space: nowrap; }
    .file-path { font-size: .68rem; color: var(--text-secondary); overflow: hidden;
                 text-overflow: ellipsis; white-space: nowrap; }
    .file-meta { font-size: .7rem; color: var(--text-secondary); }
    .file-meta-err { color: var(--danger); }
    .file-status { flex-shrink: 0; }
    .status-ok { color: var(--success); }
    .status-err { color: var(--danger); }

    .batch-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: .5rem;
                   margin-bottom: .75rem; }
    .push-stat { text-align: center; padding: .75rem .5rem; border: 1px solid var(--border);
                 border-radius: var(--radius-sm); }
    .push-stat-value { display: block; font-size: 1.15rem; font-weight: 700;
                       margin-bottom: .2rem; }
    .push-stat-label { font-size: .65rem; text-transform: uppercase; letter-spacing: .04em;
                       color: var(--text-secondary); }
    .push-stat-ok .push-stat-value { color: var(--success); }
    .push-stat-err { border-color: var(--danger); }
    .push-stat-err .push-stat-value { color: var(--danger); }

    .actions { display: flex; gap: .5rem; justify-content: flex-end; }

    /* ── Validation detail list ── */
    .val-list { display: grid; gap: .35rem; margin-top: .75rem; }
    .val-file { border: 1px solid var(--border); border-radius: var(--radius-sm);
                overflow: hidden; }
    .val-ok { border-left: 3px solid var(--success); }
    .val-err { border-left: 3px solid var(--danger); }
    .val-header { display: flex; gap: .5rem; align-items: center; padding: .5rem .65rem;
                  cursor: pointer; transition: background .1s; }
    .val-header:hover { background: var(--surface-hover); }
    .val-header > .pi:first-child { flex-shrink: 0; font-size: .9rem; }
    .val-info { flex: 1; min-width: 0; }
    .val-name { font-weight: 600; font-size: .82rem; display: block;
                overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .val-summary { font-size: .7rem; color: var(--text-secondary); display: block; }
    .val-badge { font-size: .68rem; color: var(--text-secondary); white-space: nowrap; }
    .val-expand { font-size: .7rem; color: var(--text-secondary); flex-shrink: 0;
                  margin-left: .25rem; }
    .val-details { padding: .4rem .65rem .5rem; background: var(--surface-hover);
                   border-top: 1px solid var(--border); }
    .val-issue { display: grid; grid-template-columns: 5rem 12rem 1fr; gap: .3rem;
                 font-size: .75rem; padding: .2rem 0; }
    .val-where { color: var(--text-secondary); font-size: .72rem; }
    .val-reason { font-size: .78rem; color: var(--danger); }

    .muted { color: var(--text-secondary); font-size: .8rem; }
    .picker { display: grid; gap: .5rem; }
    .picker-bar { display: flex; gap: .4rem; align-items: center; flex-wrap: wrap; }
  `,
})
export class BatchPage {
  private api = inject(Api);
  private gPicker = inject(GooglePicker);

  configRef = '';
  configMode: 'local' | 'link' | 'drive' = 'local';
  newRef = '';
  sourceRefs: string[] = [];
  browseFor: 'config' | 'source' = 'source';
  addMode: 'local' | 'link' | 'drive' = 'local';
  expanded: Record<string, boolean> = {};

  testingConfig = signal(false);
  configOk = signal(false);
  configError = signal<string | null>(null);

  validating = signal(false);
  validateResult = signal<BatchValidateResult | null>(null);
  pushing = signal(false);
  pushResult = signal<BatchPushResult | null>(null);
  error = signal<string | null>(null);

  // Drive state
  driveStatus = signal<{ configured: boolean; connected: boolean; email: string | null } | null>(null);
  driveConnecting = signal(false);
  driveError = signal<string | null>(null);
  pickingDrive = signal(false);

  // Browse state
  browser = false;
  wdirRoot = signal<string | null>(null);
  wdirFolder = signal('');
  wdirItems = signal<WorkbookDirItem[]>([]);

  canPush = computed(() => {
    const v = this.validateResult();
    return !!v && v.all_valid && v.valid > 0 && !this.pushResult();
  });

  toggleExpand(ref: string) {
    this.expanded = { ...this.expanded, [ref]: !this.expanded[ref] };
  }

  constructor() {
    // Pre-load Drive status so Drive tab shows connected immediately
    this.loadDriveStatus();
  }

  // ── config test ──

  downloadTemplate() {
    window.open('/api/template', '_blank');
  }

  testConfig() {
    this.testingConfig.set(true);
    this.configOk.set(false);
    this.configError.set(null);
    this.api.testRef(this.configRef, 'config').subscribe({
      next: () => { this.testingConfig.set(false); this.configOk.set(true); },
      error: (e) => { this.testingConfig.set(false); this.configError.set(e.message); },
    });
  }

  // ── file management ──

  addFile() {
    const ref = this.newRef.trim();
    if (!ref) return;
    if (this.sourceRefs.includes(ref)) {
      this.error.set(`"${this.fileName(ref)}" is already in the list`);
      return;
    }
    this.sourceRefs = [...this.sourceRefs, ref];
    this.newRef = '';
    this.validateResult.set(null);
    this.pushResult.set(null);
    this.error.set(null);
  }

  removeFile(index: number) {
    this.sourceRefs = this.sourceRefs.filter((_, i) => i !== index);
    this.validateResult.set(null);
    this.pushResult.set(null);
    this.error.set(null);
  }

  fileName(ref: string): string {
    return ref.replace(/\\/g, '/').split('/').pop() || ref;
  }

  fileResult(ref: string): BatchFileResult | null {
    const vr = this.validateResult();
    if (vr) return vr.results.find((r) => r.ref === ref) ?? null;
    const pr = this.pushResult();
    if (pr) return pr.files.find((r) => r.ref === ref) ?? null;
    return null;
  }

  fileStatus(ref: string): string {
    return this.fileResult(ref)?.status ?? '';
  }

  // ── validate ──

  validate() {
    this.validating.set(true);
    this.validateResult.set(null);
    this.pushResult.set(null);
    this.error.set(null);
    this.api.batchValidate(this.configRef, this.sourceRefs).subscribe({
      next: (r) => { this.validating.set(false); this.validateResult.set(r); },
      error: (e) => { this.validating.set(false); this.error.set(e.message); },
    });
  }

  // ── push ──

  push() {
    this.pushing.set(true);
    this.error.set(null);
    this.api.batchPush(this.configRef, this.sourceRefs).subscribe({
      next: (r) => { this.pushing.set(false); this.pushResult.set(r); },
      error: (e) => { this.pushing.set(false); this.error.set(e.message); },
    });
  }

  // ── browse ──

  loadDir(folder: string) {
    this.api.browseWorkbookDir(folder).subscribe({
      next: (r) => {
        this.wdirRoot.set(r.root);
        this.wdirFolder.set(r.folder);
        this.wdirItems.set(r.items);
      },
    });
  }

  wdirUp() {
    const parts = this.wdirFolder().split('/');
    parts.pop();
    this.loadDir(parts.join('/'));
  }

  pickItem(item: WorkbookDirItem) {
    if (item.kind === 'folder') {
      this.loadDir(item.path);
      return;
    }
    if (this.browseFor === 'config') {
      this.configRef = item.path;
      this.configOk.set(false);
      this.configError.set(null);
    } else {
      if (!this.sourceRefs.includes(item.path)) {
        this.sourceRefs = [...this.sourceRefs, item.path];
        this.validateResult.set(null);
        this.pushResult.set(null);
      }
    }
    this.browser = false;
  }

  // ── google drive ──

  loadDriveStatus() {
    this.api.driveStatus().subscribe({
      next: (s) => this.driveStatus.set(s),
      error: (e) => this.driveError.set(e.message),
    });
  }

  connectDrive() {
    this.driveConnecting.set(true);
    this.driveError.set(null);
    this.api.driveConnect().subscribe({
      next: ({ url }) => { this.driveConnecting.set(false); window.open(url, '_blank', 'noopener'); },
      error: (e) => { this.driveConnecting.set(false); this.driveError.set(e.message); },
    });
  }

  disconnectDrive() {
    this.api.driveDisconnect().subscribe({
      next: () => { this.driveStatus.set(null); this.loadDriveStatus(); },
      error: (e) => this.driveError.set(e.message),
    });
  }

  openDrivePicker(target: 'config' | 'source') {
    this.pickingDrive.set(true);
    this.driveError.set(null);

    if (target === 'config') {
      // Single select for config
      this.gPicker.pick('Select configuration workbook').subscribe({
        next: (file) => {
          this.pickingDrive.set(false);
          this.configRef = file.ref;
          this.configOk.set(false);
          this.configError.set(null);
        },
        error: (e) => {
          this.pickingDrive.set(false);
          if (e.message !== 'cancelled') this.driveError.set(e.message);
        },
      });
    } else {
      // Multi-select for source files
      this.gPicker.pickMany('Select source files (Ctrl/Cmd for multiple)').subscribe({
        next: (files) => {
          this.pickingDrive.set(false);
          let added = false;
          for (const file of files) {
            if (!this.sourceRefs.includes(file.ref)) {
              this.sourceRefs = [...this.sourceRefs, file.ref];
              added = true;
            }
          }
          if (added) {
            this.validateResult.set(null);
            this.pushResult.set(null);
          }
        },
        error: (e) => {
          this.pickingDrive.set(false);
          if (e.message !== 'cancelled') this.driveError.set(e.message);
        },
      });
    }
  }
}
