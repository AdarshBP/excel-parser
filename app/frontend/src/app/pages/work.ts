import { Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ButtonModule } from '@openng/optimus-ui/button';
import { CardModule } from '@openng/optimus-ui/card';
import { DialogModule } from '@openng/optimus-ui/dialog';
import { InputTextModule } from '@openng/optimus-ui/inputtext';
import { MessageModule } from '@openng/optimus-ui/message';
import { SelectModule } from '@openng/optimus-ui/select';
import { SkeletonModule } from '@openng/optimus-ui/skeleton';
import { TableModule } from '@openng/optimus-ui/table';
import { TagModule } from '@openng/optimus-ui/tag';
import { Api } from '../core/api';
import { Project, RunSummary } from '../core/models';
import { WorkbookRefField } from './workbook-ref';

/** "My work": the caller's saved configurations and their push history. */
@Component({
  selector: 'app-work',
  imports: [
    DatePipe, FormsModule, RouterLink, ButtonModule, CardModule, DialogModule,
    InputTextModule, MessageModule, SelectModule, SkeletonModule, TableModule, TagModule,
    WorkbookRefField,
  ],
  template: `
    <div class="page">
      @if (error()) { <p-message severity="error" [text]="error()!" /> }

      @if (loading()) {
        <p-skeleton width="100%" height="3rem" />
        <p-skeleton width="100%" height="8rem" />
        <p-skeleton width="100%" height="8rem" />
      }

      <p-card>
        <ng-template #title>
          <div class="row">
            <span>My configurations</span>
            <p-button label="Download template" icon="pi pi-download" size="small"
                      [outlined]="true" (onClick)="downloadTemplate()" />
            <p-button label="New configuration" icon="pi pi-plus" size="small"
                      (onClick)="openNew()" />
          </div>
        </ng-template>

        <p-table [value]="projects()" [loading]="loading()" dataKey="project_id" size="small">
          <ng-template #header>
            <tr>
              <th>Name</th><th>Source</th><th>Configuration</th>
              <th>Rendered</th><th>Pushed</th><th></th>
            </tr>
          </ng-template>
          <ng-template #body let-p>
            <tr>
              <td><a [routerLink]="['/project', p.project_id]">{{ p.name }}</a></td>
              <td>
                <p-tag [value]="kindLabel(p.source_kind)" severity="secondary" />
                <span class="ref" [title]="p.source_ref">{{ p.source_ref }}</span>
              </td>
              <td>
                <p-tag [value]="kindLabel(p.config_kind)" severity="secondary" />
                <span class="ref" [title]="p.config_ref">{{ p.config_ref }}</span>
              </td>
              <td>{{ p.last_render_at ? (p.last_render_at | date: 'short') : '—' }}</td>
              <td>{{ p.last_push_at ? (p.last_push_at | date: 'short') : '—' }}</td>
              <td class="actions">
                <p-button label="Open" size="small" [text]="true"
                          [routerLink]="['/project', p.project_id]" />
                <p-button label="Duplicate" size="small" [text]="true"
                          (onClick)="duplicate(p)" />
                <p-button label="Delete" size="small" [text]="true" severity="danger"
                          (onClick)="remove(p)" />
              </td>
            </tr>
          </ng-template>
          <ng-template #emptymessage>
            <tr><td colspan="6" class="empty">Nothing saved yet: start with "New configuration".</td></tr>
          </ng-template>
        </p-table>
      </p-card>

      <p-card>
        <ng-template #title>History</ng-template>
        <p-table [value]="runs()" size="small">
          <ng-template #header>
            <tr>
              <th>When</th><th>Configuration</th><th>Source file</th>
              <th>Destination</th><th>Rows</th><th>file_id</th><th>Status</th><th></th>
            </tr>
          </ng-template>
          <ng-template #body let-r>
            <tr>
              <td>{{ r.started_at | date: 'short' }}</td>
              <td><a [routerLink]="['/project', r.project_id]">{{ r.project_name }}</a></td>
              <td>{{ r.source_name ?? '—' }}</td>
              <td>{{ r.target ?? '—' }} {{ r.database ?? '' }}
                  {{ r.db_schema ? '(' + r.db_schema + ')' : '' }}</td>
              <td>{{ r.row_total ?? '—' }}</td>
              <td>{{ r.file_id ?? '—' }}</td>
              <td>
                <p-tag [value]="r.status"
                       [severity]="r.status === 'succeeded' ? 'success' : 'danger'" />
              </td>
              <td><p-button label="Details" size="small" [text]="true"
                            [routerLink]="['/run', r.run_id]" /></td>
            </tr>
          </ng-template>
          <ng-template #emptymessage>
            <tr><td colspan="8" class="empty">No pushes yet.</td></tr>
          </ng-template>
        </p-table>
      </p-card>
    </div>

    <p-dialog header="New configuration" [(visible)]="dialog" [modal]="true"
              [style]="{ width: '34rem', maxWidth: '92vw' }">
      <div class="form">
        <div class="template-hint">
          <span>Need a starting point?</span>
          <p-button label="Download template" icon="pi pi-download" size="small"
                    [outlined]="true" (onClick)="downloadTemplate()" />
        </div>

        <label [class.label-err]="submitted && !draft.name.trim()">Name *</label>
        <input pInputText [(ngModel)]="draft.name" placeholder="e.g. Swiggy annexure"
               [class.input-err]="submitted && !draft.name.trim()" />

        <label [class.label-err]="submitted && !draft.config_ref.trim()">Configuration workbook *</label>
        <app-workbook-ref [(value)]="draft.config_ref" [files]="files()"
                          placeholder="examples/01_simple/sales_config.xlsx" role="config" />

        <label [class.label-err]="submitted && !draft.source_ref.trim()">Source workbook *</label>
        <app-workbook-ref [(value)]="draft.source_ref" [files]="files()"
                          placeholder="examples/01_simple/sales_source.xlsx" />

        @if (dialogError()) { <p-message severity="error" [text]="dialogError()!" /> }
      </div>
      <ng-template #footer>
        <p-button label="Cancel" [text]="true" (onClick)="dialog = false" />
        <p-button label="Create" [loading]="saving()" (onClick)="create()" />
      </ng-template>
    </p-dialog>
  `,
  styles: `
    .page { display: grid; gap: 1rem; padding: 1.25rem; }
    .row { display: flex; justify-content: space-between; align-items: center; }
    .ref { margin-left: .4rem; font-size: .72rem; color: var(--p-text-muted-color);
           display: inline-block; max-width: 20rem; overflow: hidden;
           text-overflow: ellipsis; white-space: nowrap; vertical-align: middle; }
    .actions { white-space: nowrap; }
    .empty { text-align: center; padding: 2rem 1rem !important;
             color: var(--p-text-muted-color); }
    .template-hint { display: flex; gap: .5rem; align-items: center; justify-content: space-between;
                     padding: .5rem .65rem; background: var(--primary-soft);
                     border: 1px solid var(--primary); border-radius: var(--radius-sm);
                     font-size: .8rem; color: var(--text-secondary); }
    .form { display: grid; gap: .6rem; min-width: 0; padding-top: .75rem; }
    .form > * { min-width: 0; max-width: 100%; }
    .form label { font-size: .75rem; font-weight: 500; color: var(--p-text-muted-color);
                  text-transform: uppercase; letter-spacing: 0.04em; transition: color .15s; }
    .label-err { color: var(--danger, #dc2626) !important; }
    .input-err { border-color: var(--danger, #dc2626) !important; }
    .input-err:focus { box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.15) !important; }
    .form input, .form p-select { width: 100%; }
    .form small { overflow-wrap: anywhere; font-size: .72rem; color: var(--p-text-muted-color); }
    .form p-message { min-width: 0; max-width: 100%; }
    .form ::ng-deep :is(.p-message, .p-message-content, .p-message-text) {
      min-width: 0; max-width: 100%; overflow-wrap: anywhere; white-space: normal; }
  `,
})
export class Work {
  private api = inject(Api);
  private router = inject(Router);

