# targum identity — direction A

Ink column = source, accent column = translation. Flat only: no gradients, bevels, shadows.

## Files
- mark.svg / mark-dark.svg — two-colour monogram (light: #201e1b + #a5824f; dark: #f3efe7 + #c8a778)
- mark-mono.svg — single colour, inherits currentColor
- favicon.svg — auto light/dark via prefers-color-scheme; favicon-16/32.png fallbacks
- app-icon.svg, app-icon-dark.svg — rounded previews; app-icon-*.png are full-bleed squares (the OS masks corners), apple-touch-icon-180.png for iOS
- lockup.svg / lockup-dark.svg / lockup-rtl.svg — editable SVG text in the reading face (Iowan Old Style → Palatino → Georgia). Outline the text before print use or on systems without these faces.
- mark-512.png, mark-dark-512.png — raster monogram, transparent

## Rules
- Clear space: half the mark's height on all sides. Monogram >= 16 px; lockup >= 72 px wide; below 24 px use the monogram alone.
- Single-colour (mono) everywhere small or third-party; all-ink or all-accent are both legal.
- RTL: the mark mirrors and leads from the right; Hebrew wordmark is תרגום, same face and weight. 
- Accent is never text and never a large field. #a5824f/#7a5c38 on paper, #c8a778 on ink.

## HTML
```html
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="alternate icon" href="favicon-32.png">
<link rel="apple-touch-icon" href="apple-touch-icon-180.png">
```
