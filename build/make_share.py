#!/usr/bin/env python3
"""
Build the shareable agent page.

Produces share/index.html: one self-contained file that IS the agent - full app
plus chat, with all 322 stations embedded - so it works with no server, no
sign-up and no install, on any browser on any device.

Adds on top of the PWA:
  - Open Graph / Twitter tags so WhatsApp, iMessage, Slack and X render a rich
    preview card with the og-image
  - a welcome overlay (no login gate - a share link must not demand a sign-up)
  - an "Use it in your AI" sheet with deep links and MCP setup steps
  - PWA install handling, with iOS-specific Add-to-Home-Screen instructions
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
OUT = os.path.join(ROOT, "share")

SITE_NAME = "EV Charge India"
TITLE = "EV Charge India - ask about any EV charger in India"
DESC = ("Find EV charging stations across India - connectors, charging speed, "
        "price, payment methods and maps. Works offline, on any device.")

# ---------------------------------------------------------------------------
# 1. share overlay markup
# ---------------------------------------------------------------------------
WELCOME = """
<!-- ============ SHARE WELCOME ============ -->
<section id="welcome" class="welcome">
  <div class="w-card">
    <div class="w-logo">&#9889;</div>
    <h1>EV Charge India</h1>
    <p class="w-sub">Ask about any EV charger in India &mdash; connectors, charging speed,
       price, payments and maps.</p>
    <div class="w-chips">
      <span>322 stations</span><span>24 operators</span><span>Works offline</span>
    </div>
    <button class="btn primary" id="w-agent">Ask the agent</button>
    <button class="btn ghost" id="w-browse">Browse the map</button>
    <button class="btn ghost" id="w-install" hidden>Install as an app</button>
    <button class="btn ghost" id="w-ai">Use it inside your AI &rsaquo;</button>
    <p class="w-note">No sign-up. Opens in any browser &mdash; phone, tablet or desktop.</p>
  </div>
</section>

<!-- ============ USE IT IN YOUR AI ============ -->
<section id="aihelp" class="sheet">
  <div class="sheet-head">
    <button id="ai-close" class="icon-btn">&lsaquo;</button>
    <span>Use it inside your AI</span>
    <span style="width:34px"></span>
  </div>
  <div class="sheet-body" id="ai-body"></div>
