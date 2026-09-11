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
      <!-- Step indicator -->
      <div class="stepper">
        <div class="step"
             [class.active]="!validateResult() && !pushResult()"
             [class.done]="!!validateResult() || !!pushResult()">
          <span class="step-num">
            @if (!!validateResult() || !!pushResult()) { <i class="pi pi-check"></i> } @else { 1 }
          </span>
          <div class="step-text">
            <div class="step-label">Select configuration</div>
            <div class="step-desc">Choose configuration and upload files</div>
          </div>
        </div>
        <div class="step-bar" [class.filled]="!!validateResult() || !!pushResult()"></div>
        <div class="step"
             [class.active]="!!validateResult() && !pushResult()"
             [class.done]="!!pushResult()">
          <span class="step-num">
            @if (!!pushResult()) { <i class="pi pi-check"></i> } @else { 2 }
          </span>
          <div class="step-text">
            <div class="step-label">Validate</div>
            <div class="step-desc">Check for errors and fix</div>
          </div>
        </div>
        <div class="step-bar" [class.filled]="!!pushResult()"></div>
        <div class="step"
             [class.active]="pushing()"
             [class.done]="!!pushResult() && !pushing()">
          <span class="step-num">
            @if (!!pushResult() && !pushing()) { <i class="pi pi-check"></i> } @else { 3 }
          </span>
          <div class="step-text">
            <div class="step-label">Push</div>
            <div class="step-desc">Push data to database</div>
          </div>
        </div>
      </div>

      <!-- Config + Source side by side -->
      <div class="two-col">
        <!-- Selected configuration -->
        <div class="section-card">
          <div class="section-header">
            <div class="section-icon"><i class="pi pi-cog"></i></div>
            <div class="section-info">
              <div class="section-title">Selected configuration</div>
              @if (!configRef) {
                <div class="section-desc">Choose the configuration workbook.</div>
              }
            </div>
          </div>
          <app-workbook-ref [(value)]="configRef" role="config"
                            handleKey="batch:config" />
        </div>

        <!-- Source files -->
        <div class="section-card">
          <div class="section-header">
            <div class="section-icon"><i class="pi pi-cloud-upload"></i></div>
            <div class="section-info">
              <div class="section-title">Source files</div>
              <div class="section-desc">Upload multiple .xlsx or .csv files to validate and push.</div>
            </div>
          </div>

          <div class="drop-zone" [class.drop-active]="dragOver"
               (dragover)="onDragOver($event)" (dragleave)="dragOver = false"
               (drop)="onDrop($event)" (click)="fileInput2.click()">
            <i class="pi pi-cloud-upload drop-icon"></i>
            <span>Drop .xlsx or .csv files here, or click to browse</span>
            <small class="drop-hint">Supports multiple files</small>
            <input #fileInput2 type="file" multiple accept=".xlsx,.xlsm,.csv" hidden
                   (change)="onFileSelect($event)" />
          </div>
        </div>
      </div>

      <!-- Validation results summary -->
      @if (validateResult()) {
        <div class="section-card">
          <div class="section-header">
            <div class="section-icon success-icon"><i class="pi pi-check-circle"></i></div>
            <div class="section-info">
              <div class="section-title">Validation results</div>
              <div class="section-desc" [class.success-text]="validateResult()!.all_valid"
                   [class.error-text]="!validateResult()!.all_valid">
                @if (validateResult()!.all_valid) {
                  All files are valid and ready to push.
                } @else {
                  {{ validateResult()!.errors }} file(s) have errors. Remove or fix them before pushing.
                }
              </div>
            </div>
            @if (showValidationDetails) {
              <p-button label="Hide validation details" size="small" [text]="true"
                        icon="pi pi-eye-slash" (onClick)="showValidationDetails = false" />
            } @else {
              <p-button label="View validation details" size="small" [text]="true"
                        icon="pi pi-arrow-right" iconPos="right"
                        (onClick)="showValidationDetails = true" />
            }
          </div>

          <div class="stats-row">
            <div class="stat-card">
              <div class="stat-icon"><i class="pi pi-file"></i></div>
              <div class="stat-body">
                <div class="stat-value">{{ validateResult()!.total }}</div>
                <div class="stat-label">Total files</div>
              </div>
            </div>
            <div class="stat-card stat-success">
              <div class="stat-icon"><i class="pi pi-check-circle"></i></div>
              <div class="stat-body">
                <div class="stat-value">{{ validateResult()!.valid }}</div>
                <div class="stat-label">Valid files</div>
              </div>
            </div>
            <div class="stat-card" [class.stat-danger]="validateResult()!.errors > 0">
              <div class="stat-icon"><i class="pi pi-times-circle"></i></div>
              <div class="stat-body">
                <div class="stat-value">{{ validateResult()!.errors }}</div>
                <div class="stat-label">Errors</div>
              </div>
            </div>
          </div>

          <!-- Expandable validation details -->
          @if (showValidationDetails) {
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
          }
        </div>
      }

      <!-- Files table + detail panel -->
      @if (uploadedFiles().length || sourceRefs.length) {
        <div class="section-card">
          <div class="section-header">
            <div class="section-icon"><i class="pi pi-file"></i></div>
            <div class="section-info">
              <div class="section-title">Files ({{ totalFiles() }})</div>
              <div class="section-desc">
                @if (validateResult()?.all_valid) {
                  All files passed validation and are ready to be pushed.
                } @else if (validateResult()) {
                  {{ validateResult()!.errors }} file(s) need attention.
                } @else {
                  Select files and validate before pushing.
                }
              </div>
            </div>
            <div class="table-controls">
              <span class="p-input-icon-left search-wrap">
                <input pInputText [(ngModel)]="fileSearch" placeholder="Search files..."
                       class="search-input" />
              </span>
            </div>
          </div>

          <div class="files-split" [class.has-detail]="!!selectedFile()">
            <!-- Table -->
            <div class="table-wrap">
              <table class="files-table">
                <thead>
                  <tr>
                    <th class="col-num">#</th>
                    <th>File name</th>
                    <th class="col-tables">Tables</th>
                    <th class="col-rows">Rows</th>
                    <th class="col-size">Size</th>
                    <th class="col-status">Validation</th>
                    <th class="col-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  @for (f of filteredFiles(); track f.name; let i = $index) {
                    <tr [class.row-selected]="selectedFile() === f.name"
                        (click)="selectFile(f.name)">
                      <td class="col-num">{{ i + 1 }}</td>
                      <td>
                        <div class="file-cell">
                          <i class="pi pi-file-excel file-type-icon"></i>
                          <span class="file-cell-name">{{ f.name }}</span>
                        </div>
                      </td>
                      <td class="col-tables">{{ fileResultFor(f.name)?.tables ?? '—' }}</td>
                      <td class="col-rows">{{ fileResultFor(f.name)?.rows ?? '—' }}</td>
                      <td class="col-size">{{ (f.size / 1024).toFixed(0) }} KB</td>
                      <td class="col-status">
                        @if (fileStatus(f.name) === 'valid' || fileStatus(f.name) === 'pushed') {
                          <p-tag value="Valid" severity="success" />
                        } @else if (fileStatus(f.name) === 'error' || fileStatus(f.name) === 'failed') {
                          <p-tag value="Error" severity="danger" />
                        } @else {
                          <p-tag value="Pending" severity="secondary" />
                        }
                      </td>
                      <td class="col-actions">
                        <p-button icon="pi pi-eye" size="small" [text]="true" [rounded]="true"
                                  pTooltip="View details"
                                  (onClick)="selectFile(f.name); $event.stopPropagation()" />
                        <p-button icon="pi pi-times" size="small" [text]="true" [rounded]="true"
                                  severity="danger" pTooltip="Remove"
                                  (onClick)="removeUpload(uploadedFiles().indexOf(f)); $event.stopPropagation()" />
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>

            <!-- Detail panel (right side) -->
            @if (selectedFile(); as name) {
              <div class="file-detail">
                <div class="detail-top">
                  <div class="detail-title">
                    <i class="pi pi-file-excel file-type-icon"></i>
                    <span>{{ name }}</span>
                  </div>
                  <p-button icon="pi pi-times" size="small" [text]="true" [rounded]="true"
                            pTooltip="Close" (onClick)="selectedFile.set(null)" />
                </div>

                @if (fileResultFor(name); as r) {
                  <!-- Summary -->
                  <div class="detail-summary">
                    <div class="detail-row">
                      <span class="detail-label">Status</span>
                      @if (r.status === 'valid' || r.status === 'pushed') {
                        <p-tag value="Valid" severity="success" />
                      } @else if (r.status === 'error' || r.status === 'failed') {
                        <p-tag value="Error" severity="danger" />
                      } @else {
                        <p-tag value="Pending" severity="secondary" />
                      }
                    </div>
                    <div class="detail-row">
                      <span class="detail-label">Message</span>
                      <span class="detail-value">{{ r.message }}</span>
                    </div>
                    @if (r.tables) {
                      <div class="detail-row">
                        <span class="detail-label">Tables</span>
                        <span class="detail-value">{{ r.tables }}</span>
                      </div>
                    }
                    @if (r.rows) {
                      <div class="detail-row">
                        <span class="detail-label">Rows</span>
                        <span class="detail-value">{{ r.rows }}</span>
                      </div>
                    }
                    @if (r.bad_cells) {
                      <div class="detail-row">
                        <span class="detail-label">Type issues</span>
                        <span class="detail-value detail-warn">{{ r.bad_cells }}</span>
                      </div>
                    }
                    @if (r.skipped) {
                      <div class="detail-row">
                        <span class="detail-label">Skipped rows</span>
                        <span class="detail-value">{{ r.skipped }}</span>
                      </div>
                    }
                    @if (r.sha256) {
                      <div class="detail-row">
                        <span class="detail-label">SHA-256</span>
                        <code class="detail-value detail-sha">{{ r.sha256 }}</code>
                      </div>
                    }
                  </div>

                  <!-- Issues list -->
                  @if (r.issues?.length) {
                    <div class="detail-issues-header">
                      Issues ({{ r.issues.length }})
                    </div>
                    <div class="detail-issues">
                      @for (issue of r.issues; track $index) {
                        <div class="detail-issue">
                          <p-tag [value]="issue.severity"
                                 [severity]="issue.severity === 'error' ? 'danger' : 'warn'" />
                          <div class="detail-issue-body">
                            <span class="detail-issue-where">{{ issue.where }}</span>
                            <span class="detail-issue-msg">{{ issue.message }}</span>
                          </div>
                        </div>
                      }
                    </div>
                  }
                } @else {
                  <div class="detail-empty">
                    <i class="pi pi-info-circle"></i>
                    <span>Run validation to see details for this file.</span>
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
          <div class="section-header">
            <div class="section-icon success-icon"><i class="pi pi-check-circle"></i></div>
            <div class="section-info">
              <div class="section-title">Push complete</div>
            </div>
          </div>
          <div class="stats-row">
            <div class="stat-card stat-success">
              <div class="stat-icon"><i class="pi pi-check-circle"></i></div>
              <div class="stat-body">
                <div class="stat-value">{{ pushResult()!.pushed }}</div>
                <div class="stat-label">Pushed</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon"><i class="pi pi-database"></i></div>
              <div class="stat-body">
                <div class="stat-value">{{ pushResult()!.total_rows }}</div>
                <div class="stat-label">Total rows</div>
              </div>
            </div>
            <div class="stat-card" [class.stat-danger]="pushResult()!.failed > 0">
              <div class="stat-icon"><i class="pi pi-times-circle"></i></div>
              <div class="stat-body">
                <div class="stat-value">{{ pushResult()!.failed }}</div>
                <div class="stat-label">Failed</div>
              </div>
            </div>
          </div>
          <div class="push-files">
            @for (f of pushResult()!.files; track f.ref) {
              <div class="push-file" [class.push-ok]="f.status === 'pushed'"
                   [class.push-err]="f.status === 'failed' || f.status === 'skipped'">
                <i class="pi pi-file file-type-icon"></i>
                <div class="push-file-info">
                  <span class="push-file-name">{{ f.name }}</span>
                  <span class="push-file-meta">
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

      <!-- Bottom action bar -->
      <div class="bottom-bar">
        <div class="bottom-info">
          @if (hasFiles()) {
            <strong>{{ totalFiles() }} files selected</strong>
            @if (totalRows()) {
              <span class="bottom-sep">·</span>
              <span>{{ totalRows() }} rows</span>
            }
            <span class="bottom-sep">·</span>
            <span>
              @if (canPush()) {
                Ready to push to database
              } @else if (pushResult()) {
                Push complete
              } @else if (validateResult()) {
                Fix errors before pushing
              } @else {
                Validate before pushing
              }
            </span>
          } @else {
            <span>Upload files and select a configuration to get started</span>
          }
        </div>
        <div class="bottom-actions">
          <p-button label="Validate all" icon="pi pi-check"
                    [outlined]="true" [loading]="validating()"
                    [disabled]="!configRef || !hasFiles()"
                    pTooltip="Check all files against the configuration" tooltipPosition="top"
                    (onClick)="validate()" />
          <p-button label="Push all to database" icon="pi pi-play" severity="danger"
                    [loading]="pushing()" [disabled]="!canPush()"
                    pTooltip="Push all valid files to the database" tooltipPosition="top"
                    (onClick)="push()" />
        </div>
      </div>
    </div>
  `,
  styles: `
    .page { display: grid; gap: 1rem; padding: 1.5rem 2rem; padding-bottom: 5rem; }

    /* ── Stepper ── */
    .stepper { display: flex; align-items: center; gap: 0; padding: .75rem 0; }
    .step { display: flex; align-items: center; gap: .5rem; }
    .step-num { display: flex; align-items: center; justify-content: center;
                width: 1.75rem; height: 1.75rem; border-radius: 50%; flex-shrink: 0;
                font-size: .75rem; font-weight: 700;
                background: var(--surface-hover); color: var(--text-secondary);
                border: 2px solid var(--border); transition: all .2s; }
    .step-num .pi { font-size: .7rem; font-weight: 700; }
    .step.active .step-num { background: var(--primary); color: #fff; border-color: var(--primary); }
    .step.done .step-num { background: var(--success); color: #fff; border-color: var(--success); }
    .step-text { min-width: 0; }
    .step-label { font-size: .8rem; font-weight: 600; }
    .step-desc { font-size: .68rem; color: var(--text-secondary); }
    .step-bar { flex: 1; height: 3px; background: var(--border); margin: 0 .5rem;
                border-radius: 2px; transition: background .3s; }
    .step-bar.filled { background: var(--primary); }

    /* ── Two-column layout ── */
    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;
               align-items: stretch; }
    .two-col .section-card { min-width: 0; display: flex; flex-direction: column; }
    .two-col .section-card .section-header { min-height: 3rem; }
    .two-col .section-card :is(app-workbook-ref, .drop-zone) { flex: 1; min-height: 10rem; }
    .two-col app-workbook-ref { display: flex; flex-direction: column; }
    .two-col app-workbook-ref ::ng-deep .edit-card { flex: 1; display: flex; flex-direction: column; }
    .two-col app-workbook-ref ::ng-deep .edit-body { flex: 1; display: flex; flex-direction: column;
                                                      justify-content: center; }
    .two-col app-workbook-ref ::ng-deep .card { height: 100%; }

    /* ── Section cards ── */
    .section-card { border: 1px solid var(--border); border-radius: var(--radius);
                    background: var(--surface); padding: 1rem 1.25rem; }
    .section-header { display: flex; align-items: center; gap: .75rem; margin-bottom: .75rem; }
    .section-icon { display: flex; align-items: center; justify-content: center;
                    width: 2.25rem; height: 2.25rem; border-radius: 50%;
                    background: var(--surface-hover); flex-shrink: 0; }
    .section-icon .pi { font-size: .9rem; color: var(--text-secondary); }
    .success-icon { background: color-mix(in srgb, var(--success) 15%, transparent); }
    .success-icon .pi { color: var(--success); }
    .section-info { flex: 1; min-width: 0; }
    .section-title { font-size: .9rem; font-weight: 700; }
    .section-desc { font-size: .75rem; color: var(--text-secondary); margin-top: .1rem; }
    .success-text { color: var(--success); }
    .error-text { color: var(--danger); }
    .section-actions { display: flex; gap: .5rem; align-items: center; flex-shrink: 0; }
    .hint { font-size: .68rem; color: var(--text-secondary); }

    /* ── Drop zone ── */
    .drop-zone { display: flex; flex-direction: column; align-items: center;
                 justify-content: center; gap: .35rem;
                 padding: 1.5rem; border: 2px dashed var(--border-strong); border-radius: var(--radius);
                 cursor: pointer; transition: all .2s; text-align: center;
                 color: var(--text-secondary); font-size: .82rem; }
    .drop-zone:hover { border-color: var(--primary); background: var(--primary-soft); }
    .drop-zone.drop-active { border-color: var(--primary); background: var(--primary-soft);
                             border-style: solid; }
    .drop-icon { font-size: 1.5rem; color: var(--primary); }
    .drop-hint { font-size: .7rem; color: var(--text-secondary); }

    /* ── Stats row ── */
    .stats-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: .75rem; }
    .stat-card { display: flex; align-items: center; gap: .75rem; padding: .85rem 1rem;
                 border: 1px solid var(--border); border-radius: var(--radius-sm);
                 background: var(--surface); }
    .stat-icon { display: flex; align-items: center; justify-content: center;
                 width: 2.5rem; height: 2.5rem; border-radius: 50%;
                 background: var(--surface-hover); flex-shrink: 0; }
    .stat-icon .pi { font-size: 1rem; color: var(--text-secondary); }
    .stat-success .stat-icon { background: color-mix(in srgb, var(--success) 15%, transparent); }
    .stat-success .stat-icon .pi { color: var(--success); }
    .stat-success .stat-value { color: var(--success); }
    .stat-danger .stat-icon { background: color-mix(in srgb, var(--danger) 15%, transparent); }
    .stat-danger .stat-icon .pi { color: var(--danger); }
    .stat-danger .stat-value { color: var(--danger); }
    .stat-body { min-width: 0; }
    .stat-value { font-size: 1.25rem; font-weight: 700; line-height: 1.2; }
    .stat-label { font-size: .7rem; color: var(--text-secondary); text-transform: uppercase;
                  letter-spacing: .03em; }

    /* ── Files split layout ── */
    .files-split { display: grid; grid-template-columns: 1fr; gap: 0; }
    .files-split.has-detail { grid-template-columns: 1fr 22rem; gap: 0; }

    /* ── Files table ── */
    .table-controls { display: flex; gap: .5rem; align-items: center; flex-shrink: 0; }
    .search-wrap { min-width: 0; }
    .search-input { font-size: .8rem; width: 12rem; }
    .table-wrap { border: 1px solid var(--border); border-radius: var(--radius-sm);
                  overflow: hidden; }
    .files-table { width: 100%; border-collapse: collapse; font-size: .82rem; }
    .files-table th { background: var(--surface-raised-flat); border-bottom: 1px solid var(--border);
                      font-size: .7rem; font-weight: 600; text-transform: uppercase;
                      letter-spacing: .04em; color: var(--text-secondary);
                      padding: .6rem .75rem; text-align: left; }
    .files-table td { border-bottom: 1px solid var(--border); padding: .4rem .75rem;
                      color: var(--text); vertical-align: middle; }
    .files-table tbody tr:last-child td { border-bottom: none; }
    .files-table tbody tr:hover td { background: var(--surface-hover); }
    .col-num { width: 2.5rem; text-align: center; color: var(--text-secondary); }
    .col-tables, .col-rows { width: 5rem; text-align: right; }
    .col-size { width: 5rem; text-align: right; }
    .col-status { width: 6.5rem; text-align: center; }
    .col-actions { width: 5rem; text-align: center; white-space: nowrap; }
    .file-cell { display: flex; align-items: center; gap: .5rem; min-width: 0; }
    .file-type-icon { color: #217346; font-size: .9rem; flex-shrink: 0; }
    .file-cell-name { font-weight: 500; overflow: hidden; text-overflow: ellipsis;
                      white-space: nowrap; }
    .files-table tbody tr { cursor: pointer; }
    .files-table tbody tr.row-selected td { background: var(--primary-soft);
                                             border-color: color-mix(in srgb, var(--primary) 20%, var(--border)); }

    /* ── File detail panel ── */
    .file-detail { border-left: 1px solid var(--border); padding: .75rem;
                   overflow-y: auto; max-height: 28rem; background: var(--surface); }
    .detail-top { display: flex; align-items: center; justify-content: space-between;
                  margin-bottom: .65rem; gap: .5rem; }
    .detail-title { display: flex; align-items: center; gap: .4rem; font-weight: 600;
                    font-size: .82rem; min-width: 0; overflow: hidden;
                    text-overflow: ellipsis; white-space: nowrap; }
    .detail-summary { display: grid; gap: .35rem; margin-bottom: .75rem; }
    .detail-row { display: grid; grid-template-columns: 6.5rem 1fr; gap: .35rem;
                  font-size: .78rem; align-items: start; }
    .detail-label { color: var(--text-secondary); font-weight: 500; }
    .detail-value { overflow-wrap: anywhere; }
    .detail-warn { color: #d97706; font-weight: 600; }
    .detail-sha { font-size: .65rem; word-break: break-all; }
    .detail-issues-header { font-size: .72rem; font-weight: 700; text-transform: uppercase;
                            letter-spacing: .04em; color: var(--text-secondary);
                            margin-bottom: .35rem; padding-top: .5rem;
                            border-top: 1px solid var(--border); }
    .detail-issues { display: grid; gap: .3rem; }
    .detail-issue { display: flex; gap: .4rem; align-items: flex-start; font-size: .75rem; }
    .detail-issue-body { min-width: 0; }
    .detail-issue-where { display: block; font-size: .68rem; color: var(--text-secondary); }
    .detail-issue-msg { display: block; }
    .detail-empty { display: flex; gap: .4rem; align-items: center; padding: 1rem .5rem;
                    color: var(--text-secondary); font-size: .8rem; }

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
    .status-ok { color: var(--success); }
    .status-err { color: var(--danger); }

    /* ── Push results ── */
    .push-files { display: grid; gap: .25rem; margin-top: .75rem; }
    .push-file { display: flex; gap: .5rem; align-items: center; padding: .5rem .65rem;
                 border: 1px solid var(--border); border-radius: var(--radius-sm); }
    .push-ok { border-left: 3px solid var(--success); }
    .push-err { border-left: 3px solid var(--danger); }
    .push-file-info { flex: 1; min-width: 0; display: grid; gap: .1rem; }
    .push-file-name { font-weight: 600; font-size: .82rem; overflow: hidden;
                      text-overflow: ellipsis; white-space: nowrap; }
    .push-file-meta { font-size: .7rem; color: var(--text-secondary); }

    /* ── Bottom bar ── */
    .bottom-bar { position: fixed; bottom: 0; left: 12.5rem; right: 0;
                  display: flex; align-items: center; justify-content: space-between;
                  padding: .75rem 2rem; background: var(--surface);
                  border-top: 1px solid var(--border); z-index: 20;
                  box-shadow: 0 -2px 8px rgba(0,0,0,.08); }
    .bottom-info { font-size: .82rem; color: var(--text-secondary);
                   display: flex; align-items: center; gap: .35rem; }
    .bottom-info strong { color: var(--text); }
    .bottom-sep { color: var(--border-strong); }
    .bottom-actions { display: flex; gap: .5rem; }

    .muted { color: var(--text-secondary); font-size: .8rem; }

    /* ── tablet ── */
    @media (max-width: 1024px) {
      .page { padding: 1rem; padding-bottom: 5rem; }
      .two-col { grid-template-columns: 1fr; }
      .stepper { flex-wrap: wrap; gap: .25rem; }
      .step-bar { display: none; }
      .section-header { flex-direction: column; gap: .5rem; }
      .section-actions { align-self: flex-start; }
      .stats-row { grid-template-columns: 1fr; }
      .table-controls { width: 100%; }
      .search-input { width: 100%; }
      .bottom-bar { left: 3rem; padding: .5rem 1rem; }
      .bottom-info { font-size: .75rem; }
      .val-issue { grid-template-columns: 4.5rem 9rem 1fr; font-size: .7rem; }
      .files-split.has-detail { grid-template-columns: 1fr; }
      .file-detail { border-left: none; border-top: 1px solid var(--border); max-height: 20rem; }
      .files-table .col-tables, .files-table .col-rows { display: none; }
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
  showValidationDetails = false;
  fileSearch = '';
  selectedFile = signal<string | null>(null);

  // Upload state
  uploadedFiles = signal<File[]>([]);
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
    if (!v || !v.all_valid || v.valid === 0 || this.pushResult()) return false;
    // Only enable after ALL files have been validated (not mid-validation)
    return !this.validating() && v.results.length === this.totalFiles();
  });

  hasFiles = computed(() => this.sourceRefs.length > 0 || this.uploadedFiles().length > 0);

  totalFiles = computed(() => this.uploadedFiles().length + this.sourceRefs.length);

  totalRows = computed(() => {
    const v = this.validateResult();
    if (!v) return 0;
    return v.results.reduce((sum, r) => sum + (r.rows || 0), 0);
  });

  filteredFiles = computed(() => {
    const q = this.fileSearch.toLowerCase().trim();
    if (!q) return this.uploadedFiles();
    return this.uploadedFiles().filter(f => f.name.toLowerCase().includes(q));
  });

  selectFile(name: string) {
    this.selectedFile.set(this.selectedFile() === name ? null : name);
  }

  toggleExpand(ref: string) {
    this.expanded = { ...this.expanded, [ref]: !this.expanded[ref] };
  }

  constructor() {
    this.loadDriveStatus();
  }

  // ── config ──

  replaceConfig() {
    this.configRef = '';
    this.configOk.set(false);
    this.configError.set(null);
    this.validateResult.set(null);
    this.pushResult.set(null);
  }

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

  fileResultFor(name: string): BatchFileResult | null {
    const vr = this.validateResult();
    if (vr) return vr.results.find((r) => r.name === name) ?? null;
    const pr = this.pushResult();
    if (pr) return pr.files.find((r) => r.name === name) ?? null;
    return null;
  }

  fileStatus(name: string): string {
    return this.fileResultFor(name)?.status ?? '';
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
    const combined = [...this.uploadedFiles(), ...files];
    if (combined.length > 20) {
      this.error.set(`Maximum 20 files allowed (you have ${combined.length})`);
      return;
    }
    this.uploadedFiles.set(combined);
    this.validateResult.set(null);
    this.pushResult.set(null);
    this.error.set(null);
  }

  removeUpload(index: number) {
    if (index < 0) return;
    this.uploadedFiles.set(this.uploadedFiles().filter((_, i) => i !== index));
    this.validateResult.set(null);
    this.pushResult.set(null);
  }

  // ── validate ──

  validate() {
    this.validating.set(true);
    this.validateResult.set(null);
    this.pushResult.set(null);
    this.error.set(null);
    this.showValidationDetails = false;

    if (this.uploadedFiles().length) {
      const results: BatchFileResult[] = [];
      const files = [...this.uploadedFiles()];
      const seen: Record<string, string> = {};

      const next = (i: number) => {
        if (i >= files.length) {
          this.validating.set(false);
          return;
        }
        const file = files[i];
        this.api.batchValidateOne(this.configRef, file).subscribe({
          next: (r) => {
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

    if (this.uploadedFiles().length) {
      const fileResults: BatchFileResult[] = [];
      const files = [...this.uploadedFiles()];
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
