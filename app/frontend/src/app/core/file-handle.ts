/**
 * FileHandle service — wraps the File System Access API so other components
 * can pick local files, hold persistent handles, and re-read them later.
 *
 * Handles are persisted in IndexedDB so they survive page reloads.
 * (FileSystemFileHandle is structured-cloneable.)
 *
 * Chrome 86+, Edge 86+, Opera 72+.  Not supported in Firefox or Safari.
 * Callers must check `isSupported()` before showing any browser-pick UI.
 */
import { Injectable } from '@angular/core';
import { Observable, from, throwError } from 'rxjs';

/** Augment Window with the File System Access API types (not in TS lib yet). */
interface FSAWindow {
  showOpenFilePicker?: (opts?: {
    multiple?: boolean;
    types?: { description?: string; accept: Record<string, string[]> }[];
  }) => Promise<FileSystemFileHandle[]>;
}

export interface PickedFile {
  handle: FileSystemFileHandle;
  file: File;
  name: string;
}

/** Turn a raw browser File System Access error into a user-friendly message. */
export function fsaErrorMessage(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err);
  if (msg.includes('not allowed by the user agent') || msg.includes('NotAllowedError')) {
    return 'Your browser or device does not support local file sync. '
      + 'Please use a Chromium-based desktop browser (Google Chrome, Microsoft Edge, or Brave) '
      + 'to enable this feature.';
  }
  return msg;
}

const DB_NAME = 'ep_file_handles';
const DB_VERSION = 1;
const STORE_NAME = 'handles';

/** What we store per key in IndexedDB. */
interface IdbEntry {
  handle: FileSystemFileHandle;
  lastMod?: number;
  originalName?: string;
}

@Injectable({ providedIn: 'root' })
export class FileHandleService {
  /** handle storage: key = `${projectId}:${role}` */
  private handles = new Map<string, FileSystemFileHandle>();

  /** Last known lastModified timestamp per key, for change detection. */
  private lastModified = new Map<string, number>();

  /** Original filename the user picked (survives refresh via IDB). */
  private originalNames = new Map<string, string>();

  /** IndexedDB instance, opened lazily. */
  private dbPromise: Promise<IDBDatabase> | null = null;

  /** Whether initial load from IndexedDB has completed. */
  private loaded = false;
  private loadPromise: Promise<void>;

  constructor() {
    this.loadPromise = this.loadFromIdb();
  }

  /** Whether the File System Access API is available in this browser. */
  isSupported(): boolean {
    return typeof (window as unknown as FSAWindow).showOpenFilePicker === 'function';
  }

  /** Open the OS file picker for a single .xlsx / .csv file. */
  pick(): Observable<PickedFile> {
    const w = window as unknown as FSAWindow;
    if (!w.showOpenFilePicker) {
      return throwError(() => new Error(
        'Your browser does not support the File System Access API. '
        + 'Please use Google Chrome, Microsoft Edge, or another Chromium-based browser '
        + 'to select files directly from your computer.'));
    }
    return from(
      w.showOpenFilePicker({
        multiple: false,
        types: [
          {
            description: 'Excel workbooks and CSV files',
            accept: {
              'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
              'application/vnd.ms-excel.sheet.macroEnabled.12': ['.xlsm'],
              'text/csv': ['.csv'],
            },
          },
        ],
      }).then(async (handles) => {
        const handle = handles[0];
        const file = await handle.getFile();
        return { handle, file, name: file.name } as PickedFile;
      }),
    );
  }

  /** Store a handle for later re-reads. Key format: `projectId:role`. */
  store(key: string, handle: FileSystemFileHandle, lastMod?: number, name?: string): void {
    this.handles.set(key, handle);
    if (lastMod !== undefined) this.lastModified.set(key, lastMod);
    if (name) this.originalNames.set(key, name);
    this.persistToIdb(key, handle, lastMod, name);
  }

  /** Whether we hold a handle for this key. */
  has(key: string): boolean {
    return this.handles.has(key);
  }

  /** The original filename for this key (survives refresh). */
  getName(key: string): string {
    return this.originalNames.get(key) ?? '';
  }

  /** Wait for IndexedDB load to finish, then check. */
  async ensureLoaded(): Promise<void> {
    if (!this.loaded) await this.loadPromise;
  }

