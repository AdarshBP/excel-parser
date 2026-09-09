import {
  Component, ElementRef, afterRenderEffect, computed, input, output, signal, viewChild,
} from '@angular/core';
import { ButtonModule } from '@openng/optimus-ui/button';
import { TooltipModule } from '@openng/optimus-ui/tooltip';
import { TableModel } from '../core/models';

interface Box {
  table: TableModel;
  x: number;
  y: number;
  w: number;
  h: number;
  shown: TableModel['columns'];
  hidden: number;
  fileRowY: number | null;
}

interface Edge {
  path: string;
  label: string;
  from: string;
  table: string;
  kind: 'lineage' | 'fk';
}

const BOX_W = 250;
const HEAD_H = 34;
const ROW_H = 20;
const GAP_X = 100;
const GAP_Y = 40;
const EDGE_SPACING = 5;
const LEFT = 24;          // left padding inside the canvas
const TOP = 70;
const MAX_ROWS = 12;
const COLUMN_H = 900;

@Component({
  selector: 'app-er-diagram',
  imports: [ButtonModule, TooltipModule],
  template: `
    <div class="tools">
      <div class="btn-group">
        <p-button icon="pi pi-minus" size="small" [outlined]="true"
                  pTooltip="Zoom out" tooltipPosition="bottom" (onClick)="zoomBy(-0.1)" />
        <span class="pct">{{ (zoom() * 100).toFixed(0) }}%</span>
        <p-button icon="pi pi-plus" size="small" [outlined]="true"
                  pTooltip="Zoom in" tooltipPosition="bottom" (onClick)="zoomBy(0.1)" />
      </div>
      <div class="btn-group">
        <p-button label="Fit" size="small" [outlined]="true"
                  pTooltip="Fit diagram to viewport" tooltipPosition="bottom" (onClick)="fit()" />
        <p-button label="100%" size="small" [outlined]="true"
                  pTooltip="Reset to actual size" tooltipPosition="bottom" (onClick)="zoom.set(1)" />
      </div>
      <p-button size="small" [outlined]="!dragMode()"
                [icon]="dragMode() ? 'pi pi-lock' : 'pi pi-arrows-alt'"
                [label]="dragMode() ? 'Lock' : 'Drag'"
                [pTooltip]="dragMode() ? 'Lock table positions' : 'Enable drag to rearrange tables'"
                tooltipPosition="bottom"
                (onClick)="toggleDrag()" />
      @if (dragMode()) {
        <p-button label="Reset" size="small" [text]="true"
                  pTooltip="Reset all tables to auto-layout" tooltipPosition="bottom"
                  (onClick)="resetPositions()" />
      }
      <span class="hint">{{ autoBoxes().length }} tables
        @if (!dragMode()) { · click to preview }
        @if (dragMode()) { · drag to rearrange }
      </span>
    </div>

    <div class="canvas" [class.draggable]="dragMode()" #canvas
         (mousemove)="onMouseMove($event)" (mouseup)="onMouseUp()">
      <div class="surface"
           [style.width.px]="layout().width * zoom()"
           [style.height.px]="layout().height * zoom()">
        <div class="scaled" [style.transform]="'scale(' + zoom() + ')'"
             [style.width.px]="layout().width" [style.height.px]="layout().height">
          <svg [attr.width]="layout().width" [attr.height]="layout().height">
            @for (e of layout().edges; track e.path) {
              <path [attr.d]="e.path"
                    [class.edge]="e.kind === 'lineage'"
                    [class.edge-fk]="e.kind === 'fk'"
                    [class.edge-on]="e.table === selected() || e.from === selected()" />
            }
          </svg>

          @for (b of boxes(); track b.table.table_name) {
            <div class="box" [class.control]="b.table.control"
                 [class.on]="b.table.table_name === selected()"
                 [class.dragging]="drag?.table === b.table.table_name"
                 [style.left.px]="b.x" [style.top.px]="b.y" [style.width.px]="b.w"
                 (mousedown)="onMouseDown($event, b)"
                 (click)="onClick($event, b)">
              <header [title]="b.table.physical_name + (b.table.control ? ' (control)' :
                               ': ' + b.table.sheet_name + '!' + b.table.data_start_row)">
                <span class="tname">{{ b.table.physical_name }}</span>
                <small>{{ b.table.control ? 'control' :
                          b.table.sheet_name + '!' + b.table.data_start_row }}</small>
              </header>
              @for (c of b.shown; track c.name) {
                <div class="col" [class.lineage]="c.lineage">
                  <span class="cname">
                    {{ c.is_key ? '◆' : c.references ? '↗' : '' }} {{ c.name }}
                  </span>
                  <span class="ctype">{{ c.type }}</span>
                </div>
              }
              @if (b.hidden) {
                <div class="col more">+{{ b.hidden }} more column(s)</div>
              }
            </div>
          }
        </div>
      </div>
    </div>
  `,
  styles: `
    .tools { display: flex; gap: .5rem; align-items: center; padding: .35rem 0; }
    .btn-group { display: flex; gap: 0; align-items: center; }
    .btn-group ::ng-deep .p-button { border-radius: 0; }
    .btn-group ::ng-deep :first-child .p-button { border-radius: var(--radius-sm) 0 0 var(--radius-sm); }
    .btn-group ::ng-deep :last-child .p-button { border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }
    .btn-group .pct { border-radius: 0; }
    .pct { font-size: .75rem; width: 2.5rem; text-align: center; padding: 0 .25rem;
           color: var(--text-secondary); }
    .hint { font-size: .75rem; color: var(--text-secondary); margin-left: .25rem; }
    .canvas { overflow: auto; max-width: 100%; height: 32rem;
              border: 1px solid var(--border); border-radius: var(--radius);
              background: var(--surface-raised); }
    .canvas.draggable { cursor: default; }
    .surface { position: relative; }
    .scaled { position: absolute; top: 0; left: 0; transform-origin: top left; }
    svg { position: absolute; top: 0; left: 0; overflow: visible; }
    .edge { fill: none; stroke: var(--p-primary-color); stroke-width: 1.2; opacity: .2;
            transition: opacity .2s, stroke-width .2s; }
    .edge-fk { fill: none; stroke: #f59e0b; stroke-width: 1.2; opacity: .3;
               stroke-dasharray: 6 3; transition: opacity .2s, stroke-width .2s; }
    .edge.edge-on, .edge-fk.edge-on { opacity: .9; stroke-width: 2; }
    .box { position: absolute;
           background: var(--surface);
           border: 1px solid var(--border);
           border-radius: var(--radius-sm);
           font-size: .7rem; cursor: pointer; overflow: hidden;
           box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
           transition: box-shadow .15s, border-color .15s; }
    .box:hover { border-color: var(--border-strong); }
    .canvas.draggable .box { cursor: grab; }
    .canvas.draggable .box.dragging { cursor: grabbing;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4); z-index: 10; opacity: .92; }
    .box.control { border-color: var(--primary); }
    .box.on { border-color: var(--primary);
              box-shadow: 0 0 0 1px var(--primary), var(--shadow); }
    .box header { display: flex; justify-content: space-between; gap: .5rem;
                  align-items: baseline; height: 32px; padding: 0 .5rem;
                  background: var(--surface-raised); font-weight: 600;
                  line-height: 32px; white-space: nowrap; overflow: hidden;
                  border-bottom: 1px solid var(--border); font-size: .72rem; }
    .box header .tname, .box header small { overflow: hidden; text-overflow: ellipsis; }
    .box header .tname { flex: 1 1 auto; }
    .box header small { flex: 0 1 auto; max-width: 45%; font-weight: 400;
                        color: var(--p-text-muted-color); font-size: .65rem; }
    .col { display: flex; justify-content: space-between; gap: .5rem; height: 19px;
           line-height: 19px; padding: 0 .5rem; white-space: nowrap; }
    .col.lineage { color: var(--p-text-muted-color); }
    .col.more { font-style: italic; color: var(--p-text-muted-color); }
    .cname { overflow: hidden; text-overflow: ellipsis; }
    .ctype { color: var(--p-primary-color); font-size: .65rem; }
  `,
})
export class ErDiagram {
  tables = input<TableModel[]>([]);
  control = input<TableModel[]>([]);
  selected = input<string | null>(null);
  pick = output<TableModel>();
  zoom = signal(0.8);
  dragMode = signal(false);
  /** Per-table position overrides: {tableName: {dx, dy}} from the auto-layout. */
  private offsets = signal<Record<string, { dx: number; dy: number }>>({});
  private canvas = viewChild.required<ElementRef<HTMLElement>>('canvas');
  private fitted = false;

