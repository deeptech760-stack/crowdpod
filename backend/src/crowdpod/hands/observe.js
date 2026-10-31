// Runs in the page. Tags visible interactive elements with stable ids and returns
// what a person would see in the current viewport.
() => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const inView = (r) => r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
  const shown = (el) => {
    // checkVisibility also catches parents that are transparent or still fading in
    if (el.checkVisibility) return el.checkVisibility({ opacityProperty: true, visibilityProperty: true });
    const s = getComputedStyle(el);
    return s.visibility !== "hidden" && s.display !== "none" && parseFloat(s.opacity || "1") > 0.05;
  };
  const clean = (t) => (t || "").replace(/\s+/g, " ").trim();
  // A person can only click what's really on top: skip links inside closed menus, under sticky
  // bars or overlays, and anything marked hidden from assistive technology.
  const reachable = (el, r) => {
    if (el.closest('[aria-hidden="true"], [inert]')) return false;
    const x = Math.min(Math.max(r.left + r.width / 2, 0), vw - 1);
    const y = Math.min(Math.max(r.top + r.height / 2, 0), vh - 1);
    const top = document.elementFromPoint(x, y);
    return !!top && (top === el || el.contains(top) || top.contains(el));
  };

  let next = Number(document.documentElement.dataset.cpNext || "1");
  const selector = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], [role=tab], [onclick]';
  const elements = [];
  for (const el of document.querySelectorAll(selector)) {
    const r = el.getBoundingClientRect();
    if (!inView(r) || !shown(el) || !reachable(el, r)) continue;
    if (!el.dataset.cpId) el.dataset.cpId = "e" + next++;
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute("role") || (tag === "a" ? "link" : tag === "input" ? `input:${el.type}` : tag);
    const label = clean(el.getAttribute("aria-label") || el.innerText || el.value || el.placeholder || el.title || el.getAttribute("alt")).slice(0, 80);
    if (!label && !tag.startsWith("input") && tag !== "select" && tag !== "textarea") continue;
    elements.push({ id: el.dataset.cpId, role, label: label || "(empty field)", x: Math.round(r.x), y: Math.round(r.y) });
  }
  document.documentElement.dataset.cpNext = String(next);

  const parts = [];
  const content = []; // text that isn't inside a link or button: headings, prices, paragraphs
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let total = 0;
  while (walker.nextNode() && total < 2500) {
    const node = walker.currentNode;
    const text = clean(node.textContent);
    const parent = node.parentElement;
    if (!text || !parent || ["SCRIPT", "STYLE", "NOSCRIPT"].includes(parent.tagName)) continue;
    if (!inView(parent.getBoundingClientRect()) || !shown(parent)) continue;
    parts.push(text);
    if (!parent.closest(selector)) content.push(text);
    total += text.length + 1;
  }

  const doc = document.scrollingElement || document.documentElement;
  return {
    url: location.href,
    title: document.title,
    scroll_y: Math.round(doc.scrollTop),
    scroll_max: Math.max(0, Math.round(doc.scrollHeight - vh)),
    text: parts.join(" ").slice(0, 2500),
    content: content.join(" ").slice(0, 2500),
    elements,
  };
}
