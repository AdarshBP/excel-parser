import { HttpClient, HttpContext, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import {
  BatchFileResult, BatchPushResult, BatchValidateResult,
  DataFile,
  DriveFile, DriveStatus, Me, Project, PushResult, RenderResult, RunDetail, RunSummary,
  Status, TargetInfo,
} from './models';

/** Everything the browser asks the FastAPI backend for. */
@Injectable({ providedIn: 'root' })
export class Api {
  private http = inject(HttpClient);
  private base = '/api';

  /** The backend already words its errors for a human; show those, not "500".
   *  FastAPI returns three shapes of `detail`:
   *    - string:  our own HTTPException  ("no such project")
   *    - object:  {message, issues?}     (push validation errors)
   *    - array:   [{loc, msg, type}]     (Pydantic 422 validation errors)
   */
  private fail(error: HttpErrorResponse) {
    const detail = error.error?.detail;
    let message: string;
    if (typeof detail === 'string') {
      message = detail;
    } else if (Array.isArray(detail)) {
      // Pydantic validation: show each field that failed
      message = detail
        .map((e: { loc?: string[]; msg?: string }) => {
          const field = (e.loc ?? []).filter((s) => s !== 'body').join('.');
          return field ? `${field}: ${e.msg}` : (e.msg ?? '');
        })
        .join('; ') || `validation failed (${error.status})`;
    } else if (detail?.message) {
      message = detail.message;
    } else if (error.status === 0) {
      message = 'the backend is not reachable';
    } else {
      message = `request failed (${error.status})`;
    }
    return throwError(() => ({ message, issues: detail?.issues ?? [] }));
  }

  private get<T>(url: string): Observable<T> {
    return this.http.get<T>(this.base + url).pipe(catchError((e) => this.fail(e)));
  }

  private send<T>(method: 'post' | 'patch' | 'delete', url: string, body?: unknown): Observable<T> {
    const call =
      method === 'delete'
        ? this.http.delete<T>(this.base + url)
        : this.http[method]<T>(this.base + url, body ?? {}, { context: new HttpContext() });
    return call.pipe(catchError((e) => this.fail(e)));
  }

  login(username: string, password: string) {
    return this.send<Me>('post', '/auth/login', { username, password });
  }
  logout() { return this.send<{ status: string }>('post', '/auth/logout'); }
  me() { return this.get<Me>('/auth/me'); }
  changePassword(current: string, next: string) {
    return this.send<{ status: string }>('post', '/auth/password', { current, new: next });
  }

  projects() { return this.get<Project[]>('/projects'); }
  project(id: string) { return this.get<Project>(`/projects/${id}`); }
  createProject(body: Partial<Project>) { return this.send<Project>('post', '/projects', body); }
  updateProject(id: string, body: Partial<Project>) {
    return this.send<Project>('patch', `/projects/${id}`, body);
  }
  deleteProject(id: string) { return this.send<{ status: string }>('delete', `/projects/${id}`); }
  duplicateProject(id: string) {
    return this.send<Project>('post', `/projects/${id}/duplicate`);
  }

  render(id: string, limit = 20) {
    return this.send<RenderResult>('post', `/projects/${id}/render?limit=${limit}`);
  }
  status(id: string) { return this.get<Status>(`/projects/${id}/status`); }
  target(id: string) { return this.get<TargetInfo>(`/projects/${id}/target`); }
  push(id: string, skipAudit = false) {
    const q = skipAudit ? '?skip_audit=true' : '';
    return this.send<PushResult>('post', `/projects/${id}/push${q}`);
  }
  pushSchema(id: string) {
    return this.send<{ target: any; target_label: string; ddl: string }>(
      'post', `/projects/${id}/push-schema`);
  }
  ddl(id: string, dialect?: string) {
    const url = `${this.base}/projects/${id}/ddl` + (dialect ? `?dialect=${dialect}` : '');
    return this.http.get(url, { responseType: 'text' }).pipe(catchError((e) => this.fail(e)));
  }

  runs(projectId?: string) {
    return this.get<RunSummary[]>('/runs' + (projectId ? `?project_id=${projectId}` : ''));
  }
  run(id: string) { return this.get<RunDetail>(`/runs/${id}`); }

  dataFiles(search = '') {
    const q = search ? `?search=${encodeURIComponent(search)}` : '';
    return this.get<DataFile[]>(`/data-viewer/files${q}`);
  }
  dataFileDetail(fileId: string) {
    return this.get<DataFile>(`/data-viewer/files/${fileId}`);
  }
  rollbackFile(fileId: string) {
    return this.send<{ rolled_back: boolean; file_id: string; rows_deleted: Record<string, number>;
                       total_deleted: number; source_name: string }>(
      'post', `/data-viewer/files/${fileId}/rollback`);
  }

  autoConfig(ref: string, tableName?: string, database?: string, dbSchema?: string) {
    return this.send<{ ok: boolean; config_ref: string; name: string }>(
      'post', '/auto-config', { ref, table_name: tableName, database, db_schema: dbSchema });
  }

  exportCsvUrl(projectId: string, table: string) {
    return `${this.base}/projects/${projectId}/export-csv?table=${encodeURIComponent(table)}`;
  }



  uploadWorkbook(file: File) {
    const fd = new FormData();
    fd.append('file', file);
    return this.http.post<{ ref: string; name: string; size: number; sha256: string }>(
      this.base + '/upload-workbook', fd).pipe(catchError((e) => this.fail(e)));
  }

  testRef(ref: string, role: 'source' | 'config' = 'source') {
    return this.send<{ ok: boolean; name: string; sheets: string[]; size: number; role: string }>(
      'post', '/test-ref', { ref, role });
  }

  batchValidate(config_ref: string, source_refs: string[]) {
    return this.send<BatchValidateResult>('post', '/batch/validate',
      { config_ref, source_refs });
  }
  batchPush(config_ref: string, source_refs: string[]) {
    return this.send<BatchPushResult>('post', '/batch/push',
      { config_ref, source_refs });
  }

  batchValidateUpload(configRef: string, files: File[]) {
    const fd = new FormData();
    fd.append('config_ref', configRef);
    files.forEach(f => fd.append('files', f));
    return this.http.post<BatchValidateResult>(this.base + '/batch/validate-upload', fd)
      .pipe(catchError((e) => this.fail(e)));
  }
  batchPushUpload(configRef: string, files: File[]) {
    const fd = new FormData();
    fd.append('config_ref', configRef);
    files.forEach(f => fd.append('files', f));
    return this.http.post<BatchPushResult>(this.base + '/batch/push-upload', fd)
      .pipe(catchError((e) => this.fail(e)));
  }

  /** Validate a single uploaded file. */
  batchValidateOne(configRef: string, file: File) {
    const fd = new FormData();
    fd.append('config_ref', configRef);
    fd.append('file', file);
    return this.http.post<BatchFileResult>(this.base + '/batch/validate-one', fd)
      .pipe(catchError((e) => this.fail(e)));
  }
  /** Push a single uploaded file. */
  batchPushOne(configRef: string, file: File) {
    const fd = new FormData();
    fd.append('config_ref', configRef);
    fd.append('file', file);
    return this.http.post<BatchFileResult>(this.base + '/batch/push-one', fd)
      .pipe(catchError((e) => this.fail(e)));
  }

  drivePicker() {
    return this.get<{ api_key: string; access_token: string; client_id: string }>('/drive/picker');
  }
  driveStatus() { return this.get<DriveStatus>('/drive/status'); }
  driveConnect() { return this.send<{ url: string }>('post', '/drive/connect'); }
  driveDisconnect() { return this.send<{ status: string }>('post', '/drive/disconnect'); }
  driveFiles(search = '', folder = '') {
    const query = new URLSearchParams();
    if (search) query.set('search', search);
    if (folder) query.set('folder', folder);
    const suffix = query.toString();
    return this.get<{ files: DriveFile[] }>('/drive/files' + (suffix ? `?${suffix}` : ''));
  }
  driveFile(id: string) { return this.get<DriveFile>(`/drive/files/${id}`); }
}
