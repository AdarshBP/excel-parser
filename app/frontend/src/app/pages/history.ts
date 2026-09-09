import { Component, inject, signal, computed } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ButtonModule } from '@openng/optimus-ui/button';
import { CardModule } from '@openng/optimus-ui/card';
import { InputTextModule } from '@openng/optimus-ui/inputtext';
import { SelectModule } from '@openng/optimus-ui/select';
import { TagModule } from '@openng/optimus-ui/tag';
import { Api } from '../core/api';
import { RunSummary } from '../core/models';

@Component({
  selector: 'app-history',
  imports: [DatePipe, FormsModule, RouterLink, ButtonModule, CardModule,
            InputTextModule, SelectModule, TagModule],
  template: `
    <div class="page">
      <h2>Push history</h2>
      <p class="subtitle">Timeline of all push operations across your projects.</p>

      <!-- Filters -->
      <div class="filters">
        <input pInputText [(ngModel)]="search" placeholder="Search project or file..."
               class="filter-input" />
        <p-select appendTo="body" [options]="statusOptions" optionLabel="label" optionValue="value"
                  [(ngModel)]="statusFilter" placeholder="Status" [showClear]="true" />
      </div>

      @if (filtered().length) {
        <div class="timeline">
          @for (r of filtered(); track r.run_id) {
            <div class="tl-item" [class.tl-ok]="r.status === 'succeeded'"
                 [class.tl-fail]="r.status === 'failed'"
                 [class.tl-rb]="r.status === 'rolled_back'">
              <div class="tl-dot"></div>
              <div class="tl-card">
                <div class="tl-header">
                  <a [routerLink]="['/run', r.run_id]" class="tl-project">{{ r.project_name }}</a>
                  <p-tag [value]="r.status"
                         [severity]="r.status === 'succeeded' ? 'success' : r.status === 'rolled_back' ? 'warn' : 'danger'" />
                  <span class="tl-time">{{ r.started_at | date: 'medium' }}</span>
                </div>
                <div class="tl-body">
                  <div class="tl-detail">
                    @if (r.row_total) {
                      <span class="tl-stat">{{ r.row_total }} rows</span>
                    }
                    @if (r.target) {
                      <span class="tl-target">{{ r.target }}{{ r.database ? ' · ' + r.database : '' }}</span>
                    }
                    @if (r.source_name) {
                      <span class="tl-file">{{ r.source_name }}</span>
                    }
                  </div>
                  <div class="tl-meta">
                    @if (r.file_id) {
                      <span class="tl-fid">file_id: {{ r.file_id }}</span>
                    }
                    @if (r.db_schema) {
                      <span>schema: {{ r.db_schema }}</span>
                    }
                    @if (r.prefix) {
                      <span>prefix: {{ r.prefix }}</span>
                    }
                  </div>
                </div>
                <div class="tl-actions">
                  <p-button label="Details" size="small" [text]="true" icon="pi pi-arrow-right"
                            [routerLink]="['/run', r.run_id]" />
                  <p-button label="Project" size="small" [text]="true" icon="pi pi-external-link"
                            [routerLink]="['/project', r.project_id]" />
                </div>
              </div>
            </div>
          }
        </div>
      } @else {
        <p-card>
          <p class="muted center">
            @if (runs().length) {
              No runs match your filters.
            } @else {
              No push history yet.
            }
          </p>
        </p-card>
      }
    </div>
  `,
  styles: `
    .page { display: grid; gap: 1rem; padding: 1.25rem; max-width: 52rem; margin: 0 auto; }
    h2 { margin: 0; font-size: 1.1rem; }
    .subtitle { font-size: .8rem; color: var(--text-secondary); margin: 0; }

    .filters { display: flex; gap: .5rem; align-items: center; }
    .filter-input { flex: 1; min-width: 0; }

    /* Timeline */
    .timeline { display: grid; gap: 0; padding-left: 1rem; }
    .tl-item { display: flex; gap: .75rem; position: relative;
               padding: .25rem 0; border-left: 2px solid var(--border); padding-left: 1.25rem; }
    .tl-dot { position: absolute; left: -5px; top: .7rem; width: 8px; height: 8px;
              border-radius: 50%; background: var(--border); flex-shrink: 0; }
    .tl-ok .tl-dot { background: var(--success); }
    .tl-fail .tl-dot { background: var(--danger); }
    .tl-rb .tl-dot { background: #f59e0b; }

    .tl-card { flex: 1; min-width: 0; padding: .5rem .65rem; border: 1px solid var(--border);
               border-radius: var(--radius-sm); background: var(--surface);
               transition: box-shadow .15s; }
    .tl-card:hover { box-shadow: var(--shadow-sm); }

    .tl-header { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }
    .tl-project { font-weight: 600; font-size: .85rem; color: var(--primary);
                  text-decoration: none; }
    .tl-project:hover { text-decoration: underline; }
    .tl-time { font-size: .7rem; color: var(--text-secondary); margin-left: auto; }

    .tl-body { margin-top: .3rem; }
    .tl-detail { display: flex; gap: .75rem; font-size: .78rem; flex-wrap: wrap; }
    .tl-stat { font-weight: 600; }
    .tl-target { color: var(--text-secondary); }
    .tl-file { color: var(--text-secondary); }
    .tl-meta { display: flex; gap: .75rem; font-size: .68rem; color: var(--text-secondary);
               margin-top: .2rem; }
    .tl-fid { font-family: monospace; }

    .tl-actions { display: flex; gap: .25rem; margin-top: .25rem; }

    .muted { color: var(--text-secondary); font-size: .85rem; }
    .center { text-align: center; padding: 2rem 1rem; }
  `,
})
export class HistoryPage {
  private api = inject(Api);
  runs = signal<RunSummary[]>([]);

  search = '';
  statusFilter: string | null = null;
  statusOptions = [
    { label: 'Succeeded', value: 'succeeded' },
    { label: 'Failed', value: 'failed' },
    { label: 'Rolled back', value: 'rolled_back' },
  ];

  filtered = computed(() => {
    let list = this.runs();
    if (this.statusFilter) {
      list = list.filter(r => r.status === this.statusFilter);
    }
    if (this.search.trim()) {
      const q = this.search.toLowerCase();
      list = list.filter(r =>
        (r.project_name || '').toLowerCase().includes(q) ||
        (r.source_name || '').toLowerCase().includes(q) ||
        (r.config_name || '').toLowerCase().includes(q) ||
        (r.database || '').toLowerCase().includes(q));
    }
    return list;
  });

  constructor() {
    this.api.runs().subscribe({
      next: (r) => this.runs.set(r),
    });
  }
}
