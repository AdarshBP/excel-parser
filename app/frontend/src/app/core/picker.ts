/**
 * Google Picker — opens the native Google Drive file chooser.
 *
 * Usage:
 *   const picker = inject(GooglePicker);
 *   picker.pick().subscribe(file => ...);         // single select
 *   picker.pickMany().subscribe(files => ...);    // multi select
 */
import { Injectable, inject } from '@angular/core';
import { Observable, from, switchMap } from 'rxjs';
import { Api } from './api';

declare const google: any;
declare const gapi: any;

const PICKER_SCRIPT = 'https://apis.google.com/js/api.js';

export interface PickedFile {
  id: string;
  name: string;
  mimeType: string;
  ref: string;
}

@Injectable({ providedIn: 'root' })
export class GooglePicker {
  private api = inject(Api);
  private loaded = false;

  private loadScript(): Promise<void> {
    if (this.loaded) return Promise.resolve();
    return new Promise((resolve, reject) => {
      if (document.querySelector(`script[src="${PICKER_SCRIPT}"]`)) {
        this.loaded = true;
        resolve();
        return;
      }
      const script = document.createElement('script');
      script.src = PICKER_SCRIPT;
      script.onload = () => {
        gapi.load('picker', () => { this.loaded = true; resolve(); });
      };
      script.onerror = () => reject(new Error('failed to load Google Picker'));
      document.head.appendChild(script);
    });
  }

  /** Open the native Drive picker — single file. */
  pick(title = 'Select a workbook'): Observable<PickedFile> {
    return this.api.drivePicker().pipe(
      switchMap((creds) => from(this.openPicker(creds, false, title))),
    ) as Observable<PickedFile>;
  }

  /** Open the native Drive picker — multi-select. */
  pickMany(title = 'Select source files (Ctrl/Cmd for multiple)'): Observable<PickedFile[]> {
    return this.api.drivePicker().pipe(
      switchMap((creds) => from(this.openPicker(creds, true, title))),
    ) as Observable<PickedFile[]>;
  }

  private async openPicker(
    creds: { api_key: string; access_token: string; client_id: string },
    multi: boolean,
    title: string,
  ): Promise<PickedFile | PickedFile[]> {
    await this.loadScript();
    return new Promise((resolve, reject) => {
      const sheetsView = new google.picker.DocsView(google.picker.ViewId.SPREADSHEETS)
        .setIncludeFolders(true)
        .setSelectFolderEnabled(false);
      const xlsxView = new google.picker.DocsView()
        .setIncludeFolders(true)
        .setSelectFolderEnabled(false)
        .setMimeTypes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');

      const builder = new google.picker.PickerBuilder()
        .addView(sheetsView)
        .addView(xlsxView)
        .setOAuthToken(creds.access_token)
        .setDeveloperKey(creds.api_key)
        .setAppId(creds.client_id.split('-')[0])
        .setTitle(title)
        .setCallback((data: any) => {
          if (data.action === google.picker.Action.PICKED) {
            const files = data.docs.map((doc: any) => ({
              id: doc.id,
              name: doc.name,
              mimeType: doc.mimeType,
              ref: `drive:${doc.id}`,
            }));
            resolve(multi ? files : files[0]);
          } else if (data.action === google.picker.Action.CANCEL) {
            reject(new Error('cancelled'));
          }
        });

      if (multi) {
        builder.enableFeature(google.picker.Feature.MULTISELECT_ENABLED);
      }

      builder.build().setVisible(true);
    });
  }
}
