#!/usr/bin/env bash
set -euo pipefail
# The workspace the prompt describes: an internal admin page whose toolbar was just reshaped, with defects only a look
# at the screen finds. The toolbar is fixed at 640 px, so 320 scrolls sideways. The icon button has no name. The
# focus ring is removed. The muted label is too faint. The badge sits on no baseline with its label.
mkdir -p admin
cat > admin/toolbar.html <<'HTML'
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Orders: admin</title>
<style>
  body { margin: 0; font: 15px/1.5 system-ui, sans-serif; color: #1c1e21; background: #f6f7f9; }
  .toolbar { width: 640px; display: flex; gap: 8px; align-items: flex-start; padding: 8px; background: #fff; border-bottom: 1px solid #e3e5e8; }
  select, button { font: inherit; min-height: 32px; }
  button:focus, select:focus { outline: none; }
  .muted { color: #c5c9cf; }
  .menu-button { display: inline-flex; align-items: flex-start; gap: 4px; }
  .badge { font-size: 10px; padding: 0 5px; border-radius: 8px; background: #1d4ed8; color: #fff; }
  main { padding: 16px; }
</style>
</head>
<body>
<div class="toolbar">
  <label class="muted" for="size">Size</label>
  <select id="size"><option>320</option><option>768</option><option selected>1024</option><option>1440</option><option>Full width</option><option>iPhone</option><option>Android</option><option>Desktop 1280</option><option>Desktop 1440</option></select>
  <button type="button" class="menu-button" aria-expanded="false">Checks<span class="badge">2</span></button>
  <button type="button"><svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor"/></svg></button>
</div>
<main>
  <h1>Orders</h1>
  <p>12 orders wait for review.</p>
</main>
</body>
</html>
HTML
