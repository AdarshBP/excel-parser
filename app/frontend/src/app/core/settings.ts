import { Injectable, signal } from '@angular/core';

const STORAGE_KEY = 'ep_settings';

export interface AppSettings {
  pollInterval: number;   // seconds
  keyboardShortcuts: boolean;
  // Feature flags
  auditLog: boolean;
  exportCsv: boolean;
  loadTracking: boolean;
  dataViewer: boolean;
}

const DEFAULTS: AppSettings = {
  pollInterval: 10,
  keyboardShortcuts: false,
  auditLog: true,
  exportCsv: true,
  loadTracking: true,
  dataViewer: true,
};

@Injectable({ providedIn: 'root' })
export class Settings {
  private current = signal<AppSettings>(this.load());

  get() { return this.current(); }
  pollInterval() { return this.current().pollInterval; }
  pollMs() { return this.current().pollInterval * 1000; }
  keyboardShortcuts() { return this.current().keyboardShortcuts; }
  auditLog() { return this.current().auditLog; }
  exportCsv() { return this.current().exportCsv; }
  loadTracking() { return this.current().loadTracking; }
  dataViewer() { return this.current().dataViewer; }

  update(partial: Partial<AppSettings>) {
    const merged = { ...this.current(), ...partial };
    this.current.set(merged);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
  }

  private load(): AppSettings {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) return { ...DEFAULTS, ...JSON.parse(raw) };
    } catch {}
    return { ...DEFAULTS };
  }
}
