const toggle = document.querySelector('.mobile-toggle');
const navigation = document.querySelector('#nav-links');
toggle.addEventListener('click', () => {
  const open = toggle.getAttribute('aria-expanded') !== 'true';
  toggle.setAttribute('aria-expanded', String(open));
  toggle.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
  navigation.classList.toggle('open', open);
});
navigation.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
  navigation.classList.remove('open');
  toggle.setAttribute('aria-expanded', 'false');
  toggle.setAttribute('aria-label', 'Open navigation');
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
    button.textContent = 'Copied';
    status.textContent = 'Installation command copied.';
    setTimeout(() => { document.querySelector('#copy-command').textContent = 'Copy'; }, 1800);
  } catch {
    status.textContent = 'Select the command above and copy it with your keyboard.';
  }
});

async function loadRelease() {
  try {
    const response = await fetch('https://api.github.com/repos/Zwart04/sweepdesk/releases/latest', {cache: 'no-store'});
    if (!response.ok) return;
    const release = await response.json();
    const version = String(release.tag_name || '').replace(/^v/, '');
    if (!/^\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.-]+)?$/.test(version)) return;
    document.querySelectorAll('[data-version]').forEach(node => { node.textContent = 'Version ' + version; });
    document.querySelector('#install-command').textContent = `sudo apt install ./sweepdesk_${version}_all.deb`;
    const files = {deb: asset => asset.name.endsWith('_all.deb'), portable: asset => asset.name.endsWith('.tar.gz'), checksums: asset => asset.name === 'SHA256SUMS'};
    for (const [type, matches] of Object.entries(files)) {
      const asset = Array.isArray(release.assets) && release.assets.find(matches);
      if (asset && String(asset.browser_download_url).startsWith('https://github.com/Zwart04/sweepdesk/releases/download/')) {
        document.querySelectorAll(`[data-download="${type}"]`).forEach(link => { link.href = asset.browser_download_url; });
      }
    }
  } catch { /* Release-page links remain usable if the API is unavailable. */ }
}
loadRelease();
