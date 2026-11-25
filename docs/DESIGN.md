# Sistem Desain Sister Creative

Sumber kebenaran token ada di `assets/css/input.css` (`@theme`). Dokumen ini menjelaskan cara memakainya.
Palet bawaan Tailwind dimatikan (`--color-*: initial`), jadi kelas seperti `bg-gray-100` tidak akan berfungsi.

## Warna

| Token | Hex | Pemakaian |
|---|---|---|
| `primary` | `#6d28d9` | CTA utama, tautan, aksen, fokus |
| `primary-dark` | `#4c1d95` | Hover CTA |
| `primary-soft` | `#efe5ff` | Latar sorotan, badge |
| `primary-light` | `#c8a8ff` | Eyebrow/aksen di atas latar gelap |
| `accent` | `#f4c95d` | Sorotan kecil (nomor langkah, ikon) di latar gelap |
| `ink` | `#17131f` | Teks utama |
| `muted` | `#6d6876` | Teks sekunder di latar terang |
| `surface` | `#f7f5fb` | Latar section/footer/dashboard |
| `line` | `#e7e1ee` | Border, pemisah |
| `dark` | `#181221` | Section gelap, panel hero |
| `dark-raised` | `#251d30` | Kartu di atas `dark` |
| `on-dark-muted` | `#bcb3c7` | Teks sekunder di latar gelap |
| `success` / `-soft` | `#15803d` / `#dcfce7` | Status berhasil |
| `danger` / `-soft` | `#b91c1c` / `#fee2e2` | Error, aksi hapus |
| `warning` / `-soft` | `#92400e` / `#fef3c7` | Peringatan, status menunggu |
| `white` | `#ffffff` | Latar halaman, teks di atas `primary` |

**Kontras (WCAG AA, teks normal ≥ 4.5:1):** `ink`/white 18:1, `muted`/white 5.4:1, `primary`/white 7.1:1,
white/`primary` 7.1:1, `on-dark-muted`/`dark` 9:1, `accent`/`dark` 11:1.
Jangan pakai `accent` sebagai warna teks di atas latar terang, karena kontrasnya terlalu rendah.

## Tipografi

Font: **Open Sans** (400, 500, 600, 700, 800). Basis 16px, `line-height` 1.7.

| Peran | Kelas | Ukuran |
|---|---|---|
| Judul hero (h1) | `text-display font-extrabold` | clamp(2.5rem → 4.75rem) |
| Judul section (h2) | `text-heading font-extrabold` | clamp(2rem → 3.25rem) |
| Judul kartu (h3) | `text-xl font-bold` (kartu besar `text-2xl`) | 1.25 / 1.5rem |
| Teks pengantar | `text-lg text-muted` | 1.125rem |
| Teks isi | `text-base` | 1rem |
| Eyebrow | `text-eyebrow font-extrabold uppercase text-primary` | 0.78rem, tracking 0.14em |
| Kecil / meta | `text-sm` / `text-xs` | 0.875 / 0.75rem |

## Spacing & layout

Spacing memakai skala bawaan Tailwind (kelipatan 4px). Pola baku:

- **Container:** `container-site` (maks 1160px, gutter 16px di mobile dan 20px mulai `md`).
- **Section:** `py-18 md:py-24`. Hero memakai `pt-14 pb-18 md:pt-24 md:pb-22`.
- **Kepala section:** `max-w-2xl mb-10 md:mb-12`.
- **Grid kartu:** `grid gap-4 md:grid-cols-2 lg:grid-cols-3`.
- **Padding kartu:** `p-6 md:p-8`.
- **Form:** label ke input `gap-1.5`, antarfield `gap-5`.

Breakpoint yang wajib dicek: **375px** (mobile), **768px** (`md`) dan **1280px** (`xl`). Tulis kelas untuk mobile lebih dulu.

## Radius & bayangan

- `rounded-button` (14px): tombol, input.
- `rounded-card` (22px): kartu.
- `rounded-panel` (32px): panel besar, CTA kontak.
- `rounded-full`: pill/tag.
- `shadow-soft`: kartu saat hover, panel hero. `shadow-primary`: tombol primer.

## Komponen

- **Tombol primer:** `bg-primary text-white rounded-button min-h-13 px-6 font-extrabold shadow-primary hover:bg-primary-dark`.
- **Tombol sekunder:** `bg-white border border-line rounded-button min-h-13 px-6 font-extrabold`.
- Target sentuh minimal 44×44px.
- **Ikon:** Lucide, ditulis inline lewat `{% include "components/icon.html" with name="..." %}`. Ukuran default 20px dengan `stroke-width` 2. Ikon dekoratif diberi `aria-hidden="true"`.

## Gerak

- Animasi memakai Motion (vanilla JS) dan diaktifkan lewat atribut `data-reveal`. Durasinya 0.5–0.7 detik dengan *ease-out*.
- Pengguna yang memilih `prefers-reduced-motion` tidak mendapat animasi; konten langsung tampil.
- Tidak ada `<script>` di template halaman. Semua JS ada di `static/js/` dan dimuat dari `base.html`.

## Aksesibilitas

- Semua `<img>` wajib punya `alt`. Gambar dekoratif memakai `alt=""`.
- Fokus keyboard selalu terlihat (outline `primary` 3px dari `:focus-visible`).
- Ada tautan "Lewati ke konten" di `base.html`.
- Field form wajib punya `<label>`, dan pesan error dihubungkan lewat `aria-describedby`.
