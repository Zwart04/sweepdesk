# SweepDesk

Pengelola aplikasi GUI dan CLI untuk **Debian, Ubuntu, dan distro turunannya**. Tema gelap memakai palet abu-abu netral dan aksen biru ala macOS.

[![Dukung Zwart04 di Tako](assets/support-tako.svg)](https://tako.id/Zwart04)

**[Dukung pengembangan SweepDesk melalui Tako](https://tako.id/Zwart04)**. Dukungan bersifat sukarela; semua fitur tetap tersedia.

![Tampilan SweepDesk dengan daftar contoh](docs/screenshot.png)

## Memasang dengan mudah

1. Buka halaman **[Releases](https://github.com/Zwart04/sweepdesk/releases/latest)**.
2. Unduh `sweepdesk_0.3.0_all.deb`.
3. Klik dua kali untuk memasang, atau buka terminal di folder unduhan dan jalankan:

```bash
sudo apt install ./sweepdesk_0.3.0_all.deb
```

Buka **SweepDesk** dari menu aplikasi. Jalankan sebagai pengguna biasa, tanpa sudo. Kata sandi admin hanya diminta saat operasi paket sistem memerlukannya.

## Menjalankan dari kode sumber

```bash
sudo apt install python3 python3-gi gir1.2-gtk-3.0 librsvg2-common policykit-1
git clone https://github.com/Zwart04/sweepdesk.git
cd sweepdesk
./run.sh
```

Jika distro tidak menyediakan `policykit-1`, gunakan paket `pkexec`. Untuk menambah shortcut menu khusus pengguna, jalankan `./install.sh`. Untuk menghapus instalasi khusus pengguna itu, gunakan `./install.sh --uninstall`. Penghapusan paket `.deb` memakai `sudo apt purge sweepdesk`.

## Cakupan

Sumber yang didukung: **APT/DEB, npm global, pip, Cargo, Flatpak, Snap, pipx, uv tools, Bun global, Homebrew, AppImage ArtCraft, dan executable manual**. Manager yang belum terpasang tidak dipaksakan dipasang. Python sistem yang dilindungi PEP 668 tidak diubah paksa.

Debian 11–13 dan Ubuntu 22.04/24.04/26.04 menjadi target CI. Mint, LMDE, Pop!_OS, Zorin, elementary OS, Kali, dan turunan lain diharapkan kompatibel jika menyediakan Python 3.9+, GTK 3.24+, APT/dpkg, serta sesi desktop dengan agen autentikasi polkit. Bukan jaminan semua versi distro pernah diuji. Lihat status terbaru di [Actions](https://github.com/Zwart04/sweepdesk/actions).

## Memakai aplikasi

1. Pilih kategori atau sumber instalasi pada **sidebar**. Cari nama aplikasi atau ID paket pada kolom pencarian.
2. Gunakan **System Packages** untuk melihat paket pendukung. Tombol **View options** mengatur visibilitas paket sistem, kerapatan baris, dan panel detail.
3. Klik dua kali untuk detail lengkap. **Klik kanan** menyediakan detail, daftar file APT, buka folder instalasi, salin ID/nama, dan pratinjau uninstall. Aksi yang tidak tersedia dibuat nonaktif.
4. Klik **Review Uninstall…**, pilih opsi pembersihan, lalu **Preview Removal**. Periksa daftar paket dan lokasi data sebelum mencentang persetujuan dan menekan **Uninstall**.
5. **More (•••) → Activity** menyimpan log operasi hanya untuk sesi berjalan. More juga menyediakan ekspor inventaris, status pemindaian, dan bantuan.

Tombol **Settings** pada toolbar ringkas membuka pengaturan tema Dark/Light/System, baris Compact/Comfortable, panel detail, paket sistem, sumber pemindaian, dan folder tambahan. Pengaturan tersimpan di `~/.config/sweepdesk/preferences.json` atau lokasi `XDG_CONFIG_HOME`. Inventaris dan log operasi tidak disimpan otomatis.

![Settings SweepDesk](docs/settings.png)

Tambahkan virtualenv atau folder instalasi melalui **Settings → Scanning** atau menu **More**. Folder bisa diingat untuk sesi berikutnya. Alternatif:

```bash
./run.sh --python "$HOME/proyek/demo/.venv/bin/python" --manual-dir "$HOME/Applications"
```

Pintasan: **Ctrl+F** mencari, **Ctrl+R** memindai ulang, **Ctrl+,** membuka Settings, **Ctrl+I / Enter** membuka detail, **Ctrl+E** mengekspor, dan **Shift+F10** membuka menu klik kanan. **Delete** hanya memulai alur pratinjau, bukan langsung menghapus. Kontrol jendela tetap mengikuti desktop Linux.

Logo aplikasi tersedia sebagai SVG dan PNG 16–512 piksel serta dipasang melalui paket `.deb` agar dipakai di menu aplikasi dan integrasi jendela/dock. Tombol **♥ Support** berbentuk pill membuka [Tako Zwart04](https://tako.id/Zwart04).

## Seberapa bersih penghapusannya?

SweepDesk memakai uninstaller asli tiap manager dan hanya membersihkan data yang lokasinya dikenali. Dependensi bersama, cache bersama, snapshot Snap, runtime Flatpak, dan paket orphan lama yang tidak terkait tidak dihapus sembarangan. Perilaku tiap sumber dijelaskan pada [tabel lengkap README](README.md#what-can-it-clean).

**Tidak ada jaminan semua sisa setiap installer bisa diketahui.** Skrip `curl | bash` dapat menulis ke sembarang tempat tanpa daftar kepemilikan. SweepDesk mendeteksi executable/lokasi yang dikenal; file sistem tanpa registrasi hanya dapat diinventarisasi. File proyek dan seluruh virtualenv di disk tidak dipindai otomatis.

Profil data yang saat ini dikenali meliputi LibreOffice, OpenCode, Claude Code, Codex, curl, dan data aplikasi Flatpak. Pembersihan data bersifat pilihan dan dapat mencakup riwayat, login, profil, serta pengaturan. Data dipindahkan ke **Sampah**, sehingga ruang baru kembali setelah Sampah dikosongkan. Bila Sampah tidak tersedia, penghapusan tidak dialihkan ke hapus permanen.

Ikon aplikasi dibaca dari launcher lokal. Logo resmi OpenCode, Command Code, curl, dan npm disertakan agar CLI tertentu juga mudah dikenali tanpa internet. CLI lain memakai ikon terminal bila ikon resminya belum tersedia.

## Bantuan dan dukungan

- [Dokumentasi lengkap berbahasa Inggris](README.md)
- [Laporkan masalah](https://github.com/Zwart04/sweepdesk/issues)
- **[♥ Dukung Zwart04 melalui Tako](https://tako.id/Zwart04)** — tombol yang sama ada pada judul aplikasi.

Jangan unggah inventaris pribadi, token, atau kata sandi ke laporan publik. Kode asli berlisensi MIT; merek dan logo tetap milik pembuatnya.
