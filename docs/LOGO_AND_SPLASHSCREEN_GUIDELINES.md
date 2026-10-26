# SPECTRA — Visual Identity, HD Logo Recreation & Splashscreen Guidelines

---

## 1. Executive Summary & Brand Metaphor

**SPECTRA** (*Universal Hardware Telemetry & Logic Board Diagnostics*) represents high-precision, low-level optical and serial interrogation of embedded microcontrollers. 

### Visual Metaphor
* **The Monolith / Obsidian Prism**: Represents the machine's encrypted or raw EEPROM and logic board—opaque, protective, and dense with internal telemetry.
* **The Coherent Ruby Beam**: Represents the physical interrogation probe (such as the optical infrared carrier of the *Jura USB Scanner N 010* or serial TX line) penetrating the hardware barrier.
* **Chromatic Dispersion (The Spectrum)**: Represents SPECTRA's core engine decoding monolithic memory registers into four isolated, actionable operational telemetry streams.
* **The Carbon Hexagonal Shield**: Symbolizes industrial ruggedness, embedded hardware protection, and diagnostic safety interlocks.

---

## 2. Geometric Anatomy & Vector Construction

To faithfully recreate the icon in clean HD vector format (SVG, Adobe Illustrator, Affinity Designer, or Figma), adhere to the following geometric framework:

```
                  Hexagonal Outer Frame
                     ┌───────────┐
                    /             \
                   /   ▲ Prism     \
                  /   / \           \
  Ruby Laser --->│---│-*-│==========│---> 4 Spectral Traces
   (Input Probe)  \   \ /           /      (Decoded Telemetry)
                   \   ▼           /
                    \             /
                     └───────────┘
```

### A. Outer Hexagonal Shield
1. **Geometry**: Regular hexagon oriented with flat top and bottom edges (or vertical symmetry along the Y-axis).
2. **Beveling & Chamfer**: Subtle corner rounding ($r \approx 8\%$ of radius) with a 2-step inner chamfer giving a milled metallic/carbon finish.
3. **Substrate Texture**: Radial carbon-weave / dark brushed obsidian (`#0B0D13` to `#161922`).
4. **Bicolor Edge Lighting**:
   - **Left Facets**: Electric Cyan rim glow (`#00F0FF`, 40% opacity, soft outer blur).
   - **Right Facets**: Neon Ruby rim glow (`#FF1E56`, 40% opacity, soft outer blur).

### B. The Obsidian Prism
1. **Geometry**: Centered equilateral or tall isosceles triangle ($60^\circ$ apex or $55^\circ$ apex angle).
2. **Faceting & Depth**: 3D translucent smoky glass. Three distinct faceted planes (Left receiving face, Right dispersing face, and Bottom reflection plane).
3. **Internal Caustic Core**: An intense white-hot point of convergence at the internal refraction junction where the ruby laser breaks into the four spectral data channels.

### C. Input Coherent Beam
- A continuous, laser-focused ruby-red vector stroke entering from the left border, passing through the hexagonal badge, and terminating cleanly on the left facet of the prism.
- Core: Solid `#FFFFFF` (1px width).
- Inner Glow: Intense Neon Ruby (`#FF1E56`, 3px stroke).
- Outer Halo: Soft crimson dispersion field (`#FF003C`, 8px stroke, 30% alpha).

### D. The Four Telemetry Spectral Traces
Each ray represents a specific domain of machine diagnostics, diverging cleanly toward the right at precise angles:

| Channel | Diagnostic Meaning | Angle | Gradient Hex Range | Terminal Node |
| :--- | :--- | :--- | :--- | :--- |
| **Trace 1 (Top)** | **Thermal & Heat Management** (Thermoblocks, NTC sensors) | $-24^\circ$ | `#FF1E56` $\rightarrow$ `#FF6B00` | Circular node at $X=88\%, Y=28\%$ |
| **Trace 2 (Upper Mid)** | **Safety Interlocks & Alerts** (Microswitches, tray/tank sensors) | $-8^\circ$ | `#FF8A00` $\rightarrow$ `#FFD600` | Circular node at $X=92\%, Y=44\%$ |
| **Trace 3 (Lower Mid)** | **Lifecycle & Hygiene Metrics** (Cups dispensed, rinse/clean cycles) | $+8^\circ$ | `#00FF88` $\rightarrow$ `#50FA7B` | Circular node at $X=92\%, Y=56\%$ |
| **Trace 4 (Bottom)** | **Hydraulics & Pressure Dynamics** (DigiMesa flowmeter, pump duty) | $+24^\circ$ | `#00D2FF` $\rightarrow$ `#8BE9FD` | Circular node at $X=88\%, Y=72\%$ |

### E. Circuit Termination Nodes
- Each spectral ray terminates in a concentric holographic circuit pad.
- **Inner Circle**: Solid neon matching the trace color.
- **Outer Ring**: 1.5px stroke with a $25\%$ gap on the left to indicate wire entry.

---

## 3. Master Color Palette Specifications

```
HEX CODES REFERENCE:
┌─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│ Obsidian Base   │ Carbon Dark     │ Edge Cyan Glow  │ Edge Ruby Glow  │
│ #0B0D13         │ #161922         │ #00F0FF         │ #FF1E56         │
├─────────────────┼─────────────────┼─────────────────┼─────────────────┤
│ Thermal Ruby    │ Safety Amber    │ Lifecycle Green │ Hydraulic Cyan  │
│ #FF3B30 -> 6B00 │ #FFB800 -> E600 │ #00FF88 -> 50FA │ #00E5FF -> 8BE9 │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
```

