# Xenimus Game Map - World 2431

A GitHub Pages deployment of interactive map viewers for the Xenimus World 2431 game world. This repository contains static HTML/JS files served via GitHub Pages at [nwl9009/Gamemap2431](https://github.com/nwl9009/Gamemap2431), providing two browser-based tools for exploring the world map with overlays for teleports, hazards, monster spawns, and more.

## Quick Start

For local testing, start a simple HTTP server from the project root:

```bash
python -m http.server 8000
```

Then open http://localhost:8000 in your browser.

## Viewers

### Satellite Viewer (`satellite_viewer.html`)

Leaflet-based tiled map with full pan/zoom support. Features include:

- Overlay layers for teleports, hazards, monster spawn zones, and special tiles
- Clickable markers with detailed info popups
- Room overlays showing dungeon boundaries and breakouts
- Layer toggle controls to show/hide individual overlay categories

### Map Viewer (`map_viewer.html`)

Canvas-based composite map rendering the full world as a single image. Features include:

- Tile type and flag inspection on hover
- Requires `../map_output/` with pre-generated PNG images from XenMap

## Data Sources

All map data is generated upstream and copied into this repository for static serving. The viewer consumes the following data files:

- **`hazards.json`** — Hazard tile locations and types
- **`teleports.json`** — Teleport entry/exit coordinates
- **`mongen_zones.json`** — Monster spawn zone definitions
- **`special_tiles.json`** — Special tile markers (shops, altars, etc.)
- **`rooms/`** — Dungeon room boundary definitions
- **`tiles/`** — Pre-rendered tile images used by the satellite viewer

This data is produced by [XenMap](https://github.com/nwl9009/XenMap) using tile data captured by [XenTools](https://github.com/nwl9009/XenTools). See those repositories for the generation pipeline.

## Deployment

This site is served via GitHub Pages from the `nwl9009/Gamemap2431` repository. To update the map:

1. Regenerate data files using XenMap tools (see XenMap README for details)
2. Copy the updated JSON files, room definitions, and tile images into this repo
3. Commit and push — GitHub Pages will serve the changes automatically
