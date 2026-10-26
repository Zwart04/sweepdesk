# SweepDesk

**[Website Bahasa Indonesia](https://zwart04.github.io/sweepdesk/id.html)** · [Unduh versi terbaru](https://github.com/Zwart04/sweepdesk/releases/latest) · [English](README.md)

Pengelola aplikasi GUI dan CLI untuk **Debian, Ubuntu, dan distro turunannya**. Tema gelap memakai palet abu-abu netral dan aksen biru ala macOS.

[![Dukung Zwart04 di Tako](assets/support-tako-id.svg)](https://tako.id/Zwart04)

**[Dukung pengembangan SweepDesk melalui Tako](https://tako.id/Zwart04)**. Dukungan bersifat sukarela; semua fitur tetap tersedia.

![Tampilan SweepDesk dengan daftar contoh](docs/screenshot-id.png)

## Memasang dengan mudah

1. Buka halaman **[Releases](https://github.com/Zwart04/sweepdesk/releases/latest)**.
2. Unduh `sweepdesk_0.4.0_all.deb`.
3. Klik dua kali untuk memasang, atau buka terminal di folder unduhan dan jalankan:

```bash
sudo apt install ./sweepdesk_0.4.0_all.deb
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

## Bahasa aplikasi

Buka **Pengaturan → Tampilan → Bahasa**, pilih **Bahasa Indonesia**, **English**, atau **Ikuti sistem**, lalu tekan **Simpan**. Tampilan langsung berubah tanpa menutup aplikasi. Daftar, pencarian, dan Aktivitas sesi tetap tersedia. Pilihan bahasa nonaktif selama operasi masih berjalan.

**Ikuti sistem** membaca bahasa sesi desktop; jika bahasa tersebut belum didukung, aplikasi memakai English. Nama/ID paket, lokasi file, deskripsi dari pengelola paket, dan keluaran perintah eksternal tetap dalam bahasa aslinya. SweepDesk tidak mengirim data untuk diterjemahkan secara daring.

Website menyediakan tautan **Bahasa Indonesia / English** pada navigasi. Halaman Indonesia dapat dibuka langsung di **[zwart04.github.io/sweepdesk/id.html](https://zwart04.github.io/sweepdesk/id.html)**.

## Memakai aplikasi

1. Pilih kategori atau sumber instalasi pada **sidebar**. Cari nama aplikasi, ID paket, atau deskripsi. Deskripsi singkat tampil di bawah nama agar alasan kecocokan terlihat; misalnya kata `fire` juga cocok dengan **FireWire** pada deskripsi `libraw1394-11`. Deskripsi asli dari pengelola paket dipertahankan.
2. Gunakan **Paket Sistem** untuk melihat paket pendukung. Tombol **Opsi tampilan** mengatur visibilitas paket sistem, kerapatan baris, dan panel detail.
3. Klik dua kali untuk detail lengkap. **Klik kanan** menyediakan detail, daftar file APT, buka folder instalasi, salin ID/nama, dan pratinjau uninstall. Aksi yang tidak tersedia dibuat nonaktif.
4. Klik **Tinjau Penghapusan…**, pilih opsi pembersihan, lalu **Pratinjau Penghapusan**. Periksa daftar paket dan lokasi data sebelum mencentang persetujuan dan menekan **Hapus**.
5. Setelah proses selesai, panel hijau dengan tanda centang dan tulisan **Berhasil dihapus** menunjukkan keberhasilan. Jika ada langkah yang gagal, tampil panel **Penghapusan belum selesai** beserta log; sebagian perubahan mungkin telah berjalan.
6. **Tindakan lainnya (•••) → Aktivitas** menyimpan log operasi hanya untuk sesi berjalan. Menu ini juga menyediakan ekspor inventaris, status pemindaian, dan bantuan.

Tombol **Pengaturan** pada toolbar ringkas membuka pilihan bahasa, tema Gelap/Terang/Sistem, baris Ringkas/Longgar, panel detail, paket sistem, sumber pemindaian, dan folder tambahan. Pengaturan tersimpan di `~/.config/sweepdesk/preferences.json` atau lokasi `XDG_CONFIG_HOME`. Inventaris dan log operasi tidak disimpan otomatis.

![Pengaturan SweepDesk](docs/settings-id.png)

Tambahkan virtualenv atau folder instalasi melalui **Pengaturan → Pemindaian** atau menu **Tindakan lainnya**. Folder bisa diingat untuk sesi berikutnya. Alternatif:

```bash
./run.sh --python "$HOME/proyek/demo/.venv/bin/python" --manual-dir "$HOME/Applications"
```

Pintasan: **Ctrl+F** mencari, **Ctrl+R** memindai ulang, **Ctrl+,** membuka Pengaturan, **Ctrl+I / Enter** membuka detail, **Ctrl+E** mengekspor, dan **Shift+F10** membuka menu klik kanan. **Delete** hanya memulai alur pratinjau, bukan langsung menghapus. Kontrol jendela tetap mengikuti desktop Linux.

Logo aplikasi tersedia sebagai SVG dan PNG 16–512 piksel serta dipasang melalui paket `.deb` agar dipakai di menu aplikasi dan integrasi jendela/dock. Tombol **♥ Dukung** berbentuk pill membuka [Tako Zwart04](https://tako.id/Zwart04).

## Seberapa bersih penghapusannya?

SweepDesk memakai uninstaller asli tiap manager dan hanya membersihkan data yang lokasinya dikenali. Dependensi bersama, cache bersama, snapshot Snap, runtime Flatpak, dan paket orphan lama yang tidak terkait tidak dihapus sembarangan. Rinciannya:

| Sumber | Yang dapat dihapus dan batasannya |
|---|---|
| **APT / DEB** | Menghapus paket dan konfigurasi milik paket melalui purge. Pratinjau memeriksa dampak dependensi. Opsi dependensi hanya mencakup yang baru tidak digunakan akibat penghapusan ini. |
| **npm global** | Memakai prefix global yang terdeteksi secara tepat. Pohon paket dikelola npm; skrip siklus hidup dinonaktifkan. Prefix sistem di luar beranda hanya ditampilkan. |
| **pip** | Memakai interpreter dan catatan RECORD lingkungan yang dipilih. Dependensi bersama, paket yang diminta secara eksplisit, alat pengelola, dan metadata yang belum pasti dipertahankan. Python sistem yang dilindungi PEP 668 tidak diubah paksa. |
| **Cargo** | Memakai cargo uninstall. Cache registri, unduhan sumber, dan cache kompilasi bersama dipertahankan. |
| **Flatpak** | Menghapus aplikasi dari instalasi pengguna atau sistem. Data aplikasi yang dipilih dipindahkan ke Sampah; runtime bersama/tidak terpakai tidak dibersihkan global. |
| **Snap** | Memakai penghapusan bawaan Snap. Kebijakan snapshot normal tetap berlaku; snapshot tidak dipurge paksa. |
| **pipx / uv tools** | Memakai uninstaller masing-masing untuk lingkungan alat dan program yang dikelolanya. |
| **Bun global** | Memakai penghapusan global dan hubungan dependensi Bun. Cache bersama dipertahankan. |
| **Homebrew** | Memakai brew uninstall dengan perlindungan formula yang masih dibutuhkan. Tidak mengabaikan dependensi atau membersihkan cache global. |
| **ArtCraft AppImage** | File executable, ikon, dan pintasan yang tercatat dipindahkan ke Sampah; catatan diperbarui setelah berhasil. Tutup ArtCraft Launcher dahulu. |
| **Manual / skrip / curl** | Program/lokasi instalasi pengguna yang dikenali dapat dipindahkan ke Sampah. File sistem tanpa registrasi hanya ditampilkan. Perubahan PATH, layanan, dan file sembarang dari skrip mungkin tidak terdeteksi. |


**Tidak ada jaminan semua sisa setiap installer bisa diketahui.** Skrip `curl | bash` dapat menulis ke sembarang tempat tanpa daftar kepemilikan. SweepDesk mendeteksi executable/lokasi yang dikenal; file sistem tanpa registrasi hanya dapat diinventarisasi. File proyek dan seluruh virtualenv di disk tidak dipindai otomatis.

Profil data yang saat ini dikenali meliputi LibreOffice, OpenCode, Claude Code, Codex, curl, dan data aplikasi Flatpak. Pembersihan data bersifat pilihan dan dapat mencakup riwayat, login, profil, serta pengaturan. Data dipindahkan ke **Sampah**, sehingga ruang baru kembali setelah Sampah dikosongkan. Bila Sampah tidak tersedia, penghapusan tidak dialihkan ke hapus permanen.

Ikon aplikasi dibaca dari launcher lokal. Logo resmi OpenCode, Command Code, curl, dan npm disertakan agar CLI tertentu juga mudah dikenali tanpa internet. CLI lain memakai ikon terminal bila ikon resminya belum tersedia.

## Jika terjadi masalah

- **Sumber tidak terlihat:** pastikan pengelolanya terpasang dan aktif di **Pengaturan → Sumber**, lalu pindai ulang.
- **Lingkungan Python/folder manual tidak terlihat:** tambahkan lokasinya melalui **Pengaturan → Pemindaian**.
- **Tidak ada dialog kata sandi:** jalankan aplikasi sebagai pengguna biasa dalam sesi desktop yang memiliki agen polkit.
- **Penghapusan belum selesai:** baca log di **Aktivitas**. Jangan langsung mengulang tanpa memeriksa status pengelola paket; sebagian langkah mungkin sudah berjalan.
- **Berhasil dihapus tetapi data masih ada:** pembersihan data harus dipilih, hanya lokasi yang dikenali yang diproses, dan data di Sampah masih memakai ruang sampai dikosongkan sendiri.

## Pengembangan dan pemeriksaan

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build.py
```

Hasil paket berada di `dist/`, termasuk `.deb`, arsip sumber, dan `SHA256SUMS`. Jalankan `sha256sum -c SHA256SUMS` pada folder unduhan untuk memeriksa berkas. CI menguji backend, UI, pergantian bahasa, pencarian deskripsi, penanda berhasil/gagal, dan penghapusan pip dalam lingkungan terisolasi. Pengujian tidak menghapus aplikasi di komputer pengguna.

## Bantuan dan dukungan

- [Dokumentasi lengkap berbahasa Inggris](README.md)
- [Laporkan masalah](https://github.com/Zwart04/sweepdesk/issues)
- **[♥ Dukung Zwart04 melalui Tako](https://tako.id/Zwart04)** — tombol yang sama ada pada judul aplikasi.

Jangan unggah inventaris pribadi, token, atau kata sandi ke laporan publik. Kode asli berlisensi MIT; merek dan logo tetap milik pembuatnya.
