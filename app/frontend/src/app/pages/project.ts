import { Component, HostListener, OnDestroy, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription, interval, switchMap } from 'rxjs';
import { MessageService } from '@openng/optimus-ui/api';
import { Settings } from '../core/settings';
import { ButtonModule } from '@openng/optimus-ui/button';
import { CardModule } from '@openng/optimus-ui/card';
import { DialogModule } from '@openng/optimus-ui/dialog';

import { InputTextModule } from '@openng/optimus-ui/inputtext';
import { MessageModule } from '@openng/optimus-ui/message';

import { SelectModule } from '@openng/optimus-ui/select';
import { SkeletonModule } from '@openng/optimus-ui/skeleton';
import { TableModule } from '@openng/optimus-ui/table';
import { TagModule } from '@openng/optimus-ui/tag';
import { ToggleSwitchModule } from '@openng/optimus-ui/toggleswitch';
import { TooltipModule } from '@openng/optimus-ui/tooltip';
import { Api } from '../core/api';
import { FileHandleService, PickedFile, fsaErrorMessage } from '../core/file-handle';
import { ErDiagram } from './er-diagram';
import { WorkbookRefField } from './workbook-ref';
import { Issue, Project, PushResult, RenderResult, Status, TableModel } from '../core/models';

// Poll interval comes from Settings (default 10s)