* **Obsidian Crystal Tint**: Linear gradient from `rgba(28, 32, 48, 0.85)` at apex to `rgba(12, 14, 20, 0.95)` at base, with specular surface reflection along the left edge (`rgba(255, 255, 255, 0.3)`).
* **Specular Dispersion Core**: `#FFFFFF` with radial falloff into `#FFB8F8` (high-energy chromatic aberration).

---

## 4. Multi-Resolution & Scalability Matrix

When producing vector and raster assets, generate the following dedicated versions:

| Resolution | Target Usage | Complexity & Detailing Rules |
| :--- | :--- | :--- |
| **16×16 px** | Favicon, tiny desktop tray | **Silhouette Mode**: Thick 2px outer hexagon, solid triangle prism, single high-contrast ruby-to-cyan split. Remove fine textures, carbon grid, and glowing nodes. |
| **32×32 px** | Window titlebars, file managers | **Medium Detail**: Visible 4 colored lines, solid terminal nodes, simplified bevels. |
| **48×48 / 64×64 px** | Desktop taskbars, system menus | **Full Iconography**: Full glow halos, visible prism transparency, dual-color rim lighting. |
| **128×128 / 256×256 px** | Standard application icon (`icon.png`) | **Master Render**: Full carbon-fiber weave background, specular prism facets, precise terminal circuit pads. |
| **512×512 / 1024×1024 px** | High-DPI screens, docs, release banners | **Ultra-HD Render**: Volumetric light bloom, sub-surface scattering in obsidian glass, brushed metal bevel micro-scratches. |
| **Vector SVG Master** | Source repository asset | Fully scalable pure vector path structure with organized groups (`frame`, `prism`, `rays`, `nodes`). |

---

## 5. Animation Specification (Motion Design Blueprint)

For a future animated boot sequence or interactive telemetry indicator:

### Motion Phases & Timing
1. **Phase 1: Boot Energize (0.0s – 0.4s)**:
   - Hexagonal border illuminates clockwise with cyan and ruby streaks.
   - The central obsidian prism fades in with an ease-out scale ($90\% \rightarrow 100\%$).
2. **Phase 2: Optical Laser Strike (0.4s – 0.7s)**:
   - A ruby laser pulses rapidly from left to right along the X-axis ($X: 0\% \rightarrow 42\%$).
   - Upon impact with the prism's left facet, an instantaneous high-energy optical burst flares at the contact point.
3. **Phase 3: Telemetry Dispersion (0.7s – 1.3s)**:
   - The four spectral traces shoot outward simultaneously along their trajectory angles.
   - Particle glow sparks travel along each path.
4. **Phase 4: Node Lock & Telemetry Steady-State (1.3s – 1.8s)**:
   - The terminal circuit nodes flash bright and snap into place.
   - Steady-state idle animation begins: subtle $\pm 5\%$ breathing pulse on the core caustics and subtle periodic light packets traveling through the 4 data lines every 1.5 seconds (synchronous with auto-polling frequency).

---

## 6. Splashscreen Implementation Architecture

### A. GTK3 Desktop Splashscreen (`gui.py`)
- **Dimensions**: $640 \times 400\text{ px}$ (golden ratio centered dialog).
- **Window Flags**: `Gtk.WindowType.TOPLEVEL`, `set_decorated(False)`, `set_position(Gtk.WindowPosition.CENTER)`.
- **Background**: Translucent rounded dark card (`border-radius: 12px`, `#121620` with 95% opacity).
- **Visuals**:
  - Top center: Animated or high-DPI rendered logo ($220 \times 220\text{ px}$).
  - Typography: **`SPECTRA`** in bold tracking ($24\text{pt}$, `#8BE9FD`), subtitle *"Universal Hardware Telemetry & Logic Board Diagnostics"*.
  - Bottom strip: Slim high-tech progress bar with animated cyan-to-ruby gradient and real-time status string (e.g., *"Probing diagnostic adapter on /dev/ttyUSB0..."*).
- **Transition**: Seamless 250ms cross-fade into main window once serial handshake completes.

### B. Web Dashboard Boot Loader (`gui_web.py`)
- Zero external dependencies: Pure SVG + CSS keyframe animations.
- Embedded directly in the initial HTTP payload before `fetch('/api/ports')` returns.
- CSS `@keyframes` handle the laser beam draw-in (`stroke-dashoffset`) and ray dispersion.

---

## 7. Designer Checklist for Re-creation

When exporting assets:
- [ ] Maintain exact hex colors defined in **Section 3**.
- [ ] Export master SVG with `viewBox="0 0 1024 1024"`.
- [ ] Convert all text and stroke outlines to closed compound paths.
- [ ] Ensure SVG uses clean grouping (`<g id="shield">`, `<g id="prism">`, `<g id="beam">`, `<g id="traces">`, `<g id="nodes">`) to facilitate direct CSS/Lottie animation.
- [ ] Test raster icons against both pure dark (`#000000`) and mid-grey desktop backgrounds to guarantee optical contrast.
