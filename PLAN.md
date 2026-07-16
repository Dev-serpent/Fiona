# Execution Plan: Fiona Mobile-Responsive UI + Module Completion

**Status: ✅ ALL COMPLETE** — See `devlog.md` Entry 15 for details.

## Overview

**Goal:** Make the Fiona web UI (FionaLocalPages) fully usable from a phone browser (Chrome on Android) and complete the Files Tab and Actions System modules.

**Approach:** Bottom-up — first establish the mobile-responsive shell (CSS + hamburger menu), then adapt each page module, finishing with touch interaction patterns. Companion code patterns are extracted selectively for config atomicity and event bus improvements.

**Target device:** Chrome on Android, 360px–430px viewport width.

---

## Milestones

1. **Milestone 1: Responsive Shell Foundation** — Hamburger overlay sidebar, mobile header, status bar simplification
2. **Milestone 2: Touch Interaction Layer** — Long-press context menus, 44px tap targets, touch gestures
3. **Milestone 3: File Explorer Mobile** — Vertical stacking, mobile-friendly tree/list/preview, drag-drop upload
4. **Milestone 4: Actions Page Completion & Mobile** — Library CRUD completeness review, mobile-optimized tabs + editor
5. **Milestone 5: Cross-Cutting Mobile Polish** — Right panel overlay, modal sizing, toast positioning, WebSocket notifications
6. **Milestone 6: Companion Pattern Extraction** — Atomic config writes, event bus improvements (optional, time-permitting)

---

## Milestone 1: Responsive Shell Foundation

**Objective:** The app shell (sidebar + header + content + status bar) works on phone screens with a hamburger menu overlay.

### Tasks

| ID | Task Description | Dependencies | Priority | Complexity | Affected Files |
|----|------------------|--------------|----------|------------|----------------|
| M1.1 | **Add mobile breakpoints to `layout.css`** — Add `@media (max-width: 768px)` rules: sidebar becomes `position: fixed` overlay with `transform: translateX(-100%)` / `translateX(0)` when open; content area takes full width; status bar simplified to show only clock + connection; header gets hamburger button. | None | **Critical** | M | `css/layout.css`, `css/globals.css` |
| M1.2 | **Add hamburger button to `index.html` header** — Insert a new `<button>` in `.app-header__left` (before breadcrumb) that toggles sidebar visibility on mobile. Only visible `≤ 768px`. Include three-line SVG icon. | None | **Critical** | S | `index.html` |
| M1.3 | **Implement sidebar toggle logic in `app.js`** — Wire hamburger button click to toggle a CSS class `app-main--mobile-sidebar-open` on the `#app-main` element. Close sidebar on nav-item click (mobile only). Add backdrop overlay element. | M1.1, M1.2 | **Critical** | M | `js/app.js` |
| M1.4 | **Add mobile sidebar overlay CSS** — Style the sidebar as a slide-in drawer with semi-transparent backdrop on mobile. Ensure proper z-index layering (backdrop: 40, sidebar: 41). Smooth slide animation. | M1.1 | **High** | M | `css/layout.css` |
| M1.5 | **Simplify status bar on mobile** — Hide status bar on screens `≤ 768px` entirely (reclaim 32px of vertical space). Adjust `#app` grid to 2-row on mobile. | M1.1 | **Medium** | S | `css/layout.css` |
| M1.6 | **Mobile-friendly header** — Reduce header height to 44px on mobile, hide breadcrumb on small screens, show only hamburger + search trigger + notification bell. Hide the "Quick actions..." label from search trigger, show only the icon. | M1.1, M1.2 | **High** | S | `css/layout.css`, `index.html` |
| M1.7 | **Right panel becomes bottom sheet on mobile** — On screens `≤ 768px`, change right panel from grid column to `position: fixed; bottom: 0; left: 0; right: 0` with slide-up animation and max-height 60vh. Add swipe-down-to-dismiss. | M1.1 | **Medium** | L | `css/layout.css`, `js/app.js` |

### Rationale
The shell is the foundation — every page inherits its layout from here. Getting the sidebar, header, and content area right first means all downstream page work benefits immediately. The 768px breakpoint is chosen because it covers phones in both portrait and landscape.

---

## Milestone 2: Touch Interaction Layer

**Objective:** Touch-friendly interactions across the app — long-press context menus, adequate tap targets, scroll behaviors.

### Tasks