  // Drag state (not reactive -- only used during a drag gesture)
  drag: { table: string; startX: number; startY: number; origDx: number; origDy: number } | null = null;
  private didMove = false;

  constructor() {
    afterRenderEffect(() => {
      if (this.fitted || !this.autoBoxes().length) return;
      this.fitted = true;
      this.fit();
    });
  }

  fit() {
    const box = this.canvas().nativeElement.getBoundingClientRect();
    const { width, height } = this.layout();
    if (!width || !height) return;
    const scale = Math.min(box.width / width, box.height / height);
    this.zoom.set(Math.min(1, Math.max(0.2, Math.floor(scale * 100) / 100)));
  }

  toggleDrag() { this.dragMode.update((v) => !v); }
  resetPositions() { this.offsets.set({}); }

  // ─── drag handlers ───

  onMouseDown(event: MouseEvent, box: Box) {
    if (!this.dragMode()) return;
    event.preventDefault();
    const off = this.offsets()[box.table.table_name] ?? { dx: 0, dy: 0 };
    this.drag = {
      table: box.table.table_name,
      startX: event.clientX,
      startY: event.clientY,
      origDx: off.dx,
      origDy: off.dy,
    };
    this.didMove = false;
  }

  onMouseMove(event: MouseEvent) {
    if (!this.drag) return;
    event.preventDefault();
    const z = this.zoom();
    const dx = this.drag.origDx + (event.clientX - this.drag.startX) / z;
    const dy = this.drag.origDy + (event.clientY - this.drag.startY) / z;
    this.didMove = true;
    this.offsets.update((prev) => ({ ...prev, [this.drag!.table]: { dx, dy } }));
  }

