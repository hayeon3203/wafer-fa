# Wafer Failure Analysis

Stage 1 of a semiconductor wafer defect classification system, modeled after SemiFA. Takes a wafer's die-level test result grid and classifies which defect pattern it shows.

## Language

**Wafer Map**:
A grid of per-die test outcomes for one wafer (source: WM-811K, values 0/1/2 per die). Rendered as a color image before being fed to the classifier.
_Avoid_: wafer photo, wafer image (as source data — it is not a photo until rendered)

**Die**:
A single unit position on the wafer map grid, with test outcome background / pass / fail.

**Defect Class**:
One of the 9 WM-811K labels assigned to a wafer map: Center, Donut, Edge-Loc, Edge-Ring, Loc, Random, Scratch, Near-full, none.
_Avoid_: failure type, defect category

**Digital Twin Feed**:
The intended production source of wafer map matrices — auto-collected from a digital twin of the fab equipment, not a camera photo. The classifier's real input is this raw matrix; a rendered image is only a display/model-input step derived from it.
_Avoid_: wafer camera, wafer photo (as the production source)
