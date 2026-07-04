/* ==========================================================================
   apicatalog.js — Public API Catalog Browser
   ==========================================================================
   Search and browse the public-apis/public-apis catalog of ~1500 free APIs.
   Features live search with category filtering, relevance scoring display,
   detail modal, and catalog refresh.

   Exports: { render(container), mount(container), destroy() }
   Default export: factory for the SPA router.
   ========================================================================== */

import { html } from '../js/components/BaseComponent.js';
import { ICONS } from '../js/components/_icons.js';
import { loadTemplate } from '../js/template-loader.js';
import {
  skeletonCard,
  skeletonText,
  skeletonHeading,
  skeletonButton,
} from '../js/components/LoadingSkeleton.js';

/* ── Module-level State ─────────────────────────────────────────────────── */

const _state = {
  container: null,
  destroyed: false,
  loading: true,
  error: false,
  errorMessage: '',

  // Status
  entryCount: 0,
  lastRefreshed: '—',

  // Categories
  categories: [],
  selectedCategory: '',

  // Search
  query: '',
  topK: 10,
  results: [],

  // Detail modal
  detailEntry: null,
};

/* ── Helpers ────────────────────────────────────────────────────────────── */

function getApi() {
  return window.fiona?.api;
}

function esc(str) {
  if (!str) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return String(str).replace(/[&<>"']/g, (ch) => map[ch]);
}

function truncate(str, maxLen = 120) {
  if (!str) return '';
  if (str.length <= maxLen) return str;
  return str.slice(0, maxLen) + '…';
}

/* ── Render ─────────────────────────────────────────────────────────────── */

async function renderPage(container) {
  if (_state.destroyed) return;
  _state.container = container;

  if (_state.loading) {
    renderSkeletons(container);
    return;
  }

  if (_state.error) {
    renderError(container);
    return;
  }

  // Build category options — pre-select current
  const categoryOptions = _state.categories
    .map((c) =>
      `<option value="${esc(c.name)}"${c.name === _state.selectedCategory ? ' selected' : ''}>${esc(c.name)} (${c.count})</option>`
    )
    .join('');

  // Build results HTML
  let resultsHtml;
  if (_state.results.length === 0) {
    if (_state.query) {
      resultsHtml = `<div style="text-align: center; padding: var(--space-8); color: var(--text-muted); font-size: var(--font-size-sm);">
        No APIs match "${esc(_state.query)}". Try a different search term or category.
      </div>`;
    } else {
      resultsHtml = `<div style="text-align: center; padding: var(--space-8); color: var(--text-muted); font-size: var(--font-size-sm);">
        Enter a search query above to browse the catalog of 1500+ public APIs.
      </div>`;
    }
  } else {
    resultsHtml = '<div class="api-grid">' +
      _state.results.map((r) => renderResultCard(r)).join('') +
      '</div>';
  }

  // Detail modal
  const detailModal = _state.detailEntry ? renderDetailModal(_state.detailEntry) : '';

  const data = {
    entryCount: _state.entryCount,
    lastRefreshed: esc(_state.lastRefreshed),
    refreshIcon: ICONS.refresh.html,
    searchIcon: ICONS.search.html,
    searchQuery: esc(_state.query),
    categoryOptions,
    resultCount: _state.results.length,
    resultsHtml,
    detailModal,
  };

  container.innerHTML = await loadTemplate('apicatalog', data);
  mountHandlers(container);
}

function renderResultCard(r) {
  const e = r.entry;
  const httpsBadge = e.https
    ? '<span class="c-badge c-badge--success" style="font-size:9px;padding:0 6px;" title="HTTPS">HTTPS</span>'
    : '<span class="c-badge c-badge--default" style="font-size:9px;padding:0 6px;" title="No HTTPS">HTTP</span>';

  const corsBadge = e.cors && e.cors !== 'no'
    ? '<span class="c-badge c-badge--info" style="font-size:9px;padding:0 6px;" title="CORS: ' + esc(e.cors) + '">CORS</span>'
    : '';

  const authBadge = e.auth && e.auth !== 'no' && e.auth !== ''
    ? '<span class="c-badge c-badge--warning" style="font-size:9px;padding:0 6px;" title="Auth: ' + esc(e.auth) + '">' + esc(e.auth) + '</span>'
    : '<span class="c-badge c-badge--default" style="font-size:9px;padding:0 6px;">No Auth</span>';

  const scoreVal = typeof r.score === 'number' ? r.score : 0;
  const scorePct = Math.round(scoreVal * 100);

  return html`
    <div class="c-card api-result-row" style="cursor:pointer;" data-action="show-detail" data-api-name="${esc(e.name)}">
      <div class="c-card__body" style="padding: var(--space-3) var(--space-4);">
        <!-- Top row: name + badges -->
        <div style="display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap;margin-bottom:4px;">
          <span style="font-size:var(--font-size-sm);font-weight:var(--font-weight-medium);color:var(--text-primary);">
            ${esc(e.name)}
          </span>
          <span style="font-size:var(--font-size-xxs);color:var(--text-muted);font-family:var(--font-mono);">
            ${esc(e.category)}
          </span>
          ${html.raw(httpsBadge)}
          ${html.raw(corsBadge)}
          ${html.raw(authBadge)}
        </div>

        <!-- Description -->
        <div style="font-size:var(--font-size-xs);color:var(--text-secondary);margin-bottom:4px;max-width:600px;">
          ${esc(truncate(e.description, 140))}
        </div>

        <!-- Bottom row: URL + score -->
        <div style="display:flex;align-items:center;justify-content:space-between;gap:var(--space-2);">
          <span style="font-size:var(--font-size-xxs);color:var(--text-muted);font-family:var(--font-mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:60%;">
            ${esc(e.url)}
          </span>
          <span class="api-score" style="font-size:var(--font-size-xxs);color:var(--text-muted);flex-shrink:0;" title="Relevance score">
            ${scorePct}% match
          </span>
        </div>
      </div>
    </div>
  `;
}

function renderDetailModal(entry) {
  const httpsBadge = entry.https
    ? '<span class="c-badge c-badge--success" style="font-size:10px;">HTTPS</span>'
    : '<span class="c-badge c-badge--default" style="font-size:10px;">HTTP</span>';

  const corsLabel = entry.cors && entry.cors !== 'no' ? entry.cors : 'No';
  const authLabel = entry.auth && entry.auth !== 'no' ? entry.auth : 'None';

  return html`
    <div class="c-modal-overlay" id="apicat-modal" style="position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:1000;display:flex;align-items:center;justify-content:center;">
      <div class="c-modal" style="background:var(--bg-primary);border-radius:var(--radius-lg);max-width:600px;width:90%;max-height:80vh;overflow-y:auto;box-shadow:var(--shadow-xl);">
        <!-- Modal header -->
        <div style="display:flex;align-items:center;justify-content:space-between;padding:var(--space-4) var(--space-4) 0;">
          <h2 style="font-size:var(--font-size-lg);font-weight:var(--font-weight-bold);color:var(--text-primary);margin:0;">
            ${esc(entry.name)}
          </h2>
          <button class="c-btn c-btn--sm c-btn--ghost" id="apicat-modal-close" style="padding:4px;">
            <span class="c-btn__icon">${ICONS.close}</span>
          </button>
        </div>

        <!-- Modal body -->
        <div style="padding:var(--space-4);">
          <p style="font-size:var(--font-size-sm);color:var(--text-secondary);margin:0 0 var(--space-4);">
            ${esc(entry.description)}
          </p>

          <div style="display:grid;grid-template-columns:120px 1fr;gap:var(--space-2) var(--space-3);font-size:var(--font-size-sm);">
            <span style="color:var(--text-muted);">Category</span>
            <span style="color:var(--text-primary);">${esc(entry.category)}</span>

            <span style="color:var(--text-muted);">URL</span>
            <span style="color:var(--accent);font-family:var(--font-mono);font-size:var(--font-size-xs);word-break:break-all;">
              <a href="${esc(entry.url)}" target="_blank" rel="noopener" style="color:var(--accent);">
                ${esc(entry.url)}
              </a>
            </span>

            <span style="color:var(--text-muted);">Auth</span>
            <span>${esc(authLabel)}</span>

            <span style="color:var(--text-muted);">Protocol</span>
            <span>${html.raw(httpsBadge)}</span>

            <span style="color:var(--text-muted);">CORS</span>
            <span>${esc(corsLabel)}</span>
          </div>
        </div>

        <!-- Modal footer -->
        <div style="display:flex;justify-content:flex-end;gap:var(--space-2);padding:0 var(--space-4) var(--space-4);">
          <button class="c-btn c-btn--sm c-btn--ghost" id="apicat-modal-close-btn">Close</button>
          <a href="${esc(entry.url)}" target="_blank" rel="noopener"
             class="c-btn c-btn--sm c-btn--primary">
            <span class="c-btn__icon">${ICONS.externalLink}</span>
            Open API
          </a>
        </div>
      </div>
    </div>
  `;
}

/* ── Skeletons & Error ──────────────────────────────────────────────────── */

function renderSkeletons(container) {
  container.innerHTML = `
    <div style="margin-bottom: var(--space-5);">
      ${skeletonHeading}
      ${skeletonText}
    </div>
    <div style="margin-bottom: var(--space-4);">
      ${skeletonButton} ${skeletonButton} ${skeletonButton}
    </div>
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: var(--space-3);">
      ${skeletonCard} ${skeletonCard} ${skeletonCard}
    </div>
  `;
}

function renderError(container) {
  container.innerHTML = `
    <div style="text-align: center; padding: var(--space-8);">
      <div style="color: var(--error); margin-bottom: var(--space-4);">
        ${ICONS.error}
      </div>
      <h2 style="font-size: var(--font-size-lg); color: var(--text-primary); margin: 0 0 var(--space-2);">Failed to load API Catalog</h2>
      <p style="font-size: var(--font-size-sm); color: var(--text-muted); margin: 0 0 var(--space-4);">
        ${esc(_state.errorMessage || 'The backend could not be reached. Make sure the server is running.')}
      </p>
      <button class="c-btn c-btn--primary c-btn--sm" id="apicat-retry">
        <span class="c-btn__icon">${ICONS.refresh}</span>
        Retry
      </button>
    </div>
  `;
  const retryBtn = container.querySelector('#apicat-retry');
  if (retryBtn) retryBtn.addEventListener('click', () => loadData());
}

/* ── Event Handlers ─────────────────────────────────────────────────────── */

function mountHandlers(container) {
  // Search input — debounced
  const searchInput = container.querySelector('#apicat-search');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      _state.query = searchInput.value;
      scheduleSearch();
    });
  }

  // Category filter
  const catSelect = container.querySelector('#apicat-category');
  if (catSelect) {
    catSelect.addEventListener('change', () => {
      _state.selectedCategory = catSelect.value;
      if (_state.query) scheduleSearch();
    });
  }

  // Top K selector
  const topKSelect = container.querySelector('#apicat-topk');
  if (topKSelect) {
    topKSelect.addEventListener('change', () => {
      _state.topK = parseInt(topKSelect.value, 10) || 10;
      if (_state.query) scheduleSearch();
    });
  }

  // Refresh button
  const refreshBtn = container.querySelector('#apicat-refresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', handleRefresh);
  }

  // Result card clicks (delegated)
  container.querySelectorAll('[data-action="show-detail"]').forEach((el) => {
    el.addEventListener('click', () => {
      const name = el.dataset.apiName;
      if (name) handleShowDetail(name);
    });
  });

  // Modal close
  const modalClose = container.querySelector('#apicat-modal-close');
  if (modalClose) modalClose.addEventListener('click', closeModal);
  const modalCloseBtn = container.querySelector('#apicat-modal-close-btn');
  if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeModal);
  const modalOverlay = container.querySelector('#apicat-modal');
  if (modalOverlay) {
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) closeModal();
    });
  }
}