  onMouseUp() {
    this.drag = null;
  }

  onClick(event: MouseEvent, box: Box) {
    // In drag mode, only emit pick if the user clicked without dragging
    if (this.dragMode() && this.didMove) return;
    this.pick.emit(box.table);
  }

  // ─── layout ───

  private blocks = computed(() => this.tables() ?? []);
  private controls = computed(() => this.control() ?? []);

  controlName = computed(() =>
    this.controls().find((t) => t.table_name === 'source_file')?.physical_name ?? 'source_file');

  /** The auto-layout positions (before drag offsets). */
  autoBoxes = computed<Box[]>(() => {
    const controls = this.controls();
    const blocks = this.blocks();
    const boxes: Box[] = [];

    const anchor = controls.find((t) => t.table_name === 'source_file');
    const otherControls = controls.filter((t) => t !== anchor);
    let cy = 0;
    if (anchor) {
      boxes.push(this.box(anchor, LEFT, TOP));
      cy = this.heightOf(anchor) + GAP_Y;
    }
    for (const ctrl of otherControls) {
      boxes.push(this.box(ctrl, LEFT, TOP + cy));
      cy += this.heightOf(ctrl) + GAP_Y;
    }

    let x = LEFT + BOX_W + GAP_X;
    let y = 0;
    for (const table of blocks) {
      if (y > 0 && y + this.heightOf(table) > COLUMN_H) { x += BOX_W + GAP_X; y = 0; }
      boxes.push(this.box(table, x, TOP + y));
      y += this.heightOf(table) + GAP_Y;
    }
    return boxes;
  });

  /** Final box positions = auto-layout + drag offsets. */
  boxes = computed<Box[]>(() => {
    const off = this.offsets();
    return this.autoBoxes().map((b) => {
      const d = off[b.table.table_name];
      return d ? { ...b, x: b.x + d.dx, y: b.y + d.dy } : b;
    });
  });

  private colY(box: Box, colName: string): number | null {
    const idx = box.shown.findIndex((c) => c.name === colName);
    return idx < 0 ? null : HEAD_H + idx * ROW_H + ROW_H / 2;
  }

  private edgePath(fromBox: Box, fromY: number, toBox: Box, toY: number,
                   gutterSlot: number, corridorSlot: number): string {
    const offset = gutterSlot * EDGE_SPACING;
    const absFromY = fromBox.y + fromY;
    const absToY = toBox.y + toY;

    const sameColumn = fromBox.x === toBox.x
      || (fromBox.x < toBox.x + toBox.w && fromBox.x + fromBox.w > toBox.x);
    if (sameColumn) {
      const rightEdge = Math.max(fromBox.x + fromBox.w, toBox.x + toBox.w);
      const vx = rightEdge + 15 + offset;
      return `M ${fromBox.x + fromBox.w} ${absFromY} H ${vx} V ${absToY} H ${toBox.x + toBox.w}`;
    }

    const fromRight = fromBox.x + fromBox.w;
    const toLeft = toBox.x;

    if (fromRight <= toLeft) {
      const gutterMid = fromRight + GAP_X / 2;
      if (toLeft - fromRight < GAP_X + 10) {
        const vx = gutterMid + offset;
        return `M ${fromRight} ${absFromY} H ${vx} V ${absToY} H ${toLeft}`;
      }
      const corridorY = 10 + corridorSlot * EDGE_SPACING;
      const vxFrom = gutterMid + offset;
      const vxTo = toLeft - GAP_X / 2 + offset;
      return `M ${fromRight} ${absFromY} H ${vxFrom} V ${corridorY} `
           + `H ${vxTo} V ${absToY} H ${toLeft}`;
    }
    const fromLeft = fromBox.x;
    const toRight = toBox.x + toBox.w;
    const corridorY = 10 + corridorSlot * EDGE_SPACING;
    const vxFrom = fromLeft - GAP_X / 2 + offset;
    const vxTo = toRight + GAP_X / 2 + offset;
    return `M ${fromLeft} ${absFromY} H ${vxFrom} V ${corridorY} `
         + `H ${vxTo} V ${absToY} H ${toRight}`;
  }

