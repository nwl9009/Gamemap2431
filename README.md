# Xenimus Game Map - World 2431

Interactive map viewers for the Xenimus World 2431 game world.

## Quick Start

From the project root, start a local HTTP server:

```bash
python -m http.server 8000
```

Then open http://localhost:8000 in your browser.

## Viewers

- **Satellite Viewer** (`satellite_viewer.html`) - Leaflet-based tiled map with overlays for monster zones, hazard tiles, teleports, and dungeon room breakouts.
- **Map Viewer** (`map_viewer.html`) - Canvas-based composite map with tile type/flag inspection on hover. Requires `../map_output/` with generated PNG images.
