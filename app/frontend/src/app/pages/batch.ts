import { Component, inject, signal, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from '@openng/optimus-ui/button';
import { InputTextModule } from '@openng/optimus-ui/inputtext';
import { MessageModule } from '@openng/optimus-ui/message';
import { TagModule } from '@openng/optimus-ui/tag';
import { TooltipModule } from '@openng/optimus-ui/tooltip';
import { Api } from '../core/api';
import { GooglePicker } from '../core/picker';
import {
  BatchFileResult, BatchPushResult, BatchValidateResult,
} from '../core/models';
import { WorkbookRefField } from './workbook-ref';

@Component({
  selector: 'app-batch',
  imports: [
    FormsModule, ButtonModule,
    InputTextModule, MessageModule, TagModule, TooltipModule,
    WorkbookRefField,
  ],
  template: `
    <div class="page">
      <div class="page-header">
        <div class="page-header-left">
          <h1 class="page-title">Batch run</h1>
          <p class="page-subtitle">Validate and push multiple source files against one configuration.</p>
        </div>
      </div>

      <!-- Step indicator -->
      <div class="step-indicator">
        <div class="step">
          <span class="step-circle active">1</span>
          <div>
            <div class="step-label">Select configuration</div>
            <div class="step-desc">Choose configuration and upload files</div>
          </div>
        </div>
        <div class="step-line"></div>
        <div class="step">
          <span class="step-circle" [class.active]="!!validateResult()" [class.inactive]="!validateResult()">2</span>
          <div>
            <div class="step-label">Validate</div>
            <div class="step-desc">Check for errors and fix</div>
          </div>
        </div>
        <div class="step-line"></div>
        <div class="step">
          <span class="step-circle" [class.active]="!!pushResult()" [class.inactive]="!pushResult()">3</span>
          <div>
            <div class="step-label">Push</div>
            <div class="step-desc">Push data to database</div>
          </div>
        </div>
      </div>

      <!-- Config selector -->
      <div class="section-card">
        <div class="section-card-header">
          <div>
            <div class="section-title">Configuration</div>
            <div class="section-desc" style="margin-bottom: 0;">Select the configuration to use for this batch run.</div>
          </div>
          <p-button label="Download template" icon="pi pi-download" size="small"
                    [outlined]="true" (onClick)="downloadTemplate()" />
        </div>
        <app-workbook-ref [(value)]="configRef" role="config"
                          handleKey="batch:config" />
      </div>

      <!-- Source files -->
      <div class="section-card">
        <div class="section-card-header">
          <div>
            <div class="section-title">Source files</div>
            <div class="section-desc" style="margin-bottom: 0;">Upload multiple source files to validate and push.</div>
          </div>
          <p-button label="Upload files" icon="pi pi-upload" size="small"
                    [outlined]="true" (onClick)="fileInput2.click()" />
          <input #fileInput2 type="file" multiple accept=".xlsx,.xlsm,.csv" hidden
                 (change)="onFileSelect($event)" />
        </div>

        <div class="drop-zone" [class.drop-active]="dragOver"
             (dragover)="onDragOver($event)" (dragleave)="dragOver = false"
             (drop)="onDrop($event)" (click)="fileInput3.click()">
          <i class="pi pi-cloud-upload drop-icon"></i>
          <span>Drop .xlsx or .csv files here, or click to browse</span>
          <small class="hint">Max 20 files, 20 MB each</small>
          <input #fileInput3 type="file" multiple accept=".xlsx,.xlsm,.csv" hidden
                 (change)="onFileSelect($event)" />
        </div>

        <div class="selected-header">Selected files ({{ uploadedFiles.length + sourceRefs.length }})</div>

        <div class="table-wrap-inner">
          <table class="files-table">
            <thead>
              <tr>
                <th>File name</th><th>Size</th><th>Status</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (f of uploadedFiles; track f.name; let i = $index) {
                <tr>
                  <td>{{ f.name }}</td>
                  <td>{{ (f.size / 1024).toFixed(0) }} KB</td>
                  <td>
                    @if (fileStatus(f.name) === 'valid' || fileStatus(f.name) === 'pushed') {
                      <i class="pi pi-check-circle status-ok"></i>
                    } @else if (fileStatus(f.name) === 'error' || fileStatus(f.name) === 'failed') {
                      <i class="pi pi-times-circle status-err"></i>
                    } @else {
                      <span class="muted">Pending</span>
                    }
                  </td>
                  <td>
                    <p-button icon="pi pi-times" size="small" [text]="true" severity="danger"
                              pTooltip="Remove" (onClick)="removeUpload(i)" />
                  </td>
                </tr>
              }
              @for (ref of sourceRefs; track ref; let i = $index) {
                <tr>
                  <td>{{ fileName(ref) }}</td>
                  <td>—</td>
                  <td>
                    @if (fileStatus(ref) === 'valid' || fileStatus(ref) === 'pushed') {
                      <i class="pi pi-check-circle status-ok"></i>
                    } @else if (fileStatus(ref) === 'error' || fileStatus(ref) === 'failed') {
                      <i class="pi pi-times-circle status-err"></i>
                    } @else {
                      <span class="muted">Pending</span>
                    }
                  </td>
                  <td>
                    <p-button icon="pi pi-times" size="small" [text]="true" severity="danger"
                              pTooltip="Remove" (onClick)="removeFile(i)" />
                  </td>
                </tr>
              }
              @if (!uploadedFiles.length && !sourceRefs.length) {
                <tr>
                  <td colspan="4">
                    <div class="empty-state">
                      <div class="empty-state-icon"><i class="pi pi-list"></i></div>
                      <p class="empty-state-title">No files selected yet</p>
                      <p class="empty-state-desc">Upload one or more files to continue.</p>
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

      <!-- Validation results -->
      @if (validateResult()) {
        <div class="section-card">
          <div class="section-title">Validation results</div>

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
        </div>
      }

      <!-- Push result -->
      @if (pushResult()) {
        <div class="section-card">
          <div class="section-title">Push complete</div>
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
        </div>
      }

      <!-- Error -->
      @if (error()) { <p-message severity="error" [text]="error()!" /> }

      <!-- Actions -->
      <div class="actions">
        <p-button label="Validate all" icon="pi pi-check" size="small"
                  [outlined]="true" [loading]="validating()"
                  [disabled]="!configRef || (!sourceRefs.length && !uploadedFiles.length)"
                  pTooltip="Check all files against the configuration" tooltipPosition="top"
                  (onClick)="validate()" />
        <p-button label="Push all" icon="pi pi-play" size="small" severity="success"
                  [loading]="pushing()" [disabled]="!canPush()"
                  pTooltip="Push all valid files to the database" tooltipPosition="top"
                  (onClick)="push()" />
      </div>
    </div>

  `,
  styles: `
    .page { display: grid; gap: 1rem; padding: 1.5rem 2rem; }

    .section-card-header { display: flex; align-items: flex-start; justify-content: space-between;
                           gap: 1rem; margin-bottom: .75rem; }

    .config-row, .add-row { display: flex; gap: .4rem; align-items: center; }
    .config-result { display: flex; gap: .5rem; align-items: center; padding: .4rem .5rem;
                     border: 1px solid var(--border); border-radius: var(--radius-sm);
                     margin-top: .25rem; }
    .config-result .file-name { font-weight: 600; font-size: .82rem; }
    .config-result .file-path { font-size: .68rem; color: var(--text-secondary);
                                flex: 1; overflow: hidden; text-overflow: ellipsis;
                                white-space: nowrap; }
    .add-section { display: grid; gap: .4rem; }
    .hint { font-size: .7rem; color: var(--text-secondary); }
    .config-row input, .add-row input { flex: 1; min-width: 0; }

    .selected-header { font-size: .85rem; font-weight: 600; margin-top: 1rem; margin-bottom: .35rem; }

    /* Files table */
    .table-wrap-inner { border: 1px solid var(--border); border-radius: var(--radius-sm);
                        overflow: hidden; }
    .files-table { width: 100%; border-collapse: collapse; font-size: .82rem; }
    .files-table th { background: var(--surface-raised-flat); border-bottom: 1px solid var(--border);
                      font-size: .72rem; font-weight: 600; text-transform: uppercase;
                      letter-spacing: .04em; color: var(--text-secondary);
                      padding: .55rem .75rem; text-align: left; }
    .files-table td { border-bottom: 1px solid var(--border); padding: .5rem .75rem;
                      color: var(--text); }
    .files-table tbody tr:last-child td { border-bottom: none; }
    .files-table tbody tr:hover td { background: var(--surface-hover); }

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

    /* ── Drop zone ── */
    .drop-zone { display: flex; flex-direction: column; align-items: center; gap: .4rem;
                 padding: 1.5rem; border: 2px dashed var(--border-strong); border-radius: var(--radius);
                 cursor: pointer; transition: all .2s; text-align: center;
                 color: var(--text-secondary); font-size: .82rem; margin-bottom: .25rem; }
    .drop-zone:hover { border-color: var(--primary); background: var(--primary-soft); }
    .drop-zone.drop-active { border-color: var(--primary); background: var(--primary-soft);
                             border-style: solid; }
    .drop-icon { font-size: 1.5rem; color: var(--primary); }

    /* ── tablet ── */
    @media (max-width: 1024px) {
      .page { padding: 1rem; }
      .section-card-header { flex-direction: column; gap: .35rem; align-items: flex-start; }
      .drop-zone { padding: 1rem; }
      .files-table th { font-size: .65rem; padding: .4rem .5rem; }
      .files-table td { font-size: .75rem; padding: .35rem .5rem; }
      .val-issue { grid-template-columns: 4.5rem 9rem 1fr; font-size: .7rem; }
    }
  `,
})
export class BatchPage {
  private api = inject(Api);
  private gPicker = inject(GooglePicker);

  configRef = '';
  newRef = '';
  sourceRefs: string[] = [];
  expanded: Record<string, boolean> = {};

  // Upload state
  uploadedFiles: File[] = [];
  dragOver = false;

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

  canPush = computed(() => {
    const v = this.validateResult();
    return !!v && v.all_valid && v.valid > 0 && !this.pushResult();
  });

  hasFiles = computed(() => this.sourceRefs.length > 0 || this.uploadedFiles.length > 0);

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

  // ── file upload ──

  onDragOver(event: DragEvent) {
    event.preventDefault();
    this.dragOver = true;
  }

  onDrop(event: DragEvent) {
    event.preventDefault();
    this.dragOver = false;
    const files = event.dataTransfer?.files;
    if (files) this.addUploads(Array.from(files));
  }

  onFileSelect(event: Event) {
    const input = event.target as HTMLInputElement;
    if (input.files) this.addUploads(Array.from(input.files));
    input.value = '';
  }

  private addUploads(files: File[]) {
    const allowed = ['.xlsx', '.xlsm', '.csv'];
    for (const f of files) {
      const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase();
      if (!allowed.includes(ext)) {
        this.error.set(`${f.name}: only .xlsx and .csv files are accepted`);
        return;
      }
    }
    const combined = [...this.uploadedFiles, ...files];
    if (combined.length > 20) {
      this.error.set(`Maximum 20 files allowed (you have ${combined.length})`);
      return;
    }
    this.uploadedFiles = combined;
    this.validateResult.set(null);
    this.pushResult.set(null);
    this.error.set(null);
  }

  removeUpload(index: number) {
    this.uploadedFiles = this.uploadedFiles.filter((_, i) => i !== index);
    this.validateResult.set(null);
    this.pushResult.set(null);
  }

  // ── validate ──

  validate() {
    this.validating.set(true);
    this.validateResult.set(null);
    this.pushResult.set(null);
    this.error.set(null);

    if (this.uploadedFiles.length) {
      // Validate one file at a time — UI updates after each
      const results: BatchFileResult[] = [];
      const files = [...this.uploadedFiles];
      const seen: Record<string, string> = {};

      const next = (i: number) => {
        if (i >= files.length) {
          this.validating.set(false);
          return;
        }
        const file = files[i];
        // Client-side duplicate check within batch
        this.api.batchValidateOne(this.configRef, file).subscribe({
          next: (r) => {
            // Duplicate content check within this batch
            if (r.status === 'valid' && r.sha256 && seen[r.sha256]) {
              r.status = 'error';
              r.message = `Duplicate content — identical to ${seen[r.sha256]}`;
            } else if (r.sha256) {
              seen[r.sha256] = r.name;
            }
            results.push(r);
            const valid = results.filter(x => x.status === 'valid').length;
            const errors = results.filter(x => x.status === 'error').length;
            this.validateResult.set({
              results: [...results],
              all_valid: errors === 0,
              total: files.length,
              valid,
              errors,
            });
            next(i + 1);
          },
          error: (e) => {
            results.push({
              ref: file.name, name: file.name, status: 'error',
              message: e.message, rows: 0,
            });
            const valid = results.filter(x => x.status === 'valid').length;
            const errors = results.filter(x => x.status === 'error').length;
            this.validateResult.set({
              results: [...results],
              all_valid: false,
              total: files.length,
              valid,
              errors,
            });
            next(i + 1);
          },
        });
      };
      next(0);
    } else {
      this.api.batchValidate(this.configRef, this.sourceRefs).subscribe({
        next: (r) => { this.validating.set(false); this.validateResult.set(r); },
        error: (e) => { this.validating.set(false); this.error.set(e.message); },
      });
    }
  }

  // ── push ──

  push() {
    this.pushing.set(true);
    this.error.set(null);

    if (this.uploadedFiles.length) {
      // Push one file at a time — UI updates after each
      const fileResults: BatchFileResult[] = [];
      const files = [...this.uploadedFiles];
      let totalRows = 0;

      const next = (i: number) => {
        if (i >= files.length) {
          this.pushing.set(false);
          return;
        }
        const file = files[i];
        this.api.batchPushOne(this.configRef, file).subscribe({
          next: (r) => {
            fileResults.push(r);
            if (r.rows) totalRows += r.rows;
            const pushed = fileResults.filter(x => x.status === 'pushed').length;
            const failed = fileResults.filter(x => x.status === 'failed').length;
            this.pushResult.set({
              batch_id: '',
              files: [...fileResults],
              total_rows: totalRows,
              pushed,
              failed,
              total: files.length,
              target: { target: '', database: '', db_schema: '', prefix: '' },
            });
            if (r.status === 'failed') {
              // Stop batch on first failure
              this.pushing.set(false);
              return;
            }
            next(i + 1);
          },
          error: (e) => {
            fileResults.push({
              ref: file.name, name: file.name, status: 'failed',
              message: e.message, rows: 0,
            });
            this.pushResult.set({
              batch_id: '',
              files: [...fileResults],
              total_rows: totalRows,
              pushed: fileResults.filter(x => x.status === 'pushed').length,
              failed: fileResults.filter(x => x.status === 'failed').length,
              total: files.length,
              target: { target: '', database: '', db_schema: '', prefix: '' },
            });
            this.pushing.set(false);
          },
        });
      };
      next(0);
    } else {
      this.api.batchPush(this.configRef, this.sourceRefs).subscribe({
        next: (r) => { this.pushing.set(false); this.pushResult.set(r); },
        error: (e) => { this.pushing.set(false); this.error.set(e.message); },
      });
    }
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