/* ── Search (debounced) ──────────────────────────────────────────────────── */

let _searchTimer = null;

function scheduleSearch() {
  if (_searchTimer) clearTimeout(_searchTimer);
  _searchTimer = setTimeout(doSearch, 300);
}

async function doSearch() {
  if (_state.destroyed) return;
  const q = _state.query.trim();
  if (!q) {
    _state.results = [];
    if (_state.container) renderPage(_state.container);
    return;
  }

  const api = getApi();
  if (!api) return;

  const params = { q, top_k: String(_state.topK) };
  if (_state.selectedCategory) {
    params.category = _state.selectedCategory;
  }

  try {
    const resp = await api.get('/api/v1/apicatalog/search', params);
    const data = resp?.data || resp;
    _state.results = data?.results || [];
    _state.error = false;
  } catch (err) {
    console.log('[apicatalog] Search failed:', err.message);
    _state.results = [];
    _state.error = true;
    _state.errorMessage = err.message;
  }

  if (!_state.destroyed && _state.container) {
    renderPage(_state.container);
  }
}

/* ── Detail Modal ────────────────────────────────────────────────────────── */

async function handleShowDetail(name) {
  const api = getApi();
  if (!api) return;

  try {
    const resp = await api.get('/api/v1/apicatalog/info', { name });
    const data = resp?.data || resp;
    _state.detailEntry = data?.entry || null;
    if (_state.container) renderPage(_state.container);
  } catch (err) {
    console.log('[apicatalog] Failed to fetch detail:', err.message);
  }
}