/** One saved configuration: render the diagram, inspect it, then push it. */
@Component({
  selector: 'app-project',
  imports: [
    DatePipe, FormsModule, RouterLink, ButtonModule, CardModule, DialogModule,
    InputTextModule, MessageModule, SelectModule,
    SkeletonModule, TableModule, TagModule, ToggleSwitchModule, TooltipModule,
    ErDiagram, WorkbookRefField,
  ],
  templateUrl: './project.html',
  styles: `
    .page { display: grid; gap: .75rem; padding: 1rem 1.5rem; min-width: 0; }
    .page > *, .page > * > * { min-width: 0; max-width: 100%; }
    :host ::ng-deep .p-card,
    :host ::ng-deep .p-card-body,
    :host ::ng-deep .p-card-content { min-width: 0; max-width: 100%; }

    .skeleton-bar { display: flex; gap: .5rem; align-items: center; padding: .5rem .85rem; }
    .grow { flex: 1; }

    /* ── top bar ── */
    .topbar { display: flex; gap: .75rem; align-items: center;
              padding: .25rem 0; }
    .breadcrumb { display: flex; gap: .35rem; align-items: center; }
    .crumb { font-size: .75rem; color: var(--text-secondary); text-decoration: none;
             cursor: pointer; white-space: nowrap; }
    .crumb:hover { color: var(--text); text-decoration: none; }
    .crumb-sep { font-size: .45rem; color: var(--text-secondary); opacity: .4; }
    .crumb-current { font-size: .75rem; color: var(--text-secondary); white-space: nowrap;
                     max-width: 12rem; overflow: hidden; text-overflow: ellipsis; }
    .topbar-search { display: flex; align-items: center; gap: .4rem;
                     padding: .3rem .65rem; background: var(--surface);
                     border: 1px solid var(--border); border-radius: var(--radius-sm);
                     cursor: pointer; }
    .topbar-search:hover { border-color: var(--border-strong); }
    .topbar-search-icon { font-size: .7rem; color: var(--text-secondary); }
    .topbar-search-text { font-size: .72rem; color: var(--text-secondary); }
    .topbar-shortcut { display: flex; gap: .15rem; margin-left: .5rem; }
    .topbar-shortcut kbd { font-size: .58rem; font-family: inherit; padding: .1rem .25rem;
                           background: var(--surface-hover); border: 1px solid var(--border);
                           border-radius: 3px; color: var(--text-secondary); }

    /* ── project header ── */
    .proj-header { display: flex; align-items: center; justify-content: space-between;
                   gap: 1rem; }
    .proj-header-left { display: flex; flex-direction: column; gap: .1rem; min-width: 0; }
    .proj-title-row { display: flex; align-items: center; gap: .5rem; }
    .proj-name-input { font-size: 1.25rem !important; font-weight: 700 !important;
                       background: transparent !important; border-color: transparent !important;
                       padding: .1rem .25rem !important; height: auto !important;
                       line-height: 1.3 !important; min-width: 4rem; max-width: 16rem; }
    .proj-name-input:focus { border-color: var(--primary) !important; }
    .proj-subtitle { font-size: .78rem; color: var(--text-secondary); margin: 0; }
    .proj-header-right { display: flex; gap: .35rem; align-items: center; flex-shrink: 0; }
    .proj-stats { display: flex; flex-direction: column; align-items: flex-end;
                  gap: .1rem; font-size: .7rem; color: var(--text-secondary);
                  margin-right: .5rem; }

    .poll-indicator { display: inline-flex; gap: .3rem; align-items: center;
                      padding: .2rem .6rem; border-radius: 999px;
                      background: var(--success-soft); vertical-align: middle;
                      flex-shrink: 0; }
    .poll-indicator:has(.poll-dot-stale) { background: rgba(245, 158, 11, 0.1); }
    .poll-indicator:has(.poll-dot-err) { background: var(--danger-soft); }
    .poll-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
    .poll-dot-ok { background: var(--success); }
    .poll-dot-stale { background: #f59e0b; animation: pulse 1.5s infinite; }
    .poll-dot-err { background: var(--danger); animation: pulse 1s infinite; }
    .poll-label { font-size: .68rem; color: var(--success); white-space: nowrap; font-weight: 500; }
    .poll-label-stale { color: #f59e0b; font-weight: 600; }
    .poll-label-err { color: var(--danger); font-weight: 600; }
    @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
    .preview-title-row { display: flex; align-items: center; justify-content: space-between; }
    .auto-config-hint { display: flex; gap: .5rem; align-items: center; padding: .5rem .65rem;
                        background: var(--primary-soft); border: 1px solid var(--primary);
                        border-radius: var(--radius-sm); font-size: .8rem; margin-top: .5rem; }
    .auto-config-hint .pi-info-circle { color: var(--primary); }
    .browser-file-hint { display: flex; gap: .5rem; align-items: flex-start; padding: .5rem .65rem;
                         background: color-mix(in srgb, #f59e0b 8%, transparent);
                         border: 1px solid color-mix(in srgb, #f59e0b 25%, var(--border));
                         border-radius: var(--radius-sm); font-size: .75rem;
                         color: var(--text-secondary); line-height: 1.4; margin-top: .25rem; }
    .browser-file-hint .pi-info-circle { color: #f59e0b; font-size: .8rem; margin-top: .1rem;
                                         flex-shrink: 0; }

    .help-shortcuts { display: grid; gap: .35rem; }
    .shortcut-row { display: flex; gap: 1rem; align-items: center;
                    padding: .4rem .5rem; border-radius: var(--radius-sm); }
    .shortcut-row:hover { background: var(--surface-hover); }
    .shortcut-row kbd { min-width: 7rem; text-align: center; padding: .25rem .5rem;
                        background: var(--surface-hover); border: 1px solid var(--border);
                        border-radius: var(--radius-sm); font-size: .75rem;
                        font-family: inherit; white-space: nowrap; }
    .shortcut-row span { font-size: .8rem; color: var(--text-secondary); }

    /* button group: joined buttons */
    .btn-group { display: flex; gap: 0; align-items: center; }
    .btn-group ::ng-deep .p-button { border-radius: 0 !important; }
    .btn-group ::ng-deep :first-child .p-button {
      border-radius: var(--radius-sm) 0 0 var(--radius-sm) !important; }
    .btn-group ::ng-deep :last-child .p-button {
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0 !important; }

    /* ── configuration files section ── */
    .config-section { padding: 1rem 1.25rem; }
    .config-section-header { display: flex; align-items: center; justify-content: space-between;
                             margin-bottom: .75rem; }
    .config-hint { display: flex; gap: .35rem; align-items: center;
                   font-size: .72rem; color: var(--text-secondary); }
    .config-hint .pi { font-size: .7rem; }

    .config-file-rows { display: grid; gap: .5rem; }
    .config-file-row { display: grid; grid-template-columns: 16rem minmax(0, 1fr);
                       gap: .75rem; align-items: center;
                       padding: .75rem .85rem; border: 1px solid var(--border);
                       border-radius: var(--radius-sm); }
    .config-file-label { display: flex; gap: .5rem; align-items: center; }
    .config-file-icon { font-size: 1rem; color: var(--text-secondary); flex-shrink: 0; }
    .config-file-title { font-size: .82rem; font-weight: 600; }
    .config-file-desc { font-size: .68rem; color: var(--text-secondary); line-height: 1.4; }
    .config-file-detail { min-width: 0; }

    .config-footer { display: flex; gap: 1.5rem; align-items: center; flex-wrap: wrap;
                     padding-top: .75rem; border-top: 1px solid var(--border);
                     margin-top: .75rem; }
    .config-option { display: flex; gap: .4rem; align-items: center; }
    .config-label { font-size: .78rem; font-weight: 600; white-space: nowrap; }
    .config-option-desc { font-size: .68rem; color: var(--text-secondary); }

    /* ── bottom bar ── */
    .bottom-bar { display: flex; gap: .75rem; align-items: center;
                  padding: .45rem .75rem; background: var(--surface);
                  border: 1px solid var(--border); border-radius: var(--radius); }
    .bottom-meta { display: flex; gap: .25rem; align-items: center;
                   font-size: .75rem; }
    .bottom-meta.clickable { cursor: pointer; }
    .bottom-meta.clickable:hover { text-decoration: underline; }
    .bottom-icon-ok { color: var(--success); font-size: .72rem; }
    .bottom-icon-err { color: var(--danger); font-size: .72rem; }
    .bottom-icon-warn { color: #d97706; font-size: .72rem; }
    .err-count { color: var(--danger); font-weight: 600; }
    .warn-count { color: #d97706; font-weight: 500; }
    .ok-count { color: var(--success); }

    /* ── two-column layout ── */
    .split { display: grid; grid-template-columns: 18rem minmax(0, 1fr); gap: .75rem;
             align-items: start; }
    .split.wide { grid-template-columns: minmax(0, 1fr); }
    .split > * { min-width: 0; }
    .detail-stack { display: grid; gap: .75rem; min-width: 0; }
    .scrollx { overflow-x: auto; max-width: 100%; }

    /* ── block list sidebar ── */
    .blocks { display: grid; gap: .25rem; }
    .block { text-align: left; border: 1px solid var(--border);
             border-radius: var(--radius-sm); padding: .45rem .65rem;
             background: transparent; cursor: pointer; color: inherit;
             transition: all .15s ease; }
    .block:hover { background: var(--surface-hover);
                   border-color: var(--border-strong); }
    .block.on { border-color: var(--p-primary-color);
                background: rgba(59, 130, 246, 0.08); }
    .block small { display: block; color: var(--p-text-muted-color); font-size: .72rem; }

    /* ── table detail ── */
    .diagram { border: 1px solid var(--border);
               border-radius: var(--radius-sm);
               overflow: hidden; max-width: 100%;
               background: var(--surface); }
    .diagram h4 { margin: 0; padding: .5rem .75rem; font-size: .85rem; font-weight: 600;
                   background: var(--surface-raised);
                   border-bottom: 1px solid var(--border); }
    .cols { width: 100%; border-collapse: collapse; font-size: .8rem; }
    .cols td { padding: .25rem .75rem; border-top: 1px solid var(--border); }
    .cols .lineage { color: var(--p-text-muted-color); }
    .cols .type { color: var(--p-primary-color); white-space: nowrap; font-size: .72rem; }
    .muted { color: var(--text-secondary); }
    .cellval { cursor: help; }

    /* ── issues ── */
    .issue { display: grid; grid-template-columns: 5.5rem 14rem 1fr; gap: .4rem;
             font-size: .8rem; padding: .15rem 0; }

    /* ── data quality ── */
    .dq-label { font-size: .8rem; color: var(--text-secondary); margin: .5rem 0 .25rem; }
    .dq-label:first-child { margin-top: 0; }
    .dq-item { display: grid; grid-template-columns: 10rem 12rem 1fr; gap: .4rem;
               font-size: .78rem; padding: .15rem 0;
               border-bottom: 1px solid var(--border); }
    .dq-item:last-child { border-bottom: none; }
    .dq-cell { font-family: monospace; color: var(--primary); }
    .dq-col { color: var(--text-secondary); }
    .dq-warn .dq-cell { color: #d97706; }
    .dq-skip .dq-cell { color: var(--text-secondary); }
    .push-dq-warn { display: grid; gap: .4rem; margin-top: .5rem; }

    /* ── push dialog ── */
    .push-content { display: grid; gap: 1rem; padding: .25rem 0; }
    .push-dest { display: flex; gap: .75rem; align-items: center; padding: .65rem .75rem;
                 border: 1px solid var(--border); border-radius: var(--radius-sm);
                 background: var(--surface-raised); }
    .push-dest-icon { font-size: 1.5rem; color: var(--primary); flex-shrink: 0; }
    .push-dest-info { flex: 1; min-width: 0; }
    .push-dest-name { font-weight: 600; font-size: .9rem; }
    .push-dest-detail { font-size: .72rem; color: var(--text-secondary); margin-top: .1rem; }
    .push-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: .6rem; }
    .push-stat { text-align: center; padding: .85rem .5rem; border: 1px solid var(--border);
                 border-radius: var(--radius-sm); }
    .push-stat-value { display: block; font-size: 1.15rem; font-weight: 700;
                       margin-bottom: .2rem; }
    .push-stat-label { font-size: .65rem; text-transform: uppercase; letter-spacing: .04em;
                       color: var(--text-secondary); }
    .push-stat-err { border-color: var(--danger); }
    .push-stat-err .push-stat-value { color: var(--danger); }
    .push-details { border: 1px solid var(--border); border-radius: var(--radius-sm);
                    overflow: hidden; }
    .push-detail-row { display: flex; justify-content: space-between; padding: .45rem .85rem;
                       font-size: .8rem; border-bottom: 1px solid var(--border); }
    .push-detail-row:last-child { border-bottom: none; }
    .push-detail-row:nth-child(even) { background: var(--surface-raised); }
    .push-detail-label { color: var(--text-secondary); font-size: .75rem; }
    .push-result-tables { display: grid; gap: .2rem; }
    .push-result-row { display: flex; justify-content: space-between; padding: .25rem .5rem;
                       font-size: .8rem; border-bottom: 1px solid var(--border); }
    .push-result-row:last-child { border-bottom: none; }
    .push-result-count { font-weight: 600; color: var(--primary); }
    .push-dq-warn { display: grid; gap: .4rem; }
    pre { background: var(--surface-raised); padding: .75rem; overflow: auto;
          max-height: 24rem; font-size: .75rem; border-radius: var(--radius-sm);
          border: 1px solid var(--border); }

    /* ── tablet ── */
    @media (max-width: 1024px) {
      .page { padding: .75rem 1rem; gap: .5rem; }
      .topbar-search-text { display: none; }
      .topbar-shortcut { margin-left: 0; }
      .proj-header { flex-direction: column; align-items: flex-start; gap: .5rem; }
      .proj-header-right { flex-wrap: wrap; width: 100%; }
      .proj-stats { flex-direction: row; margin-right: auto; gap: .5rem; }
      .proj-name-input { font-size: 1rem !important; max-width: 12rem; }
      .proj-subtitle { font-size: .7rem; }
      .config-section { padding: .75rem; }
      .config-section-header { flex-direction: column; gap: .25rem; align-items: flex-start; }
      .config-file-row { grid-template-columns: 1fr; gap: .35rem; }
      .config-footer { gap: .75rem; }
      .config-option-desc { display: none; }
      .bottom-bar { gap: .4rem; padding: .35rem .5rem; flex-wrap: wrap; }
      .split { grid-template-columns: 14rem minmax(0, 1fr); gap: .5rem; }
      .issue { grid-template-columns: 4.5rem 10rem 1fr; font-size: .72rem; }
      .dq-item { grid-template-columns: 7rem 9rem 1fr; font-size: .72rem; }
      .push-stats { grid-template-columns: repeat(2, 1fr); }
    }
  `,
})
export class ProjectPage implements OnDestroy {
  private api = inject(Api);
  private route = inject(ActivatedRoute);
  settings = inject(Settings);
  private msg = inject(MessageService);
  private fh = inject(FileHandleService);
  private poll?: Subscription;