  loading = signal(true);
  projects = signal<Project[]>([]);
  runs = signal<RunSummary[]>([]);
  files = signal<string[]>([]);
  root = signal('');
  saving = signal(false);
  error = signal<string | null>(null);
  dialogError = signal<string | null>(null);
  dialog = false;
  submitted = false;
  draft = { name: '', source_ref: '', config_ref: '' };

  constructor() {
    this.load();
  }

  kindLabel(kind: Project['source_kind']) {
    return kind === 'sheet' ? 'link' : kind === 'drive' ? 'Drive' : 'local';
  }

  private load() {
    this.api.projects().subscribe({
      next: (p) => { this.projects.set(p); this.loading.set(false); },
      error: (e) => { this.error.set(e.message); this.loading.set(false); },
    });
    this.api.runs().subscribe({ next: (r) => this.runs.set(r) });
    this.api.localWorkbooks().subscribe({
      next: (w) => { this.files.set(w.files); this.root.set(w.root); },
    });
  }

  downloadTemplate() {
    window.open('/api/template', '_blank');
  }

  openNew() {
    this.draft = { name: '', source_ref: '', config_ref: '' };
    this.submitted = false;
    this.dialogError.set(null);
    this.dialog = true;
  }

  create() {
    this.submitted = true;
    const missing = [];
    if (!this.draft.name.trim()) missing.push('Name');
    if (!this.draft.source_ref.trim()) missing.push('Source workbook');
    if (!this.draft.config_ref.trim()) missing.push('Configuration workbook');
    if (missing.length) {
      this.dialogError.set(`Required: ${missing.join(', ')}`);
      return;
    }
    this.saving.set(true);
    this.dialogError.set(null);
    this.api.createProject(this.draft).subscribe({
      next: (p) => {
        this.saving.set(false);
        this.dialog = false;
        this.router.navigate(['/project', p.project_id]);
      },
      error: (e) => { this.saving.set(false); this.dialogError.set(e.message); },
    });
  }

  duplicate(project: Project) {
    this.api.duplicateProject(project.project_id).subscribe({
      next: () => this.load(),
      error: (e) => this.error.set(e.message),
    });
  }

  remove(project: Project) {
    if (!confirm(`Delete "${project.name}" and its history?`)) return;
    this.api.deleteProject(project.project_id).subscribe({
      next: () => this.load(),
      error: (e) => this.error.set(e.message),
    });
  }
}