function closeModal() {
  _state.detailEntry = null;
  if (_state.container) renderPage(_state.container);
}

/* ── Refresh ─────────────────────────────────────────────────────────────── */

async function handleRefresh() {
  const api = getApi();
  if (!api) return;

  // Optimistic loading state
  _state.loading = true;
  if (_state.container) renderPage(_state.container);

  try {
    const resp = await api.post('/api/v1/apicatalog/refresh');
    const data = resp?.data || resp;
    if (data?.ok) {
      showToast('success', `Refreshed — ${data.entries_cached || ''} entries cached.`);
    }
  } catch (err) {
    console.log('[apicatalog] Refresh failed:', err.message);
    showToast('error', 'Refresh failed: ' + err.message);
  }

  // Reload status
  await loadStatus();
}

/* ── Data Loading ────────────────────────────────────────────────────────── */

async function loadStatus() {
  const api = getApi();
  if (!api) return;

  try {
    const resp = await api.get('/api/v1/apicatalog/status');
    const data = resp?.data || resp;
    if (data?.ok) {
      _state.entryCount = data.entry_count || 0;
      _state.lastRefreshed = data.last_refreshed || '—';
    }
  } catch {
    // Silently degrade — status is cosmetic
  }
}

async function loadCategories() {
  const api = getApi();
  if (!api) return;

  try {
    const resp = await api.get('/api/v1/apicatalog/categories');
    const data = resp?.data || resp;
    _state.categories = data?.categories || [];
  } catch {
    _state.categories = [];
  }
}

