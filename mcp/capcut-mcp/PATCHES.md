# Local patches on top of upstream capcut-mcp

Vendored from https://github.com/LHenri88/capcut-mcp (MIT, see LICENSE) at commit `8c42696`.

| File | Change | Why |
|---|---|---|
| `paths.py` | `ffmpeg_exe()` resolver (env `CAPCUT_MCP_FFMPEG` → PATH → any parent `bin/`) | MCP clients on Windows may launch servers with a stripped environment; an `env` block in the MCP config replaces the whole Windows env and the server dies. |
| `paths.py` | also search `%LOCALAPPDATA%\CapCut\Apps` for bundled fonts | default CapCut install location |
| `preview.py` | `fps=` filter before `zoompan` | a 24 fps source played at 24/30 speed and froze ~80% into every clip |
| `preview.py` | rich-text runs drawn separately | word-by-word caption highlight preview |
| `preview.py` | filter graph passed via `-filter_complex_script` | caption-heavy timelines exceed Windows' 32k command-line limit |
| `ir.py` | expose `runs` for multi-style text | feeds the rich-text preview |
| `edits.py` / `server.py` | `font_path` on add_text, `capcut_set_canvas`, `capcut_add_video_track` | 9:16 builds, B-roll tracks, custom fonts |