  id = this.route.snapshot.paramMap.get('id')!;
  project = signal<Project | null>(null);
  render = signal<RenderResult | null>(null);
  status = signal<Status | null>(null);
  selected = signal<string | null>(null);
  view = signal<'er' | 'blocks'>('er');
  configOpen = true;
  busy = signal(false);
  pushing = signal(false);
  pushingSchema = signal(false);
  error = signal<string | null>(null);
  pollError = signal<string | null>(null);
  pushResult = signal<PushResult | null>(null);
  schemaResult = signal<string | null>(null);
  pushIssues = signal<Issue[]>([]);
  ddlText = signal<string>('');
  helpDialog = false;
  isMac = navigator.platform.toUpperCase().includes('MAC');
  generatingConfig = signal(false);
  pushDialog = false;
  ddlDialog = false;
  edit = { name: '', source_ref: '', config_ref: '' };
  autoRender = false;
  /** Empty means "whatever target_config says"; otherwise it overrides it. */
  idType: '' | 'integer' | 'uuid' = '';
  idTypes = [
    { label: 'from configuration', value: '' },
    { label: 'Number', value: 'integer' },
    { label: 'UUID', value: 'uuid' },
  ];

  errors = computed(() => (this.render()?.issues ?? []).filter((i) => i.severity === 'error'));
  warnings = computed(() => (this.render()?.issues ?? []).filter((i) => i.severity === 'warning'));

