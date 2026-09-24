# Laser Plate Base SVG Generator

Python scripts for generating four-panel laser-cut plate bases. Dimensions are
specified in millimetres and the resulting SVG files use red through-cut paths
and optional blue engraving labels.

## Designs

### Loose tab-and-slot design

`src/laser_plate_base_slot_insert.py` places tabs on the front/back panels and
matching through-slots in the left/right panels. The default `hook` joint has a
5 mm downward-facing hook beyond the outside face. Insert each front/back panel
5 mm above its finished position, then slide it down; the hook catches behind
the lower slot edge. Reverse that movement to disassemble it. Use
`--joint straight` for the older non-locking version.

The hook dimensions can be adjusted with `--hook-overhang` (projection beyond
the side panel) and `--lock-drop` (vertical insertion/locking movement). Both
default to 5 mm. The default staggered layout uses different tab heights at
adjacent corners.

The default `--layout auto` nests each front/back panel inside a 90-degree
rotated side panel whenever the dimensions leave safe material bridges. This
greatly reduces sheet usage and leaves the side panels as open frames. If the
parts cannot be nested safely, the script automatically uses the original
stacked layout. Use `--layout nested` or `--layout stacked` to force either
choice, and adjust the required frame width with `--min-bridge`.

```powershell
python .\src\laser_plate_base_slot_insert.py `
  --width 100 --depth 250 --height 150 --thickness 5.5 `
  --tabs 3 --clearance 0.20 --joint hook `
  --hook-overhang 5 --lock-drop 5 `
  -o .\examples\my_slot_insert_base.svg
```

### Finger-jointed design

`src/laser_plate_base.py` creates a more strongly interlocked box-joint frame.

```powershell
python .\src\laser_plate_base.py `
  --width 100 --depth 250 --height 150 --thickness 5.5 `
  --fingers 5 --clearance 0.10 `
  -o .\examples\my_finger_joint_base.svg
```

Width and depth are the assembled outside dimensions. Measure the real sheet
thickness with calipers before cutting. Kerf is recorded in SVG metadata; apply
the machine-specific kerf/tool offset in the laser CAM software. Make a small
fit test before cutting the full-sized parts.