| ID | Task Description | Dependencies | Priority | Complexity | Affected Files |
|----|------------------|--------------|----------|------------|----------------|
| M2.1 | **Extend `ContextMenu.js` with long-press support** — Add a `longpress` event detector (300ms hold threshold) that triggers the context menu at the touch position. Must cancel on scroll. Touch context menu should appear at bottom of screen (sheet-style) on mobile instead of near-finger. | None | **Critical** | L | `js/components/ContextMenu.js` |
| M2.2 | **Add `@media (pointer: coarse)` tap target overrides** — In `components.css`, add rules that increase `.c-btn--icon` minimum size to 44×44px, `.nav-item` padding to 12px vertical, `.fe-tree-item` and `.fe-file-item` padding to 12px vertical. | None | **High** | M | `css/components.css` |
| M2.3 | **Add touch-action CSS** — Set `touch-action: pan-y` on scrollable containers (sidebar, file list, content body) to prevent scroll hijacking. Set `touch-action: manipulation` on buttons to eliminate 300ms tap delay. | None | **Medium** | S | `css/globals.css`, `css/layout.css` |
| M2.4 | **Add viewport-aware scroll-to-top on route change** — Already partially implemented in router.js; verify it works with mobile virtual keyboard. | M1.3 | **Low** | S | `js/router.js` |
| M2.5 | **Add focus management for mobile** — When sidebar opens on mobile, trap focus inside it. When modal opens, ensure focus moves to first interactive element. Return focus on close. | M1.3 | **Medium** | M | `js/app.js`, `js/components/ContextMenu.js` |

### Rationale
Context menus triggered by `contextmenu` event are inaccessible on touch devices. The long-press pattern is the standard Android/iOS convention. Making tap targets 44px minimum follows Apple HIG and WCAG 2.5.8 guidelines.

---

## Milestone 3: File Explorer Mobile

**Objective:** The file explorer works on phone screens — vertical stacking, touch-friendly navigation, mobile context menus.

### Tasks

| ID | Task Description | Dependencies | Priority | Complexity | Affected Files |
|----|------------------|--------------|----------|------------|----------------|
| M3.1 | **Mobile layout for file explorer body** — Modify `@media (max-width: 768px)` in `file-explorer.html` template CSS: instead of hiding `.fe-tree-panel` entirely, make it collapsible/expandable. Stack `.fe-body` as `grid-template-columns: 1fr` with tree panel above content panel. Add a toggle button to show/hide tree. | M2.2 | **Critical** | L | `templates/file-explorer.html` (embedded `<style>`) |
| M3.2 | **Mobile toolbar adaptation** — Stack the file-explorer toolbar vertically on mobile: breadcrumbs on its own row, toolbar buttons + search below. Make search input full-width. New file/folder buttons get 44px tap targets. | M3.1 | **High** | M | `templates/file-explorer.html` (embedded `<style>`), `pages/file-explorer.js` |
| M3.3 | **Preview panel mobile layout** — On mobile `≤ 768px`, the preview panel should become a full-screen overlay or bottom sheet (rather than a split panel). Add a close button. User taps file → preview slides up. Swipe down to dismiss. | M3.1 | **High** | L | `templates/file-explorer.html` (embedded `<style>`), `pages/file-explorer.js` |
| M3.4 | **Long-press context menu on file items** — Wire long-press (from M2.1) on `.fe-file-item` elements to show context menu (rename/delete/copy path/download). Use `data-action` attributes. | M2.1 | **High** | M | `pages/file-explorer.js` |
| M3.5 | **Touch-friendly grid view** — On mobile, ensure grid items in `fe-file-grid` have minimum 44×44px tap area, adequate spacing (8px gap), and larger icon sizes (32px). | M3.1 | **Medium** | S | `templates/file-explorer.html` (embedded `<style>`) |
| M3.6 | **Mobile drag-and-drop upload feedback** — On touch devices, drag-and-drop is unreliable. Add a visible "Upload" button in toolbar that triggers a native file input. Keep drag-drop as progressive enhancement. | None | **Medium** | M | `pages/file-explorer.js`, `templates/file-explorer.html` |
| M3.7 | **File tree scroll optimization** — Ensure `.fe-tree` and `.fe-file-list` use `-webkit-overflow-scrolling: touch` (for older Android) and `overscroll-behavior: contain` to prevent pull-to-refresh interference. | None | **Low** | S | `templates/file-explorer.html` (embedded `<style>`) |

### Rationale
File explorer is the most complex existing page (1379 lines). The split-panel layout fundamentally doesn't work on a phone — vertical stacking with collapsible panels is the standard mobile pattern (e.g., VS Code mobile, Files app on iOS). The preview-as-sheet pattern matches user expectations from native file managers.

---

## Milestone 4: Actions Page Completion & Mobile

**Objective:** Verify the Actions page CRUD is complete, then make it mobile-friendly.