  /** All data type mismatches across all tables. */
  badCells = computed(() => {
    const previews = this.render()?.previews ?? {};
    const all: { table: string; cell: string; column: string; message: string }[] = [];
    for (const [table, p] of Object.entries(previews)) {
      for (const b of p.bad_cells) all.push({ table, ...b });
    }
    return all;
  });
  /** All skipped rows (required column empty) across all tables. */
  skippedRows = computed(() => {
    const previews = this.render()?.previews ?? {};
    const all: { table: string; row: number; columns: string[] }[] = [];
    for (const [table, p] of Object.entries(previews)) {
      for (const s of p.skipped) all.push({ table, ...s });
    }
    return all;
  });
  stale = computed(() => {
    const s = this.status();
    return !!s && (s.source_changed || s.config_changed);
  });
  /** Push is allowed only when: no config errors, no type mismatches, no skipped rows. */
  canPush = computed(() =>
    !!this.render()?.can_push && !this.badCells().length && !this.skippedRows().length);
  table = computed<TableModel | null>(() => {
    const name = this.selected();
    const result = this.render();
    if (!result) return null;
    return [...result.tables, ...(result.control_tables ?? [])]
      .find((t) => t.table_name === name) ?? null;
  });
  preview = computed(() => {
    const name = this.selected();
    return name ? (this.render()?.previews?.[name] ?? null) : null;
  });
  totalRows = computed(() =>
    Object.values(this.render()?.previews ?? {}).reduce((sum, p) => sum + p.loadable_rows, 0));

