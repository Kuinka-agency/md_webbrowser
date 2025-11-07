# Overlay/Cookie Banner Mitigation Playbook
_Last updated: 2025-11_

We minimize non-content chrome in three layers, ordered by robustness:

## 1) Network-level filtering (preferred)
Use a rule engine to classify and block requests for ads/overlays/trackers, including CMP scripts.

- Engine: **python-adblock** (Rust core, EasyList syntax). Load EasyList + EasyPrivacy + cookie/consent filterlists.   
- Cookie/consent: include **EasyList Cookie List** (successor to “I don’t care about cookies” filters). 
- Playwright hook: `page.route("**/*", handler)`; consult the adblock engine with URL + type → `continue()` or `abort()`.

**Why this first?** It removes overlay scripts before they run, avoiding flaky selector hunts.

## 2) CSS-level hides (deterministic, site-agnostic)
Inject a scoped stylesheet _after_ navigation completes (and before sweeps) to hide common overlays and sticky elements:

```css
[aria-modal="true"], [role="dialog"][aria-label*="consent" i], .cookie, .consent, .gdpr, .cmp, .overlay,
[style*="z-index"][role="dialog"], [data-testid*="cookie" i],
header[style*="position:fixed"], [style*="position:sticky"]
{ display: none !important }
````

* Keep a **versioned** blocklist with allowlist exceptions per domain in `docs/blocklist.json`, referenced by manifest.

## 3) DOM heuristics (surgical)

As a last resort, auto-detect off-screen/sticky chrome and hide:

* Candidates: elements with `position: fixed|sticky`, large `z-index`, or size >25% of viewport height.
* Defer until after first sweep to avoid breaking layout; record each hidden selector in `manifest.hidden[]` for reproducibility.

## QA & Safety

* Never click “reject/accept” on CMPs automatically (legal ambiguity, anti-automation traps).
* If hides change layout significantly (detected via `scrollHeight` shrink), redo sweep with longer settle per `manifest.capture.retries`.

## References

* Adblock engine (Python bindings).
* EasyList Cookie List.
