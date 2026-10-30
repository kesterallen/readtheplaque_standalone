#!/usr/bin/env python3
"""
download_assets.py
==================
Run once to download all frontend dependencies into static/vendor/.
After this, Read The Plaque works with no internet connection at all.

Usage:
    python download_assets.py
"""

import os, re, sys, urllib.request, urllib.error

BASE     = os.path.dirname(os.path.abspath(__file__))
VENDOR   = os.path.join(BASE, 'static', 'vendor')
FONTS    = os.path.join(VENDOR, 'fonts')

os.makedirs(VENDOR, exist_ok=True)
os.makedirs(FONTS,  exist_ok=True)
os.makedirs(os.path.join(VENDOR, 'images'), exist_ok=True)

ASSETS = [
    ('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',                               'leaflet.js'),
    ('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',                              'leaflet.css'),
    ('https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js',   'leaflet.markercluster.js'),
    ('https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css',          'MarkerCluster.css'),
    ('https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css',  'MarkerCluster.Default.css'),
    # Leaflet marker images (referenced by leaflet.css)
    ('https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',                   'images/marker-icon.png'),
    ('https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',                'images/marker-icon-2x.png'),
    ('https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',                 'images/marker-shadow.png'),
    ('https://unpkg.com/leaflet@1.9.4/dist/images/layers.png',                        'images/layers.png'),
    ('https://unpkg.com/leaflet@1.9.4/dist/images/layers-2x.png',                     'images/layers-2x.png'),
]

FONT_URL = (
    'https://fonts.googleapis.com/css2'
    '?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400'
    '&family=Source+Serif+4:opsz,wght@8..60,300;8..60,400;8..60,600'
    '&display=swap'
)


def fetch_bytes(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; Read The Plaque/1.0)'
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def download(url, relpath):
    dest = os.path.join(VENDOR, relpath)
    if os.path.exists(dest):
        print(f'  skip   {relpath}')
        return
    print(f'  fetch  {relpath} … ', end='', flush=True)
    try:
        data = fetch_bytes(url)
    except Exception as e:
        print(f'FAILED ({e})')
        return
    with open(dest, 'wb') as f:
        f.write(data)
    print(f'ok ({len(data)//1024} KB)')


def download_fonts():
    dest = os.path.join(VENDOR, 'fonts.css')
    print('  fetch  fonts.css … ', end='', flush=True)
    try:
        css = fetch_bytes(FONT_URL).decode('utf-8')
    except Exception as e:
        print(f'FAILED ({e})')
        return

    woff2_urls = re.findall(r'url\((https://[^)]+\.woff2[^)]*)\)', css)
    downloaded = 0
    for wurl in woff2_urls:
        # safe filename from last path component, strip query string
        fname = re.sub(r'[^a-zA-Z0-9._-]', '_', wurl.split('/')[-1].split('?')[0])
        local = os.path.join(FONTS, fname)
        if not os.path.exists(local):
            try:
                data = fetch_bytes(wurl)
                with open(local, 'wb') as f:
                    f.write(data)
                downloaded += 1
            except Exception:
                pass  # font missing won't break layout
        css = css.replace(wurl, f'fonts/{fname}')

    with open(dest, 'w') as f:
        f.write(css)
    print(f'ok ({len(woff2_urls)} fonts, {downloaded} downloaded)')


def patch_leaflet_css():
    """Fix leaflet.css image paths to be relative to the vendor folder."""
    path = os.path.join(VENDOR, 'leaflet.css')
    if not os.path.exists(path):
        return
    with open(path) as f:
        css = f.read()
    # Leaflet ships with relative image paths already; just ensure no absolute CDN refs
    patched = re.sub(
        r'url\(https://[^)]*leaflet[^)]*/(images/[^)]+)\)',
        r'url(\1)',
        css
    )
    if patched != css:
        with open(path, 'w') as f:
            f.write(patched)
        print('  patch  leaflet.css (image paths)')


def main():
    print('\nRead The Plaque — downloading frontend assets for offline use\n')

    print('JS + CSS:')
    for url, rel in ASSETS:
        download(url, rel)

    print('\nFonts:')
    download_fonts()

    print('\nPatching CSS:')
    patch_leaflet_css()

    print('\n✓  All done!  static/vendor/ is ready.')
    print('   Run "python app.py" — no internet needed.\n')


if __name__ == '__main__':
    main()