  constructor() {
    this.api.project(this.id).subscribe({
      next: (p) => {
        this.project.set(p);
        this.edit = { name: p.name, source_ref: p.source_ref, config_ref: p.config_ref };
        this.autoRender = p.auto_render;
        this.idType = p.target?.id_type ?? '';
        if (p.render) {
          this.render.set(p.render);
          this.selected.set(p.render.tables[0]?.table_name ?? null);
        } else if (p.source_ref && p.config_ref) {
          // Auto-render on first open when both workbooks are set
          this.doRender();
        }
      },
      error: (e) => this.error.set(e.message),
    });
    // The 5-second poll only reports whether the workbooks changed; it never
    // re-renders on its own unless auto-render is on.
    // For upload: refs with stored handles, client-side lastModified checks
    // are tried first; the backend poll still runs as a fallback.
    this.refreshStatus();
    this.poll = interval(this.settings.pollMs())
      .pipe(switchMap(() => this.api.status(this.id)))
      .subscribe({
        next: (s) => {
          this.pollError.set(null);
          // For upload: refs, client-side handle checks detect local file edits.
          // The backend can't detect changes because it only sees the static cache copy.
          // Ensure IDB handles are loaded before checking.
          const sourceUpload = this.edit.source_ref.startsWith('upload:');
          const configUpload = this.edit.config_ref.startsWith('upload:');

          // If we have file handles, use them for client-side change detection.
          // If handles are missing (after refresh / IDB failure), fall back to
          // backend fingerprinting — the status still works, just can't detect
          // edits to the original local file. The card shows a re-select prompt.
          this.fh.ensureLoaded().then(() => {
            const checks: Promise<void>[] = [];
            if (sourceUpload && !s.source_changed && this.fh.has(`${this.id}:source`)) {
              checks.push(
                this.fh.hasChanged(`${this.id}:source`)
                  .then((changed) => { s.source_changed = changed; })
                  .catch(() => {}));
            }
            if (configUpload && !s.config_changed && this.fh.has(`${this.id}:config`)) {
              checks.push(
                this.fh.hasChanged(`${this.id}:config`)
                  .then((changed) => { s.config_changed = changed; })
                  .catch(() => {}));
            }

            Promise.all(checks).then(() => {
              const wasStale = this.stale();
              this.status.set(s);
              if (this.autoRender && !wasStale && (s.source_changed || s.config_changed)) {
                this.doRender();
              }
            });
          });
        },
        error: (e) => this.pollError.set(e.message),
      });
  }

