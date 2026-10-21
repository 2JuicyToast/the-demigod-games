# The Demigod Games

A Roblox game project focused on mythic heroes, powers, and competitive challenges.

## Repository layout

- `assets/blender/` — Blender source files, references, and exported model notes.
- `assets/models/` — Roblox-ready model exports such as `.fbx` or `.obj` files.
- `tools/blender/` — Python scripts and setup notes for automating Blender model preparation.
- `src/server/` — Server-side Roblox Lua scripts.
- `src/client/` — Client-side Roblox Lua scripts.
- `src/shared/` — Shared Roblox Lua modules and configuration.
- `docs/` — Design notes, workflows, and development documentation.

## Development notes

Roblox Studio is the source of truth for the place file. Large binary assets should be managed carefully and added only when needed. Keep Blender source files separate from Roblox exports so models can be re-exported later.

Lua files in `src/` are intentionally starter placeholders for future gameplay systems.