</section>
"""

WELCOME_CSS = """
/* ---------- share welcome ---------- */
.welcome { position: fixed; inset: 0; z-index: 2000; background: linear-gradient(165deg,#0B8A5E 0%,#076B49 60%,#054B34 100%);
  display: flex; align-items: center; justify-content: center; padding: 22px; overflow-y: auto; }
.welcome.hide { display: none; }
.w-card { width: 100%; max-width: 420px; text-align: center; color: #fff; padding: 8px 0 20px; }
.w-logo { width: 70px; height: 70px; border-radius: 21px; background: rgba(255,255,255,.16);
  display: grid; place-items: center; font-size: 34px; margin: 0 auto 16px; }
.welcome h1 { margin: 0 0 8px; font-size: 27px; letter-spacing: -.4px; }
.w-sub { margin: 0 auto 18px; font-size: 15px; line-height: 1.5; opacity: .9; max-width: 340px; }
.w-chips { display: flex; gap: 7px; justify-content: center; flex-wrap: wrap; margin-bottom: 22px; }
.w-chips span { font-size: 11.5px; padding: 5px 11px; border-radius: 999px;
  border: 1px solid rgba(255,255,255,.5); background: rgba(0,0,0,.10); }
.welcome .btn { max-width: 320px; margin: 0 auto 9px; display: block; }
.welcome .btn.primary { background: #fff; color: #076B49; }
.welcome .btn.primary:active { background: #EAF5F0; }
.welcome .btn.ghost { color: rgba(255,255,255,.92); }
.welcome .btn.ghost:hover { background: rgba(255,255,255,.10); }
.w-note { font-size: 11.5px; opacity: .7; margin: 14px 0 0; }
.ai-block { background: #F7FAF9; border: 1px solid var(--line); border-radius: 12px; padding: 13px; margin-bottom: 11px; }
.ai-block h4 { margin: 0 0 6px; font-size: 14px; }
.ai-block p { margin: 0 0 9px; font-size: 13px; color: var(--muted); line-height: 1.5; }
.ai-links { display: flex; flex-wrap: wrap; gap: 8px; }
.ai-link { flex: 1 1 46%; text-align: center; padding: 11px; border-radius: 10px; text-decoration: none;
  font-weight: 600; font-size: 13.5px; background: var(--card); border: 1px solid var(--line); color: var(--ink); }
.ai-link.g { background: var(--green); color: #fff; border-color: var(--green); }
.ai-code { background: #12211C; color: #D6EFE4; border-radius: 10px; padding: 11px 12px; font-size: 11.5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; overflow-x: auto; white-space: pre; line-height: 1.5; }
.ai-copy { margin-top: 8px; font-size: 12.5px; background: var(--green-lt); color: var(--green-dk);
  border: 0; border-radius: 9px; padding: 9px 12px; font-weight: 650; cursor: pointer; width: 100%; }
"""

SHARE_SW = """/* EV Charge India - share page service worker.
   Caches only files that actually exist in this build, and adds them one at a
   time so a single missing asset cannot abort the install. */
const CACHE = "evcharge-share-v1";
const SHELL = [
  "./", "index.html", "manifest.webmanifest",
  "icon-192.png", "icon-512.png", "og-image.png"
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  // never cache map tiles - they are large and need a live network anyway
  if (/tile\\.openstreetmap\\.org/.test(url.host)) return;
  e.respondWith(
    caches.match(e.request).then(hit => hit || fetch(e.request).then(res => {
      if (res.ok && url.origin === location.origin) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
      }
      return res;
    }).catch(() => caches.match("index.html")))
  );
});
"""

WELCOME_JS = """
/* ---------------- share page behaviour ---------------- */
document.addEventListener('DOMContentLoaded', function () {
  const SHARE = true;
  const welcome = document.getElementById('welcome');
  const aihelp = document.getElementById('aihelp');

  // A share link must never demand a sign-up: go straight in as a guest.
  function enterAsGuest() {
    try {
      document.getElementById('login').classList.remove('active');
      document.getElementById('app').classList.add('active');
      if (typeof state !== 'undefined') state.user = { mobile: 'guest' };
      if (typeof enterApp === 'function') enterApp();
    } catch (e) { /* app still usable without this */ }
  }

  function goTo(view) {
    const btn = document.querySelector('.nav-btn[data-view="' + view + '"]');
    if (btn) btn.click();
  }

  document.getElementById('w-agent').onclick = () => {
    welcome.classList.add('hide'); enterAsGuest(); goTo('agent');
  };
  document.getElementById('w-browse').onclick = () => {
    welcome.classList.add('hide'); enterAsGuest(); goTo('list');
  };
  document.getElementById('w-ai').onclick = () => {
    welcome.classList.add('hide'); enterAsGuest(); renderAI(); aihelp.classList.add('open');
  };
  document.getElementById('ai-close').onclick = () => aihelp.classList.remove('open');

  // ---- install handling ----
  let deferredPrompt = null;
  const installBtn = document.getElementById('w-install');
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault(); deferredPrompt = e; installBtn.hidden = false;
  });
  installBtn.onclick = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    deferredPrompt = null; installBtn.hidden = true;
  };
  window.addEventListener('appinstalled', () => { installBtn.hidden = true; });

  const ua = navigator.userAgent;
  const isIOS = /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches
                       || window.navigator.standalone === true;
  if (isIOS && !isStandalone) installBtn.hidden = false;   // iOS has no prompt event

  // ---- the "use it in your AI" sheet ----
  const PROMPT = 'I want to find EV charging stations in India. Ask me my city or highway and tell me which connectors, charging speeds, prices and payment methods are available.';
  const base = location.origin === 'null' ? '' : location.href.split('#')[0].split('?')[0];

  function renderAI() {
    const q = encodeURIComponent(PROMPT);
    const installSteps = isIOS
      ? 'On iPhone/iPad: tap the Share button in Safari, then <b>Add to Home Screen</b>.'
      : isStandalone
        ? 'Already installed as an app. Nice.'
        : 'On Android/desktop Chrome or Edge: open the browser menu and choose <b>Install app</b> (or use the Install button above).';

    document.getElementById('ai-body').innerHTML = `
      <div class="ai-block">
        <h4>This page already is the agent</h4>
        <p>You do not need any AI app to use it. The chat, the map and all 322 stations run
           right here, offline, in this browser. Scroll to the Agent tab and ask away.</p>
      </div>

      <div class="ai-block">
        <h4>Install it as an app</h4>
        <p>${installSteps} It then opens full-screen like a native app and keeps working
           without a network.</p>
      </div>

      <div class="ai-block">
        <h4>Ask your own AI about it</h4>
        <p>These open your AI with the question pre-filled. Your AI will answer from general
           knowledge - it will not have this station data unless you connect it (see below).</p>
        <div class="ai-links">
          <a class="ai-link g" href="https://chatgpt.com/?q=${q}" target="_blank" rel="noopener">ChatGPT</a>
          <a class="ai-link" href="https://claude.ai/new?q=${q}" target="_blank" rel="noopener">Claude</a>
          <a class="ai-link" href="https://www.perplexity.ai/search?q=${q}" target="_blank" rel="noopener">Perplexity</a>
          <a class="ai-link" href="https://copilot.microsoft.com/?q=${q}" target="_blank" rel="noopener">Copilot</a>
          <a class="ai-link" href="https://gemini.google.com/app" target="_blank" rel="noopener">Gemini</a>
        </div>
      </div>

      <div class="ai-block">
        <h4>Give your AI the real station data (MCP)</h4>
        <p>Claude, ChatGPT, Cursor, Copilot and Gemini can call this agent as a tool over the
           Model Context Protocol. Deploy the agent service once, then add it as a connector.
           The endpoint looks like:</p>
        <div class="ai-code">https://your-agent-host.example.com/mcp</div>
        <button class="ai-copy" id="copy-mcp">Copy endpoint</button>
      </div>

      <div class="ai-block">
        <h4>Share this link</h4>
        <p>Send it over WhatsApp, iMessage or email. It previews with a card and opens the
           agent on any device - Android, iPhone, Windows, macOS or Linux.</p>
        <div class="ai-code" id="share-url">${base || 'host this page, then the URL appears here'}</div>
        <button class="ai-copy" id="copy-url">Copy link</button>
      </div>

      <p class="fineprint center">Station data is a directory, not a live feed. Confirm status in
         the operator's own app before you plug in.</p>
    `;

    const copy = (text, btn) => {
      navigator.clipboard?.writeText(text).then(() => {
        const old = btn.textContent; btn.textContent = 'Copied';
        setTimeout(() => { btn.textContent = old; }, 1500);
      }).catch(() => {});
    };
    const cb = document.getElementById('copy-url');
    if (cb) cb.onclick = () => copy(base, cb);
    const cm = document.getElementById('copy-mcp');
    if (cm) cm.onclick = () => copy('https://your-agent-host.example.com/mcp', cm);
  }

  // reopen the sheet from the header
  const helpBtn = document.createElement('button');
  helpBtn.className = 'icon-btn'; helpBtn.title = 'About / share'; helpBtn.textContent = '?';
  helpBtn.style.marginLeft = '6px';
  helpBtn.onclick = () => { renderAI(); aihelp.classList.add('open'); };
  const locate = document.getElementById('btn-locate');
  if (locate && locate.parentNode) locate.parentNode.insertBefore(helpBtn, locate);

  renderAI();
  window.__EV_SHARE = SHARE;
});
"""


def build():
    html = open(os.path.join(APP, "index.html"), encoding="utf-8").read()
    css = open(os.path.join(APP, "styles.css"), encoding="utf-8").read()
    data = open(os.path.join(APP, "data.js"), encoding="utf-8").read()
    appjs = open(os.path.join(APP, "app.js"), encoding="utf-8").read()

    # ---- head: social preview tags ----
    og = f"""<meta name="description" content="{DESC}" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="{SITE_NAME}" />
<meta property="og:title" content="{TITLE}" />
<meta property="og:description" content="{DESC}" />
<meta property="og:image" content="og-image.png" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{TITLE}" />
<meta name="twitter:description" content="{DESC}" />
<meta name="twitter:image" content="og-image.png" />
<meta name="apple-mobile-web-app-title" content="{SITE_NAME}" />"""
    html = html.replace('<link rel="manifest" href="manifest.webmanifest" />',
                        '<link rel="manifest" href="manifest.webmanifest" />\n' + og)

    # ---- inline css + our additions ----
    html = html.replace('<link rel="stylesheet" href="styles.css" />',
                        "<style>\n" + css + "\n" + WELCOME_CSS + "\n</style>")

    # ---- welcome overlay markup before </body> ----
    html = html.replace("</body>", WELCOME + "\n</body>")

    # ---- inline data + app + share js ----
    html = html.replace('<script src="data.js"></script>',
                        "<script>\n" + data + "\n</script>")
    html = html.replace('<script src="app.js"></script>',
                        "<script>\n" + appjs + "\n</script>\n<script>\n" + WELCOME_JS + "\n</script>")

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # sidecar assets (styles/app/data are inlined, so they are NOT cached here)
    for fn in ["manifest.webmanifest", "icon-192.png", "icon-512.png"]:
        src = os.path.join(APP, fn)
        if os.path.exists(src):
            with open(src, "rb") as a, open(os.path.join(OUT, fn), "wb") as b:
                b.write(a.read())

    # A share-specific service worker. The app's own sw.js lists styles.css,
    # app.js and data.js - none of which exist here because they are inlined
    # into index.html - and a failed addAll() aborts the install, which makes
    # the browser discard the registration entirely.
    with open(os.path.join(OUT, "sw.js"), "w", encoding="utf-8") as f:
        f.write(SHARE_SW)

    # title for link previews
    html2 = open(os.path.join(OUT, "index.html"), encoding="utf-8").read()
    html2 = html2.replace("<title>EV Charge India</title>", f"<title>{TITLE}</title>")
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(html2)

    size = os.path.getsize(os.path.join(OUT, "index.html"))
    print(f"share/index.html  {size:,} bytes")
    print("share/ contents:", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    build()