  ngOnDestroy() { this.poll?.unsubscribe(); }

  @HostListener('document:keydown', ['$event'])
  onKeyDown(e: KeyboardEvent) {
    if (!this.settings.keyboardShortcuts()) return;
    const mod = e.metaKey || e.ctrlKey;
    if (!mod) return;
    if (e.key === 's') { e.preventDefault(); this.save(); }
    else if (e.key === 'r') { e.preventDefault(); this.doRender(); }
    else if (e.key === 'Enter') { e.preventDefault(); if (this.canPush()) this.openPush(); }
    else if (e.key === 'd') { e.preventDefault(); this.showDdl(); }
    else if (e.key === '/') { e.preventDefault(); this.helpDialog = !this.helpDialog; }
  }

  private refreshStatus() {
    this.api.status(this.id).subscribe({ next: (s) => this.status.set(s) });
  }

  /**
   * Re-upload any browser-held files so the backend has fresh bytes.
   * If a handle is missing (page refresh / IDB failure), auto-opens the
   * file picker so the user can re-select — the Render button click
   * provides the user gesture needed for showOpenFilePicker().
   */
  private async refreshUploads(): Promise<void> {
    await this.fh.ensureLoaded();
    for (const role of ['source', 'config'] as const) {
      const key = `${this.id}:${role}`;
      const ref = role === 'source' ? this.edit.source_ref : this.edit.config_ref;
      if (!ref.startsWith('upload:')) continue;

      let picked = this.fh.has(key) ? await this.fh.reread(key) : null;

      // No handle or read failed — auto-prompt user to re-select
      if (!picked && this.fh.isSupported()) {
        try {
          picked = await new Promise<PickedFile | null>((resolve, reject) => {
            this.fh.pick().subscribe({ next: resolve, error: reject });
          });
        } catch (e: any) {
          // User cancelled the picker (AbortError) — skip this ref
          if (e instanceof DOMException && e.name === 'AbortError') continue;
          continue;
        }
        if (picked) this.fh.store(key, picked.handle, picked.file.lastModified, picked.name);
      }

      if (!picked) continue;
      const result = await new Promise<{ ref: string }>((resolve, reject) => {
        this.api.uploadWorkbook(picked!.file).subscribe({ next: resolve, error: reject });
      });
      this.fh.markSeen(key, picked.file.lastModified);
      if (role === 'source') this.edit.source_ref = result.ref;
      else this.edit.config_ref = result.ref;
    }
  }