### Tasks

| ID | Task Description | Dependencies | Priority | Complexity | Affected Files |
|----|------------------|--------------|----------|------------|----------------|
| M4.1 | **Audit Actions page CRUD completeness** — Review all 3 tabs (Actions/History/Library) against backend API (`handlers/actions.py`). Verify: (a) Library create/edit/delete/save work end-to-end, (b) History loads from CmdTrace, (c) Run with dry-run toggle works. Document any gaps. | None | **Critical** | M | `pages/actions.js`, `server/handlers/actions.py` |
| M4.2 | **Fix any CRUD gaps found in M4.1** — Based on audit, fix broken endpoints or missing frontend wiring. Ensure editor modal save/load cycle works for both new and existing actions. | M4.1 | **Critical** | Variable | `pages/actions.js`, `server/handlers/actions.py` |
| M4.3 | **Mobile tab bar** — On mobile `≤ 768px`, render the Actions/History/Library tabs as a horizontal scrollable tab bar with larger tap targets (44px height). Keep tab labels, add icons inline. | M2.2 | **High** | M | `pages/actions.js`, `templates/actions.html` |
| M4.4 | **Mobile action cards** — On mobile, action cards should stack vertically with full-width Run button. Reduce padding. Ensure the dry-run toggle label is readable (increase font size). | M2.2 | **High** | M | `pages/actions.js` |
| M4.5 | **Mobile editor modal** — On mobile, the action editor modal (textarea for Python code) should be full-screen. Adjust `modal.showModal({ size: 'xl' })` behavior for mobile: use `size: 'fullscreen'` on narrow viewports. | M2.2 | **High** | L | `js/components/Modal.js`, `pages/actions.js` |
| M4.6 | **Mobile history items** — On mobile, history items should show timestamp + status + action name in a compact single-row layout. Expandable result output. Swipe-to-dismiss optional. | M2.2 | **Medium** | M | `pages/actions.js` |
| M4.7 | **Mobile library card actions** — On mobile, the library card action buttons (run/edit/toggle/duplicate/delete) should collapse into an overflow menu (⋯) to save horizontal space. Long-press on card shows context menu. | M2.1 | **Medium** | L | `pages/actions.js` |

### Rationale
Actions is the second priority module. The Library CRUD needs verification before mobile work because it's described as "partially done." The editor modal for Python code is the trickiest mobile UX — a textarea for code editing on a phone is inherently challenging, but full-screen with a larger font is the best vanilla JS approach.

---

## Milestone 5: Cross-Cutting Mobile Polish

**Objective:** Global mobile improvements that affect multiple pages.

### Tasks

| ID | Task Description | Dependencies | Priority | Complexity | Affected Files |
|----|------------------|--------------|----------|------------|----------------|
| M5.1 | **Mobile-optimized modals** — In `Modal.js`, detect viewport width and switch to full-screen modal layout when `≤ 768px`. Adjust `.c-modal` CSS: `max-width: 100vw`, `max-height: 100vh`, `border-radius: 0`, slide-up animation. | M1.1 | **High** | M | `js/components/Modal.js`, `css/components.css` |
| M5.2 | **Toast positioning on mobile** — Move `.c-toast-container` to bottom of screen on mobile (`bottom: 16px` instead of `top: 16px`) to be reachable with thumb. | M1.1 | **Medium** | S | `css/components.css` |
| M5.3 | **Mobile command palette** — On mobile, the command palette (⌘K) should be accessible via a search icon in the header. Render as full-screen overlay with large search input. | M1.6 | **Medium** | M | `js/app.js`, `css/components.css` |
| M5.4 | **Mobile WebSocket notifications** — Ensure toast notifications triggered by WebSocket events display correctly on mobile (proper z-index, not hidden behind sidebar overlay). Verify notification badge updates. | M1.4 | **High** | S | `js/app.js`, `css/components.css` |
| M5.5 | **Scroll performance** — Add `will-change: transform` to scrollable containers. Use `contain: layout style paint` on content area. Ensure no layout thrashing during scroll. | None | **Low** | S | `css/layout.css`, `css/components.css` |
| M5.6 | **Mobile keyboard handling** — When soft keyboard opens on Android, adjust layout to prevent content being hidden. Use `visualViewport` API to detect keyboard. Ensure inputs are scrolled into view. | None | **Medium** | L | `js/app.js` |
| M5.7 | **Test on real device** — Load the UI from phone browser via local network (`http://<host>:8765`). Test all pages, interactions, and edge cases. Document remaining issues. | M1–M5 | **Critical** | M | N/A (testing) |

