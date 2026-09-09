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
import { DividerModule } from '@openng/optimus-ui/divider';
import { InputTextModule } from '@openng/optimus-ui/inputtext';
import { MessageModule } from '@openng/optimus-ui/message';
import { PanelModule } from '@openng/optimus-ui/panel';
import { SelectModule } from '@openng/optimus-ui/select';
import { SkeletonModule } from '@openng/optimus-ui/skeleton';
import { TableModule } from '@openng/optimus-ui/table';
import { TagModule } from '@openng/optimus-ui/tag';
import { ToggleSwitchModule } from '@openng/optimus-ui/toggleswitch';
import { TooltipModule } from '@openng/optimus-ui/tooltip';
import { Api } from '../core/api';
import { ErDiagram } from './er-diagram';
import { WorkbookRefField } from './workbook-ref';
import { Issue, Project, PushResult, RenderResult, Status, TableModel } from '../core/models';

// Poll interval comes from Settings (default 10s)

/** One saved configuration: render the diagram, inspect it, then push it. */
@Component({
  selector: 'app-project',
  imports: [
    DatePipe, FormsModule, RouterLink, ButtonModule, CardModule, DialogModule,
    DividerModule, InputTextModule, MessageModule, PanelModule, SelectModule,
    SkeletonModule, TableModule, TagModule, ToggleSwitchModule, TooltipModule,
    ErDiagram, WorkbookRefField,
  ],
  templateUrl: './project.html',
  styles: `
    .page { display: grid; gap: .75rem; padding: 1rem 1.25rem; min-width: 0; }
    .page > *, .page > * > * { min-width: 0; max-width: 100%; }
    :host ::ng-deep .p-card,
    :host ::ng-deep .p-card-body,
    :host ::ng-deep .p-card-content { min-width: 0; max-width: 100%; }

    /* ── toolbar: frosted glass strip ── */
    .skeleton-bar { display: flex; gap: .5rem; align-items: center; padding: .5rem .85rem; }

    .breadcrumb { display: flex; gap: .35rem; align-items: center; }
    .crumb { font-size: .78rem; color: var(--primary); text-decoration: none;
             cursor: pointer; white-space: nowrap; }
    .crumb:hover { text-decoration: underline; }
    .crumb-sep { font-size: .55rem; color: var(--text-secondary); }
    .crumb-current { font-size: .78rem; color: var(--text-secondary); white-space: nowrap;
                     max-width: 12rem; overflow: hidden; text-overflow: ellipsis; }

    .toolbar { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap;
               padding: .5rem .85rem;
               background: var(--surface);
               border: 1px solid var(--border);
               border-radius: var(--radius);
               box-shadow: var(--shadow-sm); }
    .toolbar .grow { flex: 1; }
    .toolbar .name-input { min-width: 8rem; max-width: 14rem; font-weight: 600;
                           font-size: .85rem; background: transparent !important;
                           border-color: transparent !important; }
    .toolbar .name-input:focus { border-color: var(--p-primary-color) !important; }
    .toolbar-status { display: flex; gap: .5rem; align-items: center;
                      font-size: .72rem; letter-spacing: 0.02em; }
    .toolbar-status .pi-spinner { font-size: .8rem; color: var(--primary); }

    .poll-indicator { display: flex; gap: .3rem; align-items: center;
                      padding: .2rem .5rem; border-radius: 999px;
                      background: var(--surface-hover); }
    .poll-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
    .poll-dot-ok { background: var(--success); }
    .poll-dot-stale { background: #f59e0b; animation: pulse 1.5s infinite; }
    .poll-dot-err { background: var(--danger); animation: pulse 1s infinite; }
    .poll-label { font-size: .68rem; color: var(--text-secondary); white-space: nowrap; }
    .poll-label-stale { color: #f59e0b; font-weight: 600; }
    .poll-label-err { color: var(--danger); font-weight: 600; }
    @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
    .status-stale { color: #f59e0b; font-weight: 600; }
    .preview-title-row { display: flex; align-items: center; justify-content: space-between; }
    .auto-config-hint { display: flex; gap: .5rem; align-items: center; padding: .5rem .65rem;
                        background: var(--primary-soft); border: 1px solid var(--primary);
                        border-radius: var(--radius-sm); font-size: .8rem; }
    .auto-config-hint .pi-info-circle { color: var(--primary); }

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

    /* ── configuration panel ── */
    .config-cards { display: grid; gap: .6rem; }
    .config-row { display: grid; grid-template-columns: 7rem minmax(0, 1fr);
                  gap: .5rem; align-items: start; }
    .config-label { font-size: .72rem; font-weight: 600; color: var(--text-secondary);
                    text-transform: uppercase; letter-spacing: .03em;
                    padding-top: .65rem; text-align: right; }
    .config-footer { display: flex; gap: 1.25rem; align-items: center; flex-wrap: wrap;
                     padding-top: .25rem; padding-left: 7.5rem; }
    .config-option { display: flex; gap: .4rem; align-items: center; }
    .config-option .config-label { padding-top: 0; text-align: left; }
    .status { font-size: .72rem; color: var(--text-secondary); }

    /* ── section bar ── */
    .section-bar { display: flex; gap: .5rem; align-items: center; }
    .section-meta { font-size: .75rem; margin-left: .25rem; }
    .section-meta.clickable { cursor: pointer; }
    .section-meta.clickable:hover { text-decoration: underline; }
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
  `,
})
export class ProjectPage implements OnDestroy {
  private api = inject(Api);
  private route = inject(ActivatedRoute);
  settings = inject(Settings);
  private msg = inject(MessageService);
  private poll?: Subscription;

  id = this.route.snapshot.paramMap.get('id')!;
  project = signal<Project | null>(null);
  render = signal<RenderResult | null>(null);
  status = signal<Status | null>(null);
  selected = signal<string | null>(null);
  view = signal<'er' | 'blocks'>('er');
  configOpen = true;
  files = signal<string[]>([]);
  root = signal('');
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
    this.api.localWorkbooks().subscribe({
      next: (w) => { this.files.set(w.files); this.root.set(w.root); },
    });

    // The 5-second poll only reports whether the workbooks changed; it never
    // re-renders on its own unless auto-render is on.
    this.refreshStatus();
    this.poll = interval(this.settings.pollMs())
      .pipe(switchMap(() => this.api.status(this.id)))
      .subscribe({
        next: (s) => {
          this.pollError.set(null);
          const wasStale = this.stale();
          this.status.set(s);
          if (this.autoRender && !wasStale && (s.source_changed || s.config_changed)) {
            this.doRender();
          }
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

  doRender() {
    this.busy.set(true);
    this.error.set(null);
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
    this.api.pushSchema(this.id).subscribe({
      next: (r: any) => {
        this.pushingSchema.set(false);
        this.schemaResult.set(r.message);
        this.msg.add({ severity: 'success', summary: 'Schema pushed', life: 2000 });
      },
      error: (e) => { this.pushingSchema.set(false); this.error.set(e.message); },
    });
  }

  confirmPush() {
    this.pushing.set(true);
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