async function loadData() {
  if (_state.destroyed) return;

  const api = getApi();
  _state.error = false;
  _state.errorMessage = '';
  _state.results = [];

  if (!api) {
    _state.loading = false;
    if (!_state.destroyed && _state.container) renderPage(_state.container);
    return;
  }

  // Load status + categories in parallel
  await Promise.all([loadStatus(), loadCategories()]);

  _state.loading = false;

  if (!_state.destroyed && _state.container) {
    renderPage(_state.container);
  }
}

/* ── Toast ───────────────────────────────────────────────────────────────── */

function showToast(type, message) {
  const toast = document.createElement('div');
  toast.className = `c-toast c-toast--${type || 'info'} animate-slide-right`;
  toast.style.cssText = 'position: fixed; bottom: 60px; right: 20px; z-index: 9999; max-width: 360px;';
  toast.innerHTML = `
    <div class="c-toast__icon">${ICONS[type === 'success' ? 'check' : type === 'error' ? 'error' : 'info']}</div>
    <div class="c-toast__content"><div class="c-toast__message">${esc(message)}</div></div>
    <button class="c-toast__dismiss" data-toast-dismiss style="flex-shrink:0;">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
    </button>
  `;
  document.body.appendChild(toast);
  toast.querySelector('[data-toast-dismiss]')?.addEventListener('click', () => toast.remove());
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.2s';
    setTimeout(() => toast.remove(), 250);
  }, 3500);
}

/* ── Lifecycle ──────────────────────────────────────────────────────────── */

export function render(container) {
  _state.destroyed = false;
  _state.loading = true;
  _state.error = false;
  _state.errorMessage = '';
  _state.container = container;
  _state.results = [];
  _state.detailEntry = null;

  renderSkeletons(container);
  loadData();
}

export function mount(container) {
  if (container && !_state.container) {
    _state.container = container;
  }
  if (!_state.loading && _state.container) {
    renderPage(_state.container);
  }
}

export function destroy() {
  _state.destroyed = true;
  if (_searchTimer) clearTimeout(_searchTimer);
  _state.container = null;
  _state.results = [];
  _state.categories = [];
  _state.detailEntry = null;
}

/* ── Router-compatible default export ───────────────────────────────────── */

export default function createPage(_routeInfo) {
  return {
    render() {
      return '<div id="apicatalog-root"></div>';
    },
    mount(container) {
      const root = container.querySelector('#apicatalog-root') || container;
      render(root);
    },
    destroy,
  };
}
