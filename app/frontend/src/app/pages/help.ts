import { Component } from '@angular/core';
import { CardModule } from '@openng/optimus-ui/card';

@Component({
  selector: 'app-help',
  imports: [CardModule],
  template: `
    <div class="page">
      <h2>Help</h2>

      <p-card>
        <ng-template #title>Keyboard shortcuts</ng-template>
        <p class="hint">Shortcuts work on the project page. Use
          <kbd>{{ mod }}</kbd> as the modifier key.</p>

        <div class="section-label">Project actions</div>
        <div class="shortcuts">
          <div class="row">
            <kbd>{{ mod }} + S</kbd>
            <div>
              <div class="action">Save</div>
              <div class="desc">Save project name, workbook references, and settings</div>
            </div>
          </div>
          <div class="row">
            <kbd>{{ mod }} + R</kbd>
            <div>
              <div class="action">Render</div>
              <div class="desc">Save and re-process both workbooks: schema, preview rows, validation</div>
            </div>
          </div>
          <div class="row">
            <kbd>{{ mod }} + Enter</kbd>
            <div>
              <div class="action">Push</div>
              <div class="desc">Open the push dialog (only when validation passes)</div>
            </div>
          </div>
          <div class="row">
            <kbd>{{ mod }} + D</kbd>
            <div>
              <div class="action">DDL</div>
              <div class="desc">View the generated CREATE TABLE statements</div>
            </div>
          </div>
        </div>

        <div class="section-label">Navigation</div>
        <div class="shortcuts">
          <div class="row">
            <kbd>{{ mod }} + /</kbd>
            <div>
              <div class="action">Help</div>
              <div class="desc">Toggle the keyboard shortcuts dialog on the project page</div>
            </div>
          </div>
          <div class="row">
            <kbd>Esc</kbd>
            <div>
              <div class="action">Close dialog</div>
              <div class="desc">Close any open dialog (push, DDL, help, browse)</div>
            </div>
          </div>
        </div>
      </p-card>

      <p-card>
        <ng-template #title>Sync status indicator</ng-template>
        <div class="shortcuts">
          <div class="row">
            <span class="dot dot-ok"></span>
            <div>
              <div class="action">Synced</div>
              <div class="desc">The workbooks haven't changed since the last render.
                Checked every few seconds (configurable in Settings).</div>
            </div>
          </div>
          <div class="row">
            <span class="dot dot-stale"></span>
            <div>
              <div class="action">Changed</div>
              <div class="desc">A workbook was modified since the last render. Click Render
                (or enable auto-render) to pick up the changes.</div>
            </div>
          </div>
          <div class="row">
            <span class="dot dot-err"></span>
            <div>
              <div class="action">Sync failed</div>
              <div class="desc">The server couldn't check the workbooks: network issue,
                Drive token expired, or file not accessible.</div>
            </div>
          </div>
        </div>
      </p-card>

      <p-card>
        <ng-template #title>Workbook sources</ng-template>
        <div class="shortcuts">
          <div class="row">
            <kbd class="icon">📁</kbd>
            <div>
              <div class="action">Local file</div>
              <div class="desc">A path on the server inside the configured WORKBOOK_DIR.
                Use "Browse" to pick from the directory tree.</div>
            </div>
          </div>
          <div class="row">
            <kbd class="icon">🔗</kbd>
            <div>
              <div class="action">Google Sheets link</div>
              <div class="desc">A shareable URL to a Google Sheet. Must be shared as
                "Anyone with the link: Viewer".</div>
            </div>
          </div>
          <div class="row">
            <kbd class="icon">☁️</kbd>
            <div>
              <div class="action">Google Drive</div>
              <div class="desc">Pick files from your Drive using Google's native picker.
                Requires signing in with your Google account. Only read-only access.</div>
            </div>
          </div>
        </div>
      </p-card>
    </div>
  `,
  styles: `
    .page { display: grid; gap: 1rem; padding: 1.25rem; max-width: 44rem; margin: 0 auto; }
    h2 { margin: 0; font-size: 1.1rem; }
    .hint { font-size: .78rem; color: var(--text-secondary); margin: 0 0 .75rem; }
    .hint kbd { font-size: .72rem; padding: .15rem .35rem; background: var(--surface-hover);
                border: 1px solid var(--border); border-radius: var(--radius-sm); }

    .section-label { font-size: .7rem; text-transform: uppercase; letter-spacing: .06em;
                     color: var(--text-secondary); margin: 1rem 0 .3rem; font-weight: 600; }
    .section-label:first-of-type { margin-top: 0; }

    .shortcuts { display: grid; gap: .25rem; }
    .row { display: flex; gap: 1rem; align-items: start;
           padding: .45rem .5rem; border-radius: var(--radius-sm); }
    .row:hover { background: var(--surface-hover); }
    .row kbd { min-width: 7.5rem; text-align: center; padding: .25rem .5rem;
               background: var(--surface-hover); border: 1px solid var(--border);
               border-radius: var(--radius-sm); font-size: .75rem;
               font-family: inherit; white-space: nowrap; flex-shrink: 0; }
    .row kbd.icon { border: none; background: none; font-size: 1.1rem; min-width: 2.5rem; }
    .action { font-weight: 600; font-size: .82rem; }
    .desc { font-size: .72rem; color: var(--text-secondary); line-height: 1.45; margin-top: .1rem; }

    .dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
           margin: .35rem 2.5rem .35rem 1rem; }
    .dot-ok { background: var(--success); }
    .dot-stale { background: #f59e0b; }
    .dot-err { background: var(--danger); }
  `,
})
export class HelpPage {
  isMac = navigator.platform.toUpperCase().includes('MAC');
  mod = this.isMac ? '⌘' : 'Ctrl';
}
