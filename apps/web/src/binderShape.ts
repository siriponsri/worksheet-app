/* =========================================================================
   The shape of the files on the shelf
   -------------------------------------------------------------------------
   The shelf shipped with one silhouette — the A4 lever arch file that is
   actually on the ANF3 shelf. That is the honest default and stays the
   default. But a shelf of fifteen identical spines is monotonous to look at
   every day, and the formats below are all real office filing formats, so the
   reader can pick the one they would rather see.

   The differences are physical, not decorative. A lever arch file has a wide
   spine and a finger ring because the lever mechanism needs the depth; a ring
   binder is narrower and has no lever, so no ring; a box file is squared off
   and closes with a clasp rather than a mechanism; an expanding file has
   pleated sides and an elastic; a document wallet is a flap with no mechanism
   at all. Each shape below changes width, furniture and proportion together,
   the way the real object does.

   Sources for the format differences are listed in docs/CABINET_WORKFLOW_MATRIX.md.

   Like the colours, the choice is per browser and never leaves it: it changes
   how the shelf looks, never what a binder means. The building hue, the spine
   label and the record behind it are identical whichever shape is chosen.
   ========================================================================= */

export type BinderShapeId =
  | 'lever-arch' | 'ring-binder' | 'slim-binder' | 'box-file' | 'expanding' | 'wallet';

export type BinderShape = {
  id: BinderShapeId;
  /** Shown in the picker. */
  label: string;
  /** One line on what the real object is. */
  detail: string;
  /** Spine width in scene units (1 unit ≈ 10 cm). */
  width: number;
  /** A lever mechanism needs a finger ring; a wallet does not. */
  ring: boolean;
  /** Square shoulders (box file) rather than the softened board edge. */
  squared: boolean;
  /** Extra furniture drawn on the front face. */
  furniture: 'none' | 'clasp' | 'pocket' | 'elastic';
  /** Pleated sides, as on a concertina file. */
  pleats: boolean;
};

export const BINDER_SHAPES: BinderShape[] = [
  {
    id: 'lever-arch', label: 'Lever arch file', width: 0.70, ring: true, squared: false,
    furniture: 'none', pleats: false,
    detail: 'The file actually on the ANF3 shelf — wide spine, lever mechanism, finger ring.'
  },
  {
    id: 'ring-binder', label: 'Ring binder', width: 0.52, ring: false, squared: false,
    furniture: 'pocket', pleats: false,
    detail: 'Narrower, no lever, and a clear spine pocket for a slip-in label.'
  },
  {
    id: 'slim-binder', label: 'Slim binder', width: 0.34, ring: false, squared: false,
    furniture: 'pocket', pleats: false,
    detail: 'A two-ring binder for a thin run of pages. More files fit on a shelf.'
  },
  {
    id: 'box-file', label: 'Box file', width: 0.78, ring: true, squared: true,
    furniture: 'clasp', pleats: false,
    detail: 'Squared shoulders, a spring clip inside, and a clasp on the front edge. Pages need no holes.'
  },
  {
    id: 'expanding', label: 'Expanding file', width: 0.62, ring: false, squared: true,
    furniture: 'elastic', pleats: true,
    detail: 'Concertina sides that open as it fills, closed with an elastic.'
  },
  {
    id: 'wallet', label: 'Document wallet', width: 0.22, ring: false, squared: false,
    furniture: 'none', pleats: false,
    detail: 'A flat card wallet with a flap and no mechanism. The thinnest thing on a shelf.'
  }
];

export const DEFAULT_SHAPE: BinderShapeId = 'lever-arch';
const STORAGE_KEY = 'anf3.binder-shape.v1';
export const SHAPE_EVENT = 'anf3:shape';

export function shapeById(id: BinderShapeId): BinderShape {
  return BINDER_SHAPES.find((shape) => shape.id === id) || BINDER_SHAPES[0];
}

/** The shape in force in this browser. Falls back to the real file. */
export function readShape(): BinderShapeId {
  try {
    const raw = localStorage.getItem(STORAGE_KEY) as BinderShapeId | null;
    return raw && BINDER_SHAPES.some((shape) => shape.id === raw) ? raw : DEFAULT_SHAPE;
  } catch { return DEFAULT_SHAPE; }
}

export function setShape(id: BinderShapeId) {
  try {
    if (id === DEFAULT_SHAPE) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, id);
  } catch { /* a disabled store must never stop the shelf rendering */ }
  window.dispatchEvent(new CustomEvent(SHAPE_EVENT));
}