  layout = computed(() => {
    const boxes = this.boxes();
    const boxMap = new Map(boxes.map((b) => [b.table.table_name, b]));
    const edges: Edge[] = [];

    const gutterCount = new Map<number, number>();
    const nextGutterSlot = (fromX: number, toX: number) => {
      const key = Math.round((fromX + toX) / 2);
      const slot = gutterCount.get(key) ?? 0;
      gutterCount.set(key, slot + 1);
      return slot;
    };
    let corridorSlot = 0;

    const target = boxMap.get('source_file');
    if (target && target.fileRowY !== null) {
      for (const box of boxes) {
        if (box === target || box.fileRowY === null) continue;
        const fromRight = target.x + target.w;
        const toLeft = box.x;
        const gSlot = nextGutterSlot(fromRight, toLeft);
        const needsCorridor = (toLeft - fromRight) >= GAP_X + 10;
        const cSlot = needsCorridor ? corridorSlot++ : 0;
        const path = this.edgePath(target, target.fileRowY, box, box.fileRowY, gSlot, cSlot);
        edges.push({ path, label: `${box.table.physical_name}.file_id`,
                     from: 'source_file', table: box.table.table_name, kind: 'lineage' });
      }
    }

    for (const box of boxes) {
      for (const col of box.table.columns) {
        if (!col.references || col.lineage) continue;
        const refTable = boxMap.get(col.references.table);
        if (!refTable || refTable === box) continue;
        const fromY = this.colY(box, col.name);
        const toY = this.colY(refTable, col.references.column);
        if (fromY === null || toY === null) continue;
        const leftBox = box.x <= refTable.x ? box : refTable;
        const rightBox = box.x <= refTable.x ? refTable : box;
        const gSlot = nextGutterSlot(leftBox.x + leftBox.w, rightBox.x);
        const needsCorridor = (rightBox.x - (leftBox.x + leftBox.w)) >= GAP_X + 10
                           || box.x > refTable.x;
        const cSlot = needsCorridor ? corridorSlot++ : 0;
        const path = this.edgePath(box, fromY, refTable, toY, gSlot, cSlot);
        edges.push({ path, label: `${box.table.physical_name}.${col.name}`,
                     from: box.table.table_name, table: refTable.table.table_name, kind: 'fk' });
      }
    }

    const maxGutterSlots = Math.max(0, ...gutterCount.values());
    const extraRight = maxGutterSlots > 0 ? 20 + maxGutterSlots * EDGE_SPACING : 0;
    const minX = Math.min(...boxes.map((b) => b.x), 0);
    const minY = Math.min(...boxes.map((b) => b.y), 0);

    return {
      edges,
      width: Math.max(...boxes.map((b) => b.x + b.w), 0) - Math.min(minX, 0) + 40 + extraRight,
      height: Math.max(...boxes.map((b) => b.y + b.h), 0) - Math.min(minY, 0) + 40,
    };
  });

  zoomBy(step: number) {
    this.zoom.set(Math.min(1.6, Math.max(0.2, Math.round((this.zoom() + step) * 10) / 10)));
  }

  private heightOf(table: TableModel): number {
    const rows = Math.min(table.columns.length, MAX_ROWS);
    const more = table.columns.length > MAX_ROWS ? 1 : 0;
    return HEAD_H + (rows + more) * ROW_H;
  }

  private box(table: TableModel, x: number, y: number): Box {
    const shown = table.columns.slice(0, MAX_ROWS);
    const index = shown.findIndex((c) => c.name === 'file_id');
    return {
      table, x, y,
      w: BOX_W,
      h: this.heightOf(table),
      shown,
      hidden: table.columns.length - shown.length,
      fileRowY: index < 0 ? null : HEAD_H + index * ROW_H + ROW_H / 2,
    };
  }
}
