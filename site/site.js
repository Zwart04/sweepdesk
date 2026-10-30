// SPDX-FileCopyrightText: 2026 Zwart04
// SPDX-License-Identifier: GPL-3.0-or-later
// SweepDesk: see LICENSE for copying terms and warranty disclaimer.
const indonesian = document.documentElement.lang === 'id';
const words = indonesian ? {open:'Buka navigasi',close:'Tutup navigasi',copied:'Disalin',copy:'Salin',success:'Perintah pemasangan berhasil disalin.',fallback:'Pilih perintah di atas dan salin dengan keyboard.',version:'Versi '} : {open:'Open navigation',close:'Close navigation',copied:'Copied',copy:'Copy',success:'Installation command copied.',fallback:'Select the command above and copy it with your keyboard.',version:'Version '};
const toggle = document.querySelector('.mobile-toggle');
const navigation = document.querySelector('#nav-links');
toggle.addEventListener('click', () => {
  const open = toggle.getAttribute('aria-expanded') !== 'true';
  toggle.setAttribute('aria-expanded', String(open));
  toggle.setAttribute('aria-label', open ? words.close : words.open);
  navigation.classList.toggle('open', open);
});
navigation.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
  navigation.classList.remove('open');
  toggle.setAttribute('aria-expanded', 'false');
  toggle.setAttribute('aria-label', words.open);
}));

document.querySelector('#copy-command').addEventListener('click', async event => {
  const button = event.currentTarget;
  const text = document.querySelector('#install-command').textContent;
  const status = document.querySelector('#copy-status');
  try {
    if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text);
    else {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(document.querySelector('#install-command'));
      selection.removeAllRanges(); selection.addRange(range);
      if (!document.execCommand('copy')) throw new Error('Copy unavailable');
      selection.removeAllRanges();
    }
    button.textContent = words.copied;
    status.textContent = words.success;
    setTimeout(() => { document.querySelector('#copy-command').textContent = words.copy; }, 1800);
  } catch {
    status.textContent = words.fallback;
  }
});

let latestVersion = '0.5.5';
const downloadURLs = {};
const systemPicker = document.querySelector('#download-system');
const packageFile = system => ({deb:`sweepdesk_${latestVersion}_all.deb`,rpm:`sweepdesk-${latestVersion}-1.fedora.noarch.rpm`,suse:`sweepdesk-${latestVersion}-1.opensuse.noarch.rpm`,arch:`sweepdesk-${latestVersion}-1-any.pkg.tar.zst`,portable:`sweepdesk-${latestVersion}.tar.gz`})[system];
function selectDownload() {
  const system=systemPicker.value;
  const file=packageFile(system);
  const command={deb:`sudo apt install ./${file}`,rpm:`sudo dnf install ./${file}`,suse:`sudo zypper install ./${file}`,arch:`sudo pacman -U ./${file}`,portable:`./install.sh`}[system];
  document.querySelector('#install-command').textContent=command;
  const link=document.querySelector('[data-selected-download]');
  link.href=downloadURLs[system] || 'https://github.com/Zwart04/sweepdesk/releases/latest';
  link.textContent=(indonesian?'Unduh ':'Download ')+(system==='portable'?(indonesian?'arsip portabel':'portable archive'):system==='deb'?'.deb':system==='arch'?'Arch (.pkg.tar.zst)':'.rpm');
  document.querySelector('#source-note').hidden=system!=='portable';
  document.querySelector('#copy-status').textContent='';
}
systemPicker.addEventListener('change',selectDownload);
selectDownload();
async function loadRelease() {
  try {
    const response = await fetch('https://api.github.com/repos/Zwart04/sweepdesk/releases/latest', {cache: 'no-store'});
    if (!response.ok) return;
    const release = await response.json();
    const version = String(release.tag_name || '').replace(/^v/, '');
    if (!/^\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.-]+)?$/.test(version)) return;
    document.querySelectorAll('[data-version]').forEach(node => { node.textContent = words.version + version; });
    latestVersion=version;
    const files = {rpm:asset=>asset.name.endsWith('.fedora.noarch.rpm'),suse:asset=>asset.name.endsWith('.opensuse.noarch.rpm'),arch:asset=>asset.name.endsWith('-any.pkg.tar.zst'),recipe:asset=>asset.name==='PKGBUILD',deb: asset => asset.name.endsWith('_all.deb'), portable: asset => asset.name.endsWith('.tar.gz'), checksums: asset => asset.name === 'SHA256SUMS'};
    for (const [type, matches] of Object.entries(files)) {
      const asset = Array.isArray(release.assets) && release.assets.find(matches);
      if (asset && String(asset.browser_download_url).startsWith('https://github.com/Zwart04/sweepdesk/releases/download/')) {
        downloadURLs[type]=asset.browser_download_url;
        document.querySelectorAll(`[data-download="${type}"]`).forEach(link => { link.href = asset.browser_download_url; });
      }
    }
    selectDownload();
  } catch { /* Release-page links remain usable if the API is unavailable. */ }
}
loadRelease();
