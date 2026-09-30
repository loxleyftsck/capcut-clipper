# capcut-clipper

Plugin untuk coding agent (Claude Code, Codex, dll.) yang mengubah video panjang talking-head/podcast
menjadi klip 9:16 TikTok/Reels/Shorts sebagai **proyek CapCut Desktop** yang siap diedit dan di-export.

Satu paket berisi:
- **Skill** `video-clipper`: workflow dan aturan editing (hook, jump cut, caption, B-roll, SFX).
- **Subagent** `clipper`: menjalankan skill dari awal sampai akhir.
- **MCP server** `capcut`: 35+ tool untuk membaca, mengedit, dan mem-preview proyek CapCut.
- **CLI** `python -m clipper`: pipeline transkrip → build → audit → install.

## Hasil per klip
- Jump cut di batas kata (dari timestamp per kata faster-whisper)
- Crop 9:16 di tengah, zoom pelan, framing bergantian di setiap cut, dan **punch-in otomatis** sampai tidak
  ada jeda visual >5 dtk
- **Caption per kata dengan highlight kuning**, font Segoe UI Black, punchline kuning dan lebih besar
- Judul hook besar di 3,6 dtk pertama, dan kredit sumber
- B-roll foto dengan zoom pelan dan whoosh
- Suara dirender ulang ke **-14 LUFS** dengan batas puncak -1,5 dBTP (tanpa clipping), denoise CapCut aktif, SFX (pop/whoosh/boom)
- Preview mp4 dan `report.json`. `audit` memeriksa freeze, loudness, jeda visual, dan durasi.

## Syarat
Windows, CapCut Desktop (sudah pernah dipakai minimal sekali; teruji di 9.5), Python 3.11+, ffmpeg.

## Instalasi
```powershell
git clone https://github.com/loxleyftsck/capcut-clipper.git
cd capcut-clipper
.\setup.ps1
```

**Sebagai plugin Claude Code** (skill, agent, dan MCP sekaligus):
```
/plugin marketplace add C:\path\ke\capcut-clipper
/plugin install capcut-clipper@capcut-clipper
```

**Hanya MCP-nya** (Claude Code, scope user): `.\setup.ps1 -RegisterMcp`

**Codex**: agent otomatis membaca `AGENTS.md`. Untuk MCP, tambahkan ke `~/.codex/config.toml`:
```toml
[mcp_servers.capcut]
command = "C:/path/ke/capcut-clipper/.venv/Scripts/python.exe"
args = ["-m", "capcut_mcp.server"]
```

## Cara pakai
Minta ke agent: *"clip-kan video `C:\...\episode.mp4` jadi 5 klip TikTok"*. Agent akan membaca transkrip,
mengusulkan kandidat klip, lalu build setelah Anda memilih.

Atau jalankan manual:
```powershell
$py = ".venv\Scripts\python.exe"
& $py -m clipper doctor
& $py -m clipper transcribe projects\episode\clips.json   # isi source + template_project dulu
# tulis clips[] di clips.json (lihat examples\clips.example.json)
& $py -m clipper broll   projects\episode\clips.json
& $py -m clipper build   projects\episode\clips.json
& $py -m clipper audit   projects\episode\clips.json
& $py -m clipper install projects\episode\clips.json
```

## Batasan
- Animasi teks, transisi, efek, dan filter CapCut hanya bisa **dipakai ulang** dari yang pernah Anda pasang
  manual (katalog lokal). Pasang 1 animasi dan 1 transisi di proyek mana saja sekali, lalu agent bisa
  memakainya massal.
- Preview ffmpeg tidak me-render animasi, transisi, filter, dan outline CapCut. Cek final dan export tetap
  dilakukan di CapCut.
- Tutup proyek di CapCut sebelum agent menulisnya.

## Lisensi
MIT. `mcp/capcut-mcp` adalah salinan [LHenri88/capcut-mcp](https://github.com/LHenri88/capcut-mcp) (MIT)
dengan patch lokal yang dicatat di `mcp/capcut-mcp/PATCHES.md`. Foto B-roll dan transkrip ada di `projects/`
dan tidak ikut di-commit.