  /** Re-read the file from a stored handle.  Returns null if no handle. */
  async reread(key: string): Promise<PickedFile | null> {
    await this.ensureLoaded();
    const handle = this.handles.get(key);
    if (!handle) return null;
    try {
      const file = await handle.getFile();
      return { handle, file, name: file.name };
    } catch {
      // Permission revoked or handle stale after reload
      this.remove(key);
      return null;
    }
  }

  /**
   * Check whether the file on disk changed since we last saw it.
   * Compares `File.lastModified` to the value stored at `store()` or
   * the last `markSeen()` call.
   */
  async hasChanged(key: string): Promise<boolean> {
    await this.ensureLoaded();
    const handle = this.handles.get(key);
    if (!handle) return false;
    try {
      const file = await handle.getFile();
      const prev = this.lastModified.get(key);
      return prev !== undefined && file.lastModified !== prev;
    } catch {
      // Permission revoked — can't check, treat as no change
      return false;
    }
  }

  /** Update the "last seen" timestamp so subsequent `hasChanged` compares against now. */
  markSeen(key: string, lastMod: number): void {
    this.lastModified.set(key, lastMod);
    const handle = this.handles.get(key);
    const name = this.originalNames.get(key);
    if (handle) this.persistToIdb(key, handle, lastMod, name);
  }

  /** Drop a stored handle (e.g. when the user switches to a different ref kind). */
  remove(key: string): void {
    this.handles.delete(key);
    this.lastModified.delete(key);
    this.originalNames.delete(key);
    this.removeFromIdb(key);
  }

  /** Move a handle from one key to another (e.g. draft → project after creation). */
  move(oldKey: string, newKey: string): void {
    const handle = this.handles.get(oldKey);
    if (!handle) return;
    const lastMod = this.lastModified.get(oldKey);
    const name = this.originalNames.get(oldKey);
    this.handles.set(newKey, handle);
    if (lastMod !== undefined) this.lastModified.set(newKey, lastMod);
    if (name) this.originalNames.set(newKey, name);
    this.handles.delete(oldKey);
    this.lastModified.delete(oldKey);
    this.originalNames.delete(oldKey);
    this.persistToIdb(newKey, handle, lastMod, name);
    this.removeFromIdb(oldKey);
  }

  // ── IndexedDB persistence ──────────────────────────────────────

  private openDb(): Promise<IDBDatabase> {
    if (this.dbPromise) return this.dbPromise;
    this.dbPromise = new Promise<IDBDatabase>((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME);
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return this.dbPromise;
  }

  private async loadFromIdb(): Promise<void> {
    try {
      const db = await this.openDb();
      const tx = db.transaction(STORE_NAME, 'readonly');
      const store = tx.objectStore(STORE_NAME);
      const req = store.getAll();
      const keyReq = store.getAllKeys();
      await new Promise<void>((resolve, reject) => {
        tx.oncomplete = () => {
          const keys = keyReq.result as string[];
          const values = req.result as IdbEntry[];
          for (let i = 0; i < keys.length; i++) {
            const key = keys[i];
            const entry = values[i];
            if (entry?.handle) {
              this.handles.set(key, entry.handle);
              if (entry.lastMod !== undefined) this.lastModified.set(key, entry.lastMod);
              if (entry.originalName) this.originalNames.set(key, entry.originalName);
            }
          }
          this.loaded = true;
          resolve();
        };
        tx.onerror = () => reject(tx.error);
      });
    } catch {
      // IndexedDB unavailable — in-memory only
      this.loaded = true;
    }
  }

  private async persistToIdb(key: string, handle: FileSystemFileHandle,
                              lastMod?: number, originalName?: string): Promise<void> {
    try {
      const db = await this.openDb();
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const entry: IdbEntry = { handle, lastMod, originalName };
      const req = tx.objectStore(STORE_NAME).put(entry, key);
      await new Promise<void>((resolve, reject) => {
        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
      });
    } catch {
      // FileSystemFileHandle not cloneable in this browser — in-memory only.
      // The handle will work for this session but won't survive refresh.
    }
  }

  private async removeFromIdb(key: string): Promise<void> {
    try {
      const db = await this.openDb();
      const tx = db.transaction(STORE_NAME, 'readwrite');
      tx.objectStore(STORE_NAME).delete(key);
    } catch { /* best-effort */ }
  }
}