  doRender() {
    this.busy.set(true);
    this.error.set(null);
    this.refreshUploads().then(() => {
      // Save first so the backend renders the current refs, not stale ones
      const target = { ...(this.project()?.target ?? {}) };
      if (this.idType) target.id_type = this.idType;
      else delete target.id_type;
      this.api.updateProject(this.id, {
        ...this.edit, auto_render: this.autoRender, target,
      }).subscribe({
        next: (p) => {
          this.project.set(p);
          this.api.render(this.id).subscribe({
            next: (result) => {
              this.render.set(result);
              if (!this.selected() || !result.tables.some((t) => t.table_name === this.selected())) {
                this.selected.set(result.tables[0]?.table_name ?? null);
              }
              this.busy.set(false);
              this.refreshStatus();
              const rows = Object.values(result.previews ?? {}).reduce((s, p) => s + p.loadable_rows, 0);
              this.msg.add({ severity: 'success',
                summary: `Rendered ${result.tables.length} table(s), ${rows} rows`, life: 2000 });
            },
            error: (e) => { this.busy.set(false); this.error.set(e.message); },
          });
        },
        error: (e) => { this.busy.set(false); this.error.set(e.message); },
      });
    }).catch((e) => {
      this.busy.set(false);
      this.error.set(fsaErrorMessage(e));
    });
  }

  save() {
    this.busy.set(true);
    const target = { ...(this.project()?.target ?? {}) };
    if (this.idType) target.id_type = this.idType;
    else delete target.id_type;
    this.api.updateProject(this.id, {
      ...this.edit, auto_render: this.autoRender, target,
    }).subscribe({
      next: (p) => {
        this.project.set(p); this.busy.set(false); this.refreshStatus();
        this.msg.add({ severity: 'success', summary: 'Saved', life: 2000 });
      },
      error: (e) => { this.busy.set(false); this.error.set(e.message); },
    });
  }

  isCsvSource() {
    return this.edit.source_ref.toLowerCase().endsWith('.csv');
  }

  hasBrowserFiles() {
    return this.edit.source_ref.startsWith('upload:') || this.edit.config_ref.startsWith('upload:');
  }

  autoGenerateConfig() {
    this.generatingConfig.set(true);
    this.error.set(null);
    this.api.autoConfig(this.edit.source_ref).subscribe({
      next: (result) => {
        this.generatingConfig.set(false);
        this.edit.config_ref = result.config_ref;
        this.msg.add({ severity: 'success', summary: `Config generated: ${result.name}`, life: 2000 });
      },
      error: (e) => { this.generatingConfig.set(false); this.error.set(e.message); },
    });
  }

