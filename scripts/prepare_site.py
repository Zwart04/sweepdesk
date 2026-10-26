#!/usr/bin/python3
"""Assemble the static GitHub Pages site using the same artwork as the application."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'.work/site-preview'
OUTPUT.mkdir(parents=True,exist_ok=True)
for name in ('index.html','id.html','style.css','site.js'):
    shutil.copy2(ROOT/'site'/name,OUTPUT/name)
assets=OUTPUT/'assets'
assets.mkdir(exist_ok=True)
for source,name in [(ROOT/'assets/sweepdesk.svg','logo.svg'),(ROOT/'docs/screenshot.png','app.png'),(ROOT/'docs/settings.png','settings.png'),(ROOT/'docs/screenshot-id.png','app-id.png'),(ROOT/'docs/settings-id.png','settings-id.png')]:
    shutil.copy2(source,assets/name)
(OUTPUT/'.nojekyll').touch()
print(OUTPUT)
