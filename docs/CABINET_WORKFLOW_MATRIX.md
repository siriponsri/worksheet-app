# Cabinet Workflow Matrix — Implementation Source of Truth

This document defines the expected binder behavior. The active React registry
in `apps/web/src/appData.ts` is the source of truth; Cabinet view, List view,
routes, filters, tests, and accessibility labels derive from that typed
configuration. This matrix is a human-readable contract checked against it.

## Building registry

| ID | Label | Color token | Asset | Storage/numbering class | Active |
|---|---|---|---|---|---|
| `B10` | Building 10 | `--binder-b10` | blue | segmented B10 | yes |
| `B12` | Building 12 | `--binder-b12` | violet | segmented B12 | yes |
| `B16` | Building 16 | `--binder-b16` | mint | segmented B16 | yes |
| `OTHER` | Other Locations | `--binder-other` | orange | exact building retained; `_OT`/unsegmented currently | yes |
| `RESERVE` | Coming Soon | `--binder-reserve` | pink | no storage/API/route | disabled |

## Active binder instances

| Instance ID | Group | Exact building filter | Workflow | Display label | Optional secondary filter |
|---|---|---|---|---|---|
| `b10-pw-prw` | B10 | Building 10 | `pw-prw` | PRW & PW | all supported water types |
| `b10-em-air` | B10 | Building 10 | `em-air` | Air Sampling | passive + active |
| `b10-ca` | B10 | Building 10 | `compressed-air` | CA | gas type CA |
| `b10-cv` | B10 | Building 10 | `cv` | Cleaning Validation | CV selector |
| `b12-pw-prw` | B12 | Building 12 | `pw-prw` | PRW & PW | all supported water types |
| `b12-em-air` | B12 | Building 12 | `em-air` | Air Sampling | passive + active |
| `b12-ca` | B12 | Building 12 | `compressed-air` | CA | gas type CA |
| `b12-cv` | B12 | Building 12 | `cv` | Cleaning Validation | CV selector |
| `b16-pw-prw` | B16 | Building 16 | `pw-prw` | PRW & PW | all supported water types |
| `b16-wfi` | B16 | Building 16 | `wfi-pus` | WFI | WFI/PUS records |
| `b16-em-air` | B16 | Building 16 | `em-air` | Air Sampling | passive + active |
| `b16-ca-n2` | B16 | Building 16 | `compressed-air` | CA & Nitrogen | gas type CA/N2 selector or all |
| `b16-cv` | B16 | Building 16 | `cv` | Cleaning Validation | CV selector |
| `other-water` | OTHER | Other | `pw-prw` | Other-Water | PW/PRW and WFI/PUS logical routes |
| `other-air` | OTHER | Other | `em-air` | Other-Air | Environmental Monitoring Air route |
| `other-ca` | OTHER | Other | `compressed-air` | Other-CA | Compressed Air / Nitrogen route |
| `other-cv` | OTHER | Other | `cv` | Other-CV | Cleaning Validation routes |

17 active binders. Other retains its orange physical binder family while the
four domain binders provide unambiguous routes. Exact Building 11, Building
19, or unknown source text remains visible on the individual record.

### Legacy source-location examples

| Section ID | Exact building filter | Workflow | Display label | Secondary filter |
|---|---|---|---|---|
| `b11-em-air` | Building 11 | `em-air` | Building 11 · Air Sampling | passive + active |
| `b11-ca` | Building 11 | `compressed-air` | Building 11 · Compressed Air | gas type CA |
| `b19-prw` | Building 19 | `pw-prw` | Building 19 · PRW | PRW |

### Inside a `cv` binder

One Cleaning Validation binder per building. The kind of record decides the
approved template, so the choice is made when the binder is opened, before the
record list — not at the moment of printing.

| Choice | Then | Template family |
|---|---|---|
| Contact Plate | straight to the record list | `cleaning-validation-contact` |
| Rinse → Pour Plate | method step, then the list | `cleaning-validation-rinse-pour` (PW / PRW) |
| Rinse → Membrane Filtration | method step, then the list | `cleaning-validation-rinse-membrane` (WFI / PUS) |

The chosen method is carried as `testMethod` in the query and pre-selects the
per-record radio group, which can still override it.

## Reserve instances

Pink binders are non-interactive or disabled controls labeled `Coming Soon`. They must not:

- call an API;
- route to an empty workflow;
- show a fake count;
- imply that a production feature exists;
- be used as the `Other Locations` color.

Exactly one reserve binder is on the shelf: `reserve-spare`, pink, spine
printed `COMING SOON`, `state: 'coming-soon'`, `route: null`. It is drawn on
the shelf because the physical spare is on the shelf; it is never openable and
never counted as a destination.

## Configuration shape

```ts
type BuildingGroup = {
  id: 'B10' | 'B12' | 'B16' | 'OTHER' | 'RESERVE';
  label: string;
  colorToken: string;
  assetId: string;
  order: number;
  active: boolean;
};

type BinderInstance = {
  id: string;
  groupId: BuildingGroup['id'];
  buildingFilter: string | null;
  workflowId: 'pw-prw' | 'wfi-pus' | 'em-air' | 'compressed-air' | 'cv';
  label: string;
  iconId: string;
  secondaryFilter?: Record<string, string | string[]>;
  route: string | null;
  state: 'active' | 'disabled' | 'coming-soon';
  order: number;
};
```

The actual code may refine types, but must preserve this separation. Building group, exact building filter, workflow, and optional subtype must not be collapsed into one color/string.

## Layout capacity

- Desktop shelf should support 3–6 normal binders without overlap.
- Building 16 has five active binders and is the minimum density reference.
- Other keeps its orange physical binder family but is split into Other-Water, Other-Air, Other-CA, and Other-CV; B11/B19/unknown source text remains visible on each record.
- If a group exceeds capacity, use shelf pagination/controlled horizontal scroll with visible controls; never shrink labels below readability.
- List view renders every active instance without pagination caused by visual shelf capacity.

## Route examples

- `#/records/water/pw-prw?building=Building%2010`
- `#/records/air/em-air?building=Building%2012`
- `#/records/air/compressed-air?building=Building%2016&gasType=CA,N2`
- `#/records/cv?building=Building%2016`
- `#/records/water/pw-prw?building=Building%2019&waterType=PRW`

Prefer stable internal IDs in code and URL-safe query encoding. Search/get APIs must accept only allowlisted normalized filters.