  exportCsv() {
    const table = this.selected();
    if (!table) return;
    window.open(this.api.exportCsvUrl(this.id, table), '_blank');
  }

  /** Keys are part of the schema, so changing them re-renders the diagram. */
  changeIdType() {
    this.busy.set(true);
    const target = { ...(this.project()?.target ?? {}) };
    if (this.idType) target.id_type = this.idType;
    else delete target.id_type;
    this.api.updateProject(this.id, { target }).subscribe({
      next: (p) => { this.project.set(p); this.doRender(); },
      error: (e) => { this.busy.set(false); this.error.set(e.message); },
    });
  }

  openPush() {
    this.pushResult.set(null);
    this.schemaResult.set(null);
    this.pushIssues.set([]);
    this.error.set(null);
    this.pushDialog = true;
  }

  confirmPushSchema() {
    this.pushingSchema.set(true);
    this.error.set(null);
    this.schemaResult.set(null);
    this.refreshUploads().then(() => {
      const target = { ...(this.project()?.target ?? {}) };
      if (this.idType) target.id_type = this.idType;
      else delete target.id_type;
      this.api.updateProject(this.id, {
        ...this.edit, auto_render: this.autoRender, target,
      }).subscribe({
        next: () => {
          this.api.pushSchema(this.id).subscribe({
            next: (r: any) => {
              this.pushingSchema.set(false);
              this.schemaResult.set(r.message);
              this.msg.add({ severity: 'success', summary: 'Schema pushed', life: 2000 });
            },
            error: (e) => { this.pushingSchema.set(false); this.error.set(e.message); },
          });
        },
        error: (e) => { this.pushingSchema.set(false); this.error.set(e.message); },
      });
    }).catch((e) => {
      this.pushingSchema.set(false);
      this.error.set(fsaErrorMessage(e));
    });
  }

  confirmPush() {
    this.pushing.set(true);
    this.refreshUploads().then(() => {
      // Save refs so the backend pushes the latest uploaded bytes
      const target = { ...(this.project()?.target ?? {}) };
      if (this.idType) target.id_type = this.idType;
      else delete target.id_type;
      this.api.updateProject(this.id, {
        ...this.edit, auto_render: this.autoRender, target,
      }).subscribe({
        next: () => {
          this.api.push(this.id, !this.settings.loadTracking()).subscribe({
            next: (result) => {
              this.pushing.set(false); this.pushResult.set(result);
              this.msg.add({ severity: 'success', summary: `Pushed ${result.row_total} rows`, life: 2000 });
            },
            error: (e) => {
              this.pushing.set(false);
              this.error.set(e.message);
              this.pushIssues.set(e.issues ?? []);
            },
          });
        },
        error: (e) => { this.pushing.set(false); this.error.set(e.message); },
      });
    }).catch((e) => {
      this.pushing.set(false);
      this.error.set(fsaErrorMessage(e));
    });
  }

  showDdl() {
    this.ddlText.set('loading…');
    this.ddlDialog = true;
    this.api.ddl(this.id).subscribe({
      next: (text) => this.ddlText.set(text),
      error: (e) => this.ddlText.set(e.message),
    });
  }

  scrollToValidation() {
    document.getElementById('validation')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  scrollToDataQuality() {
    document.getElementById('data-quality')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  show(table: TableModel) {
    this.selected.set(table.table_name);
    if (table.control) this.view.set('er');
  }

  rowsOf(table: string): number {
    return this.render()?.previews?.[table]?.loadable_rows ?? 0;
  }

  pushedRows(): { table: string; rows: number }[] {
    const rows = this.pushResult()?.rows_per_table ?? {};
    return Object.entries(rows).map(([table, count]) => ({ table, rows: count }));
  }
}
