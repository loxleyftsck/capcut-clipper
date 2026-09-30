---
name: video-clipper
description: Potong video panjang (podcast, talking-head, YouTube) jadi klip pendek 9:16 untuk TikTok/Reels/Shorts sebagai proyek CapCut, lengkap dengan hook, jump cut, caption per kata, punch-in zoom, B-roll, SFX, loudness -14 LUFS, dan preview. Gunakan saat user minta "clip", "potong jadi short", "segmen clipper", "bikin konten TikTok/Reels dari video ini", atau merevisi klip CapCut vertikal.
---

# Video Clipper (CapCut)

Semua perintah dijalankan dari root repo `capcut-clipper` dengan `.venv\Scripts\python.exe -m clipper ...`
(selanjutnya ditulis `clipper`). Satu video sumber = satu folder `projects/<slug>/` berisi `clips.json`.
Format spec: `examples/clips.example.json`.

## 0. Cek setup
`clipper doctor`. Harus: `plaintext_drafts: true`, `ffmpeg_exe` ketemu, `segoe_ui_black: true`,
`faster_whisper: true`. `catalog_entries: 0` berarti animasi/transisi CapCut belum bisa dipakai (lihat §7).

## 1. Transkrip
Buat `projects/<slug>/clips.json` minimal berisi `source`, `template_project` (nama proyek CapCut apa saja
yang sudah ada, dipakai sebagai cetakan dengan ID baru), dan `"clips": []`. Lalu jalankan
`clipper transcribe projects/<slug>/clips.json`. Hasilnya `transcript.json` (segmen + timestamp per kata)
dan `transcript.txt`. **Baca SELURUH `transcript.txt`** sebelum memilih klip.

## 2. Pilih segmen
Tulis 3–5 kandidat beserta alasan dan timestamp, lalu minta user memilih.
- **Durasi 25–60 dtk**, berisi satu ide utuh yang bisa dipahami tanpa menonton video panjangnya.
- **Mulai tepat di hook**, karena keputusan swipe terjadi dalam ≤1 dtk. Buang basa-basi seperti
  "oke jadi", "gue ada pertanyaan", atau "tadi gue bilang".
- Hook kuat: klaim kontrarian, mitos yang dipatahkan, redefinisi ("fungsi asli uang itu…"),
  angka/kontras, cerita atau analogi pendek.
- **Akhiri di punchline**, bukan di tengah transisi ke topik baru.
- Gunakan jump cut (beberapa `ranges`) untuk membuang pengulangan, filler, tangent, dan ucapan yang
  menghina penonton.
- Hindari klip yang bergantung pada "orang tadi" tanpa konteks, dan jangan jadikan klaim finansial
  spesifik (prediksi harga, ajakan beli aset) sebagai hook.

## 3. Tulis spec klip
Untuk setiap klip isi `name`, `title`, `ranges`, `captions`, dan `broll`. Semua waktu dalam **detik sumber**.
- Potong di batas kata (lihat `words` di `transcript.json`), jangan di tengah kata.
- `title` = hook ≤6 kata, boleh 2 baris (`\n`), HURUF KAPITAL.
- `captions`: `[teks, start, end, accent]`. Tulis ulang salah-dengar Whisper supaya maknanya tepat.
  Builder otomatis memecahnya jadi baris 1–3 kata dengan **highlight per kata** (kata yang diucapkan
  berwarna kuning). `accent: true` untuk punchline: seluruh baris kuning, lebih besar, dan diberi punch-in zoom.
- `broll`: `[stem_foto, start, end]`, 2–4 dtk tepat di kalimat yang dianalogikan, maksimal ~3 per klip.

## 4. B-roll (foto)
Cari foto di Pexels/Pixabay (lisensi bebas pakai). **Tunjukkan daftar foto + ukurannya dan minta izin
user sebelum mengunduh.** Simpan ke `projects/<slug>/broll/` dengan nama `<topik>_<id>.jpg`, lalu jalankan
`clipper broll SPEC` untuk mengubahnya ke 9:16 (`broll/916/`).

## 5. Build → QA → install
1. `clipper build SPEC [nomor]` membuat proyek dan preview di `out/`, plus `<klip>.report.json`.
2. `clipper audit SPEC` harus menghasilkan `issues: OK`. Yang dicek: freeze, loudness ±2 dari -14 LUFS,
   true peak, jeda visual ≤5 dtk, durasi 20–65 dtk, dan kredit.
3. Lihat frame hook, setiap jump cut, setiap B-roll, dan akhir klip (`media.frame_sheet` atau MCP
   `capcut_frame`). Pastikan wajah tidak terpotong dan caption sinkron.
4. `clipper install SPEC [nomor]` menyalin ke CapCut dan membackup versi lama. Proyek yang sedang
   dibuka (`.locked`) dilewati. CapCut otomatis mendeteksi folder baru.
5. Kirim preview mp4 ke user. SFX hasil sintesis perlu **didengar oleh user**, karena agent tidak bisa mendengar.

## 6. Gaya yang dipakai builder
- Font Segoe UI Black (mirip Montserrat Black/Hormozi), putih dengan outline hitam, highlight kuning `(1, .82, .25)`.
  Caption di y=-0.30, judul di y=0.66, kredit di y=0.88. Semuanya di dalam safe zone TikTok.
- Speaker: crop tengah 9:16, zoom pelan 1.00→1.06, framing bergantian 1.12 di setiap jump cut,
  punch-in +0.12 di punchline, dan tambahan punch-in +0.07 sampai tidak ada jeda visual >5 dtk.
- Audio: suara speaker dirender jadi track tersendiri (`out/<klip>.voice.wav`, loudnorm dua-pass -14 LUFS,
  true peak ≤ -1,5 dBTP) dengan denoise CapCut aktif, sedangkan audio asli klip video dimatikan. Jangan menaikkan
  volume klip untuk mengejar loudness karena puncak suaranya akan clipping. SFX: pop di awal, whoosh_soft di setiap jump cut,
  whoosh_fast di setiap B-roll, boom di punchline terakhir, dengan volume 0.10–0.18 (sekitar -18 s.d. -20 dB).

## 7. Animasi, transisi, dan efek CapCut
Semuanya hanya bisa **dipakai ulang** dari katalog lokal, yaitu yang pernah diterapkan manual di CapCut.
Kalau `doctor` melaporkan katalog kosong, minta user: buka proyek uji → pasang 1 animasi teks (In) +
1 transisi (+ opsional efek/filter) → simpan → tutup CapCut. Setelah itu gunakan tool MCP
`capcut_catalog_refresh`, `capcut_catalog_search`, `capcut_add_animation`, dan `capcut_add_transition`
pada proyek yang sudah di-install, lalu `capcut_save`.

## Aturan keras
- **Jangan menulis ke proyek yang sedang dibuka di CapCut.** `capcut_save` menolak selama CapCut berjalan,
  dan `install` melewati folder `.locked`.
- Minta izin sebelum mengunduh file apa pun (foto, musik, SFX, font).
- Klip dari konten kreator lain wajib diberi `credit`, kecuali user adalah pemilik kanal atau clipper resmi.
- Preview ffmpeg tidak me-render animasi, transisi, filter, atau outline CapCut. Hasil final diperiksa dan
  di-export (1080x1920) dari CapCut.
