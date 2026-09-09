import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ButtonModule } from '@openng/optimus-ui/button';
import { CardModule } from '@openng/optimus-ui/card';
import { MessageModule } from '@openng/optimus-ui/message';

/** Where Google's consent screen lands after the backend stored the token.
 *  It opens in the tab the "Connect Google Drive" button opened, so the only
 *  thing left to do here is say what happened and let the tab be closed. */
@Component({
  selector: 'app-drive-connected',
  imports: [ButtonModule, CardModule, MessageModule],
  template: `
    <div class="page">
      <p-card>
        <ng-template #title>Google Drive</ng-template>
        @if (ok()) {
          <p-message severity="success" text="Connected. Go back to the other tab and
            choose a workbook from Drive." />
        } @else {
          <p-message severity="error" text="The sign-in did not complete. Close this tab
            and press Connect Google Drive again." />
        }
        <p><p-button label="Close this tab" size="small" (onClick)="close()" /></p>
      </p-card>
    </div>
  `,
  styles: `.page { padding: 1.25rem; } p { margin-top: 1rem; }`,
})
export class DriveConnected {
  ok = signal(inject(ActivatedRoute).snapshot.queryParamMap.get('connected') === '1');

  constructor() {
    // Notify the original tab that Drive connected so it refreshes status
    if (this.ok()) {
      localStorage.setItem('drive-connected', Date.now().toString());
    }
  }

  close() {
    window.close();
  }
}
