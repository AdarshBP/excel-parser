export interface Me {
  username: string;
  must_change_password: boolean;
}

export interface TargetInfo {
  target: string;
  host: string;
  database: string;
  db_schema: string;
  prefix: string;
  id_type: 'integer' | 'uuid';
  credentials: string;
}

export interface Project {
  project_id: string;
  name: string;
  source_ref: string;
  config_ref: string;
  source_kind: SourceKind;
  config_kind: SourceKind;
  target: { target?: string; database?: string; prefix?: string; id_type?: 'integer' | 'uuid' };
  auto_render: boolean;
  created_at: string;
  updated_at: string;
  last_render_at: string | null;
  last_push_at: string | null;
  render?: RenderResult | null;
}

/** How a workbook is reached: a path in the project, a shared link, or Drive. */
export type SourceKind = 'local' | 'sheet' | 'drive';

export interface DriveStatus {
  configured: boolean;
  connected: boolean;
  email: string | null;
  connected_at: string | null;
  redirect_uri: string;
}

export interface DriveFile {
  id: string;
  name: string;
  mime_type: string;
  kind: 'folder' | 'sheet' | 'xlsx';
  modified_at: string | null;
  size: string | null;
  link: string | null;
  owner: string;
  ref: string;
}

export interface ColumnModel {
  name: string;
  type: string;
  nullable: boolean;
  is_key: boolean;
  lineage: boolean;
  source: string | null;
  references: { table: string; column: string } | null;
  source_header?: string | null;
  null_default?: string | null;
}

export interface TableModel {
  table_name: string;
  physical_name: string;
  sheet_name: string;
  layout: string;
  header_row: number | null;
  data_start_row: number | null;
  data_end_row: number | null;
  notes: string | null;
  control?: boolean;
  columns: ColumnModel[];
}

export interface Issue {
  severity: 'error' | 'warning';
  where: string;
  message: string;
}

export interface PreviewCell {
  column: string;
  cell: string;
  raw: string | null;
  value: string | null;
}

export interface TablePreview {
  sheet_name: string;
  columns: string[];
  rows: { source_row_num: number; cells: PreviewCell[] }[];
  skipped: { row: number; columns: string[] }[];
  bad_cells: { cell: string; column: string; message: string }[];
  loadable_rows: number;
  range: [number, number] | null;
  missing_sheet: boolean;
}

export interface RenderResult {
  tables: TableModel[];
  control_tables: TableModel[];
  issues: Issue[];
  previews: Record<string, TablePreview>;
  target: TargetInfo;
  source: { name: string; ref: string };
  config: { name: string; ref: string };
  can_push: boolean;
  rendered_at: string;
  preview_limit: number;
}

export interface Status {
  source_changed: boolean;
  config_changed: boolean;
  never_rendered: boolean;
  source: { name: string; sha256: string; size: number };
  config: { name: string; sha256: string; size: number };
  last_render_at: string | null;
  last_push_at: string | null;
  auto_render: boolean;
  checked_at: string;
}

export interface PushResult {
  run_id: string;
  file_id: number | string;
  row_total: number;
  rows_per_table: Record<string, number>;
  skipped_rows: string[];
  bad_cells: string[];
  target_label: string;
  target: TargetInfo;
  log: string[];
}

export interface RunSummary {
  run_id: string;
  project_id: string;
  project_name: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  target: string | null;
  database: string | null;
  db_schema: string | null;
  prefix: string | null;
  row_total: number | null;
  file_id: number | string | null;
  source_name: string | null;
  config_name: string | null;
}

export interface WorkbookDirItem {
  name: string;
  path: string;
  kind: 'folder' | 'file';
  size: number | null;
}

export interface WorkbookDirResult {
  root: string | null;
  folder: string;
  items: WorkbookDirItem[];
}

export interface BatchFileResult {
  ref: string;
  name: string;
  status: 'valid' | 'error' | 'pushed' | 'failed' | 'skipped';
  message: string;
  issues?: Issue[];
  rows: number;
  tables?: number;
  bad_cells?: number;
  skipped?: number;
  sha256?: string;
  file_id?: number | string;
  per_table?: Record<string, number>;
}

export interface BatchValidateResult {
  results: BatchFileResult[];
  all_valid: boolean;
  total: number;
  valid: number;
  errors: number;
}

export interface BatchPushResult {
  batch_id: string;
  files: BatchFileResult[];
  total_rows: number;
  pushed: number;
  failed: number;
  total: number;
  target: { target: string; database: string; db_schema: string; prefix: string };
}

export interface RunDetail extends RunSummary {
  source_ref: string;
  config_ref: string;
  source_sha256: string | null;
  config_sha256: string | null;
  log_text: string | null;
  rows_per_table: Record<string, number>;
  issues: Issue[];
}
