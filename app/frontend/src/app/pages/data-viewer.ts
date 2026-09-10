import { Component, inject, signal, computed } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from '@openng/optimus-ui/button';
import { CardModule } from '@openng/optimus-ui/card';
import { InputTextModule } from '@openng/optimus-ui/inputtext';
import { MessageModule } from '@openng/optimus-ui/message';
import { TagModule } from '@openng/optimus-ui/tag';
import { TooltipModule } from '@openng/optimus-ui/tooltip';
import { Api } from '../core/api';
import { DataFile } from '../core/models';

@Component({
  selector: 'app-data-viewer',
  imports: [DatePipe, FormsModule, ButtonModule, CardModule,
            InputTextModule, MessageModule, TagModule, TooltipModule],
  template: `
    <div class="page">
      <div class="page-header">
        <div class="page-header-left">
          <h1 class="page-title">Data Viewer</h1>
          <p class="page-subtitle">Browse files loaded into the database and inspect their metadata.</p>
        </div>
      </div>

      @if (error()) { <p-message severity="error" [text]="error()!" /> }

      <!-- Search -->
      <div class="filters">
        <span class="p-input-icon-left filter-wrap">
          <input pInputText [(ngModel)]="search" placeholder="Search by file name, schema, or file ID..."
                 class="filter-input" (ngModelChange)="onSearch()" />
        </span>
        <span class="file-count">{{ filtered().length }} file(s)</span>
      </div>

      @if (filtered().length) {
        <div class="file-list">
          @for (f of filtered(); track f.file_id) {
            <div class="file-card" [class.expanded]="expanded() === f.file_id"
                 (click)="toggle(f.file_id)">
              <div class="file-row">
                <div class="file-icon">
                  <i class="pi pi-file"></i>
                </div>
                <div class="file-info">
                  <div class="file-name">{{ f.source_name || '(unnamed)' }}</div>
                  <div class="file-meta">
                    @if (f.db_schema) {
                      <span class="meta-item">
                        <i class="pi pi-database"></i> {{ f.db_schema }}
                      </span>
                    }
                    <span class="meta-item">
                      {{ f.tables.length }} table(s)
                    </span>
                  </div>
                </div>
                <div class="file-stats">
                  <span class="stat-rows">{{ f.row_total ?? 0 }} rows</span>
                  <span class="stat-time">{{ f.pushed_at | date: 'medium' }}</span>
                </div>
                <div class="file-chevron">
                  <i class="pi" [class.pi-chevron-down]="expanded() !== f.file_id"
                     [class.pi-chevron-up]="expanded() === f.file_id"></i>
                </div>
              </div>

              <!-- Expanded detail panel -->
              @if (expanded() === f.file_id) {
                <div class="detail-panel" (click)="$event.stopPropagation()">
                  @if (detailLoading()) {
                    <p class="muted">Loading details...</p>
                  } @else if (detail(); as d) {
                    <div class="detail-grid">
                      <div class="detail-section">
                        <h4>File metadata</h4>
                        <div class="kv">
                          <span class="label">File ID</span>
                          <code class="value">{{ d.file_id }}</code>
                          <span class="label">Source file</span>
                          <span class="value">{{ d.source_name }}</span>
                          @if (d.file_sha256) {
                            <span class="label">SHA-256</span>
                            <code class="value sha">{{ d.file_sha256 }}</code>
                          }
                          <span class="label">Pushed at</span>
                          <span class="value">{{ d.pushed_at | date: 'medium' }}</span>
                          <span class="label">Total rows</span>
                          <span class="value">{{ d.row_total }}</span>
                        </div>
                      </div>

                      <div class="detail-section">
                        <h4>Location</h4>
                        <div class="kv">
                          @if (d.db_schema) {
                            <span class="label">Schema</span>
                            <span class="value">{{ d.db_schema }}</span>
                          }
                          @if (d.config_ref) {
                            <span class="label">Config</span>
                            <span class="value">{{ d.config_ref }}</span>
                          }
                          @if (d.source_ref) {
                            <span class="label">Source ref</span>
                            <span class="value">{{ d.source_ref }}</span>
                          }
                        </div>
                      </div>
                    </div>

                    <!-- Per-table breakdown -->
                    @if (d.tables.length) {
                      <div class="detail-section tables-section">
                        <h4>Tables loaded ({{ d.tables.length }})</h4>
                        <table class="tables-table">
                          <thead>
                            <tr>
                              <th>Table</th>
                              <th>Sheet</th>
                              <th>Rows</th>
                              <th>Columns</th>
                              <th>Range</th>
                              <th>Loaded at</th>
                            </tr>
                          </thead>
                          <tbody>
                            @for (t of d.tables; track t.table_name) {
                              <tr>
                                <td><code>{{ t.table_name }}</code></td>
                                <td>{{ t.sheet_name }}</td>
                                <td class="num">{{ t.row_count }}</td>
                                <td class="num">{{ t.column_count }}</td>
                                <td class="num">{{ t.data_start_row }}{{ t.data_end_row ? '–' + t.data_end_row : '' }}</td>
                                <td>{{ t.loaded_at | date: 'medium' }}</td>
                              </tr>
                            }
                          </tbody>
                        </table>
                      </div>
                    }
                  }
                </div>
              }
            </div>
          }
        </div>
      } @else {
        <p-card>
          <p class="muted center">
            @if (files().length) {
              No files match your search.
            } @else {
              No files have been loaded yet. Push data from a configuration or batch run to see it here.
            }
          </p>
        </p-card>
      }
    </div>
  `,
  styles: `
    .page { display: grid; gap: 1rem; padding: 1.5rem 2rem; max-width: 64rem; }

    .filters { display: flex; gap: .75rem; align-items: center; }
    .filter-wrap { flex: 1; }
    .filter-input { width: 100%; }
    .file-count { font-size: .78rem; color: var(--text-secondary); white-space: nowrap; }

    .file-list { display: grid; gap: .5rem; }

    .file-card { border: 1px solid var(--border); border-radius: var(--radius-sm);
                 background: var(--surface); cursor: pointer; transition: box-shadow .15s; }
    .file-card:hover { box-shadow: var(--shadow-sm); }
    .file-card.expanded { border-color: var(--primary); }

    .file-row { display: flex; align-items: center; gap: .75rem; padding: .65rem .85rem; }

    .file-icon { display: flex; align-items: center; justify-content: center;
                 width: 2rem; height: 2rem; background: var(--surface-hover);
                 border-radius: var(--radius-sm); flex-shrink: 0; }
    .file-icon .pi { font-size: .9rem; color: var(--text-secondary); }

    .file-info { flex: 1; min-width: 0; }
    .file-name { font-weight: 600; font-size: .85rem; overflow: hidden;
                 text-overflow: ellipsis; white-space: nowrap; }
    .file-meta { display: flex; gap: .75rem; font-size: .72rem; color: var(--text-secondary);
                 margin-top: .15rem; flex-wrap: wrap; }
    .meta-item { display: flex; align-items: center; gap: .25rem; }
    .meta-item .pi { font-size: .65rem; }

    .file-stats { text-align: right; flex-shrink: 0; }
    .stat-rows { display: block; font-weight: 600; font-size: .82rem; }
    .stat-time { display: block; font-size: .68rem; color: var(--text-secondary); }

    .file-chevron { flex-shrink: 0; color: var(--text-secondary); }
    .file-chevron .pi { font-size: .7rem; }

    /* Detail panel */
    .detail-panel { padding: .5rem .85rem .85rem; border-top: 1px solid var(--border); }

    .detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    @media (max-width: 768px) { .detail-grid { grid-template-columns: 1fr; } }

    .detail-section { margin-bottom: .5rem; }
    .detail-section h4 { font-size: .78rem; font-weight: 700; text-transform: uppercase;
                         letter-spacing: .04em; color: var(--text-secondary);
                         margin: 0 0 .4rem; }

    .kv { display: grid; grid-template-columns: 7rem minmax(0, 1fr); gap: .2rem .5rem;
          font-size: .8rem; }
    .kv .label { color: var(--text-secondary); }
    .kv .value { overflow-wrap: anywhere; }
    .kv .sha { font-size: .7rem; }

    .tables-section { grid-column: 1 / -1; }
    .tables-table { width: 100%; border-collapse: collapse; font-size: .8rem; }
    .tables-table th { text-align: left; font-weight: 600; font-size: .72rem;
                       text-transform: uppercase; letter-spacing: .03em;
                       color: var(--text-secondary); padding: .3rem .5rem;
                       border-bottom: 2px solid var(--border); }
    .tables-table td { padding: .3rem .5rem; border-top: 1px solid var(--border); }
    .tables-table .num { text-align: right; font-variant-numeric: tabular-nums; }

    .muted { color: var(--text-secondary); font-size: .85rem; }
    .center { text-align: center; padding: 2rem 1rem; }
  `,
})
export class DataViewerPage {
  private api = inject(Api);
  files = signal<DataFile[]>([]);
  error = signal<string | null>(null);
  expanded = signal<string | null>(null);
  detail = signal<DataFile | null>(null);
  detailLoading = signal(false);

  search = '';

  filtered = computed(() => {
    let list = this.files();
    if (this.search.trim()) {
      const q = this.search.toLowerCase();
      list = list.filter(f =>
        (f.source_name || '').toLowerCase().includes(q) ||
        (f.config_ref || '').toLowerCase().includes(q) ||
        (f.db_schema || '').toLowerCase().includes(q) ||
        (f.file_id || '').toLowerCase().includes(q));
    }
    return list;
  });

  constructor() {
    this.loadFiles();
  }

  private loadFiles() {
    this.api.dataFiles().subscribe({
      next: (f) => this.files.set(f),
      error: (e) => this.error.set(e.message),
    });
  }

  onSearch() {
    // Client-side filtering is handled by the computed signal
  }

  toggle(fileId: string) {
    if (this.expanded() === fileId) {
      this.expanded.set(null);
      this.detail.set(null);
      return;
    }
    this.expanded.set(fileId);
    this.detail.set(null);
    this.detailLoading.set(true);
    this.api.dataFileDetail(fileId).subscribe({
      next: (d) => { this.detail.set(d); this.detailLoading.set(false); },
      error: (e) => { this.error.set(e.message); this.detailLoading.set(false); },
    });
  }
}