### Rationale
These are the polish items that make the difference between "it loads on a phone" and "it's usable on a phone." The keyboard handling (M5.6) is particularly important because Android Chrome's virtual keyboard can break fixed-position layouts.

---

## Milestone 6: Companion Pattern Extraction (Optional)

**Objective:** Extract useful patterns from the Companion project into Fiona where they add value, without creating tight coupling.

### Tasks

| ID | Task Description | Dependencies | Priority | Complexity | Affected Files |
|----|------------------|--------------|----------|------------|----------------|
| M6.1 | **Extract atomic file write pattern** — Companion's `config/_watcher.py` or `_merge.py` likely has atomic write logic (write to temp, then rename). Fiona's `actions.py` already does this in `_write_actions_json()`. Verify it's robust (handles crashes mid-write) and add fsync if missing. | None | **Low** | S | `server/handlers/actions.py` |
| M6.2 | **Extract event bus wildcard pattern (conceptual)** — Companion's `SyncEventBus` supports fnmatch wildcards on event types. Fiona's WebSocket event dispatch in `app.js` uses a flat switch statement. Consider whether adding wildcard matching to the JS `api.on()` method would improve maintainability. | None | **Low** | M | `js/api.js` (if pursued) |
| M6.3 | **Extract retry/backoff pattern** — Companion's `_retry.py` has retry logic with backoff. Fiona's WebSocket reconnection already implements exponential backoff. Verify the implementation is solid; if Companion's is better, adopt its pattern. | None | **Low** | S | `js/api.js` (if pursued) |

### Rationale
The Companion project is well-architected but is a plugin framework — most of its code is overkill for Fiona's needs. The atomic writes are already partially implemented. The event bus wildcards are the most architecturally interesting extraction but lowest priority since the current flat dispatch works fine.

---

## Dependencies and Blockers

- **M1.1** is the root dependency — all mobile work depends on responsive shell CSS
- **M2.1** (long-press) is required by M3.4 and M4.7
- **M4.1** must complete before M4.2 (fix gaps before polishing)
- **M3.3** (preview panel mobile) requires M1.7 (right panel as bottom sheet) pattern
- **M5.6** (keyboard handling) is the highest-risk item — Android Chrome keyboard behavior varies by device
- **No external blockers** — all work is self-contained within the Fiona codebase

### Risk: Virtual Keyboard Layout Shift
Android Chrome's virtual keyboard causes `window.innerHeight` to change, which can break fixed-position elements and CSS grid layouts. The `visualViewport` API helps but isn't consistent across devices.
**Mitigation:** Use `position: fixed` elements sparingly. Prefer `position: absolute` within scroll containers. Test on multiple devices.

### Risk: Long-Press Conflicts with Scroll
Long-press on mobile can conflict with scroll gestures on the same element.
**Mitigation:** Cancel long-press if the finger moves more than 10px. Only trigger on elements that have `contextmenu` handlers registered.

### Risk: Modal Code Editor on Mobile
Python code editing in a `<textarea>` on a phone is inherently poor UX.
**Mitigation:** Make the editor full-screen on mobile with a larger font (14px minimum). Accept that editing complex code on a phone will be limited. Consider future integration with a mobile-optimized code editor (CodeMirror mobile) as a later enhancement.

---

## Prioritization Rationale

1. **Critical (must ship):** Responsive shell (M1) and file explorer mobile (M3) — these are the two things the user explicitly asked for and the foundation everything else builds on.
2. **High (important for usability):** Touch interaction layer (M2), actions page mobile (M4), mobile modals and notifications (M5.1, M5.4).
3. **Medium (nice to have):** Bottom sheet panels (M1.7), mobile keyboard handling (M5.6), toast repositioning (M5.2).
4. **Low (polish):** Scroll performance (M5.5), Companion pattern extraction (M6).

---

## Summary: Execution Order

```
Phase 1: M1.1 → M1.2 → M1.3 → M1.4 → M1.6 → M1.5
Phase 2: M2.2 → M2.3 → M2.1 → M2.5
Phase 3: M3.1 → M3.2 → M3.3 → M3.4 → M3.5 → M3.6
Phase 4: M4.1 → M4.2 → M4.3 → M4.4 → M4.5 → M4.6 → M4.7
Phase 5: M5.1 → M5.4 → M5.2 → M5.3 → M5.5 → M5.6
Phase 6: M5.7 (device testing)
Phase 7: M6.1 → M6.3 (optional)
```

**Estimated total effort:** ~40–60 hours of focused development.
**Quick wins (first 4 hours):** M1.1 + M1.2 + M1.3 + M2.2 + M2.3 — this alone makes the sidebar work on mobile with proper tap targets.
