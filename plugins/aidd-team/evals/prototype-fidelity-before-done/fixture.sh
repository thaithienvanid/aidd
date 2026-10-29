#!/usr/bin/env bash
set -euo pipefail
# The workspace the prompt describes: a reset-password prototype whose hooks and rules pass, with four defects only a
# read screenshot shows. The card is fixed at 420 px, so 320 scrolls sideways. The hint is cut to one line. The focus
# ring is removed. The dark theme's muted text is too faint.
mkdir -p specs/SPEC-231/design
cat > specs/SPEC-231/design/prototype.html <<'HTML'
<!doctype html>
<html lang="en" data-aidd-prototype="1">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="aidd-spec" content="SPEC-231">
<title>Reset your password: prototype for SPEC-231</title>
</head>
<body>
<p>The design of SPEC-231's prototype. Open it with <code>aidd prototype specs/SPEC-231/design/prototype.html</code>.</p>
<template id="product">
<style id="tokens">
:root { --space-2: 8px; --space-3: 16px; --radius: 8px; --typography-body: 400 1rem/1.5 system-ui, sans-serif; }
:root, :root[data-theme="light"] { --color-surface: #ffffff; --color-text: #1c1e21; --color-text-muted: #5b616b; --color-accent: #1d4ed8; --color-on-accent: #ffffff; --color-danger: #b42318; color-scheme: light; }
:root[data-theme="dark"] { --color-surface: #111317; --color-text: #f3f4f5; --color-text-muted: #3a3d42; --color-accent: #93c5fd; --color-on-accent: #0b1320; --color-danger: #fca5a5; color-scheme: dark; }
</style>
<style id="styles">
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100dvh; font: var(--typography-body); background: var(--color-surface); color: var(--color-text); }
  [hidden] { display: none !important; }
  button:focus, input:focus { outline: none; }
  .device { min-height: 100dvh; }
  .appbar { padding: var(--space-3); }
  .appbar h1 { margin: 0; font-size: 1.5rem; }
  main { padding: 0 var(--space-3) var(--space-3); }
  section[data-screen], section[data-screen] > [data-state] { display: none; }
  section[data-screen].shown, section[data-screen] > [data-state].shown { display: block; }
  section[data-screen] { width: 420px; padding: var(--space-3); border-radius: var(--radius); }
  .hint { color: var(--color-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .field { display: grid; gap: var(--space-2); margin-bottom: var(--space-3); }
  .field input { font: inherit; min-height: 44px; padding: var(--space-2); }
  .button { font: inherit; min-height: 44px; padding: 0 var(--space-3); border: 0; border-radius: var(--radius); background: var(--color-accent); color: var(--color-on-accent); }
  .error { color: var(--color-danger); }
</style>
<div class="device">
  <nav class="tabs" aria-label="Main"><button type="button" data-go="request" data-testid="app-tab-reset">Reset password</button></nav>
  <div class="appbar">
    <button type="button" class="back" data-back data-testid="app-back" hidden><span id="back-label">Back</span></button>
    <h1 id="screen-title" tabindex="-1"></h1>
  </div>
  <main id="main" tabindex="-1">
    <section data-screen="request" data-title="Reset your password" data-initial="empty">
        <p class="hint">Enter the email you signed up with, and we will send you a link that works for the next 30 minutes.</p>
        <div data-state="empty" data-testid="request-empty"></div>
        <div data-state="loading" data-testid="request-loading" aria-busy="true"><p role="status">Sending the link…</p></div>
        <div data-state="error" data-testid="request-error"><p class="error" role="alert">We could not send the link. Check the email, then try again.</p></div>
        <div data-state="success" data-testid="request-success"><p role="status">Check your inbox for the link.</p><button type="button" class="button" data-go="new-password" data-testid="request-open-link">Open the link</button></div>
        <div class="field"><label for="email">Email</label><input id="email" type="email" autocomplete="email" data-testid="request-email"></div>
        <button type="button" class="button" data-go="request/success" data-testid="request-send">Send the link</button>
    </section>
    <section data-screen="new-password" data-title="Choose a new password" data-parent="request" data-initial="empty">
        <div data-state="empty" data-testid="new-password-empty"></div>
        <div data-state="error" data-testid="new-password-error"><p class="error" role="alert">The two passwords do not match.</p></div>
        <div data-state="success" data-testid="new-password-success"><p role="status">Your password is changed. Sign in with it now.</p></div>
        <div class="field"><label for="password">New password</label><input id="password" type="password" autocomplete="new-password" data-testid="new-password-input"></div>
        <button type="button" class="button" data-go="new-password/success" data-testid="new-password-save">Save the password</button>
    </section>
  </main>
</div>
</template>
<script type="application/json" id="fixtures">
{"product": "Reset your password"}
</script>
</body>
</html>
HTML
