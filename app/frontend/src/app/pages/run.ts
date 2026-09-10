import { Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ButtonModule } from '@openng/optimus-ui/button';
import { CardModule } from '@openng/optimus-ui/card';
import { MessageModule } from '@openng/optimus-ui/message';
import { TagModule } from '@openng/optimus-ui/tag';
import { Api } from '../core/api';
import { RunDetail } from '../core/models';

/** One entry from the history: what was pushed, from where, and what it said. */
@Component({
  selector: 'app-run',
  imports: [DatePipe, RouterLink, ButtonModule, CardModule, MessageModule, TagModule],
  template: `
    <div class="page">
      @if (error()) { <p-message severity="error" [text]="error()!" /> }
      @if (run(); as r) {
        <p-card>
          <ng-template #title>
            <div class="bar">
              <span>{{ r.project_name }}</span>
              <p-tag [value]="r.status"
                     [severity]="r.status === 'succeeded' ? 'success' : 'danger'" />
              <span class="grow"></span>
              <p-button label="Open configuration" size="small" [outlined]="true"
                        [routerLink]="['/project', r.project_id]" />
              <p-button label="Configurations" size="small" [text]="true" routerLink="/work" />
            </div>
          </ng-template>
          <div class="kv">
            <span class="muted">started</span><span>{{ r.started_at | date: 'medium' }}</span>
            <span class="muted">finished</span>
            <span>{{ r.finished_at ? (r.finished_at | date: 'medium') : '—' }}</span>
            <span class="muted">source file</span>
            <span>{{ r.source_name ?? '—' }} <code>{{ r.source_ref }}</code></span>
            <span class="muted">configuration</span>
            <span>{{ r.config_name ?? '—' }} <code>{{ r.config_ref }}</code></span>
            <span class="muted">source sha256</span><code>{{ r.source_sha256 ?? '—' }}</code>
            <span class="muted">config sha256</span><code>{{ r.config_sha256 ?? '—' }}</code>
            <span class="muted">destination</span>
            <span>{{ r.target ?? '—' }} {{ r.database ?? '' }}
              {{ r.db_schema ? '(schema ' + r.db_schema + ')' : '' }}
              {{ r.prefix ? '· prefix ' + r.prefix : '' }}</span>
            <span class="muted">file_id</span><span>{{ r.file_id ?? '—' }}</span>
            <span class="muted">rows</span><span>{{ r.row_total ?? '—' }}</span>
          </div>
        </p-card>

        <p-card>
          <ng-template #title>Rows per table</ng-template>
          <table class="cols">
            @for (row of rows(); track row.table) {
              <tr><td>{{ row.table }}</td><td>{{ row.rows }}</td></tr>
            }
          </table>
          @if (!rows().length) { <p class="muted">Nothing was inserted.</p> }
        </p-card>

        <p-card>
          <ng-template #title>Issues at push time ({{ r.issues.length }})</ng-template>
          @for (i of r.issues; track $index) {
            <div class="issue">
              <p-tag [value]="i.severity"
                     [severity]="i.severity === 'error' ? 'danger' : 'warn'" />
              <span class="muted">{{ i.where }}</span><span>{{ i.message }}</span>
            </div>
          }
          @if (!r.issues.length) { <p class="muted">None.</p> }
        </p-card>

        <p-card>
          <ng-template #title>Log</ng-template>
          <pre>{{ r.log_text || '(empty)' }}</pre>
        </p-card>
      }
    </div>

  `,
  styles: `
    .page { display: grid; gap: 1rem; padding: 1.25rem; }
    .bar { display: flex; gap: .75rem; align-items: center; }
    .bar .grow { flex: 1; }
    .kv { display: grid; grid-template-columns: 10rem minmax(0, 1fr); gap: .3rem .75rem; }
    .kv > * { min-width: 0; overflow-wrap: anywhere; }
    .muted { color: var(--p-text-muted-color); }
    .cols { border-collapse: collapse; font-size: .9rem; }
    .cols td { padding: .25rem 1.5rem .25rem 0;
               border-top: 1px solid var(--p-content-border-color); }
    .issue { display: grid; grid-template-columns: 6rem 16rem 1fr; gap: .5rem;
             font-size: .85rem; padding: .2rem 0; }
    pre { background: var(--p-content-hover-background); padding: .75rem; overflow: auto;
          max-height: 22rem; font-size: .8rem; }
  `,
})
export class RunPage {
  private api = inject(Api);
  private route = inject(ActivatedRoute);
  run = signal<RunDetail | null>(null);
  error = signal<string | null>(null);

  constructor() {
    this.api.run(this.route.snapshot.paramMap.get('id')!).subscribe({
      next: (r) => this.run.set(r),
      error: (e) => this.error.set(e.message),
    });
  }

  rows() {
    return Object.entries(this.run()?.rows_per_table ?? {})
      .map(([table, rows]) => ({ table, rows }));
  }
}
