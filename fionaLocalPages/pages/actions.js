/* ==========================================================================
   actions.js — Actions Page
   ==========================================================================
   Browse registered actions, run them with optional dry-run mode, and
   view execution history.  Two-tab layout: "Actions" (list + run) and
   "History" (recent executions).

   Exports default: createPage(routeInfo) => { render, mount, destroy }
   ========================================================================== */

import { html } from '../js/components/BaseComponent.js';
import { ICONS } from '../js/components/_icons.js';
import {
  skeletonCard,
  skeletonText,
  skeletonHeading,
} from '../js/components/LoadingSkeleton.js';
import { toast } from '../js/components/Toast.js';
import { modal } from '../js/components/Modal.js';
import { loadTemplate } from '../js/template-loader.js';

/* ── Constants ──────────────────────────────────────────────────────────── */

const HISTORY_LIMIT = 50;

/* ── Module-level State ─────────────────────────────────────────────────── */

const _state = {
  container: null,
  destroyed: false,
  loading: true,
  error: false,
  errorMessage: '',

  // Tabs
  activeTab: 'actions',

  // Data
  actions: [],
  history: [],

  // UI state
  searchQuery: '',
  searchTimer: null,            // debounce timer for search input
  confirmingAction: null,       // name of action with open confirmation panel
  actionResults: {},            // { [actionName]: { loading, result, error } }
  expandedResults: new Set(),   // set of action names with expanded result
  expandedHistory: new Set(),   // set of history event IDs with expanded result

  // Library / Editor state
  activeLibraryView: 'list',    // 'list' | 'editor'
  editorAction: null,           // the action being edited (or null for new)
  editorCode: '',
  editorDescription: '',
  editorTags: '',
  editorFilename: '',
  editorIsNew: false,

  _boundListeners: [],
};

/* ── Helpers ────────────────────────────────────────────────────────────── */

function getApi() {
  return window.fiona?.api;
}

function esc(str) {
  if (!str) return '';
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  };
  return String(str).replace(/[&<>"']/g, (ch) => map[ch]);
}

function timeAgo(timestamp) {
  if (!timestamp) return '';
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  const diff = now - then;
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return 'just now';
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const days = Math.floor(hr / 24);
  return `${days}d ago`;
}

function formatTimestamp(ts) {
  if (!ts) return '--';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return '--';
  const h = String(d.getHours()).padStart(2, '0');
  const m = String(d.getMinutes()).padStart(2, '0');
  const s = String(d.getSeconds()).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

function formatDateFull(ts) {
  if (!ts) return '--';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return '--';
  return d.toISOString().replace('T', ' ').slice(0, 19);
}

function statusBadgeClass(status) {
  const map = {
    success: 'c-badge--success',
    completed: 'c-badge--success',
    failure: 'c-badge--danger',
    error: 'c-badge--danger',
    failed: 'c-badge--danger',
    running: 'c-badge--info',
    in_progress: 'c-badge--info',
    cancelled: 'c-badge--default',
    skipped: 'c-badge--default',
  };
  return map[status] || 'c-badge--default';
}

function statusLabel(status) {
  const map = {
    success: 'Success',
    completed: 'Completed',
    failure: 'Failure',
    error: 'Error',
    failed: 'Failed',
    running: 'Running',
    in_progress: 'In Progress',
    cancelled: 'Cancelled',
    skipped: 'Skipped',
  };
  return map[status] || status || 'Unknown';
}

function formatDuration(ms) {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return `${m}m ${s}s`;
}

/**
 * Format a result object into a human-readable string.
 * Falls back to pretty-printed JSON.
 */
function formatResultOutput(result) {
  if (!result) return '';
  if (typeof result.output === 'string') return result.output;
  if (typeof result.stdout === 'string') return result.stdout;
  if (typeof result.message === 'string') return result.message;
  if (typeof result.error === 'string') return result.error;
  // Try to extract meaningful fields
  const cleaned = { ...result };
  delete cleaned.status;
  delete cleaned.duration_ms;
  delete cleaned.dry_run;
  delete cleaned.timestamp;
  const keys = Object.keys(cleaned);
  if (keys.length === 0) return 'Action completed successfully.';
  if (keys.length === 1 && typeof cleaned[keys[0]] === 'string') return cleaned[keys[0]];
  return JSON.stringify(result, null, 2);
}

/* ── HTML Renderers ─────────────────────────────────────────────────────── */

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

  const fileActions = _state.actions.filter((a) => a.source === 'file');

  const data = {
    boltIcon: ICONS.bolt.html,
    clockIcon: ICONS.clock.html,
    actionsTabActive: _state.activeTab === 'actions',
    historyTabActive: _state.activeTab === 'history',
    libraryTabActive: _state.activeTab === 'library',
    actionsCount: _state.actions.length,
    historyCount: _state.history.length,
    libraryCount: fileActions.length,
    libraryIcon: ICONS.folder.html,
    tabContent: _state.activeTab === 'actions'
      ? renderActionsTab()
      : _state.activeTab === 'history'
        ? renderHistoryTab()
        : renderLibraryView(),
  };

  container.innerHTML = await loadTemplate('actions', data);
  mountComponents(container);
}

/* ── Actions Tab ──────────────────────────────────────────────────────────── */

function renderActionsTab() {
  const query = _state.searchQuery.toLowerCase().trim();
  const filtered = query
    ? _state.actions.filter((a) =>
        (a.name || '').toLowerCase().includes(query) ||
        (a.description || '').toLowerCase().includes(query)
      )
    : _state.actions;

  return html`
    <!-- Search Bar -->
    <div class="actions-search-wrap" style="position: relative; margin-bottom: var(--space-4); max-width: 360px;">
      <span style="position: absolute; left: 10px; top: 50%; transform: translateY(-50%); display: flex; color: var(--text-muted); width: 16px; height: 16px; pointer-events: none;">
        ${ICONS.search}
      </span>
      <input type="text" class="c-input" id="actions-search-input"
             placeholder="Search actions…"
             value="${esc(_state.searchQuery)}"
             style="padding-left: 32px; height: 34px;"
             autocomplete="off" />
    </div>

    <!-- Actions List -->
    ${filtered.length === 0 ? html`
      <div class="actions-empty-state" style="text-align: center; padding: var(--space-12); color: var(--text-muted);">
        <div style="font-size: 36px; margin-bottom: var(--space-4); opacity: 0.3;">${ICONS.bolt}</div>
        <div style="font-size: var(--font-size-md); font-weight: var(--font-weight-medium); margin-bottom: var(--space-2);">
          ${query ? 'No actions match your search' : 'No actions registered'}
        </div>
        <div style="font-size: var(--font-size-sm); color: var(--text-muted);">
          ${query ? 'Try a different search term.' : 'Actions will appear here once registered with the system.'}
        </div>
      </div>
    ` : html.raw(filtered.map((action) => renderActionCard(action)).join(''))}
  `;
}

function renderActionCard(action) {
  const name = action.name || 'unnamed';
  const description = action.description || '';
  const source = action.source || '';
  const resultState = _state.actionResults[name];
  const hasResult = resultState && !resultState.loading && resultState.result != null;
  const isConfirming = _state.confirmingAction === name;
  const isExpanded = _state.expandedResults.has(name);

  return html`
    <div class="c-card action-card" data-action-name="${esc(name)}" style="margin-bottom: var(--space-3);">
      <div class="c-card__body" style="padding: var(--space-4);">
        <!-- Top Row: Name + Run button -->
        <div class="action-card-main" style="display: flex; align-items: center; justify-content: space-between; gap: var(--space-3);">
          <div style="flex: 1; min-width: 0;">
            <div style="font-size: var(--font-size-md); font-weight: var(--font-weight-semibold); color: var(--text-primary); margin-bottom: 2px;">
              ${esc(name)}
            </div>
            ${description ? html`
              <div style="font-size: var(--font-size-xs); color: var(--text-secondary); margin-bottom: var(--space-2);
                          display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                ${esc(description)}
              </div>
            ` : ''}
            <div style="display: flex; align-items: center; gap: var(--space-2); font-size: var(--font-size-xxs); color: var(--text-muted);">
              ${source ? html`
                <span class="c-badge c-badge--default" style="font-size: 9px; padding: 0 6px; text-transform: none; letter-spacing: 0;">
                  ${esc(source)}
                </span>
              ` : ''}
            </div>
          </div>

          <!-- Run button (only show if not confirming and not running) -->
          <div class="action-run-btn-wrap">
          ${!isConfirming && !(resultState && resultState.loading) ? html`
            <button class="c-btn c-btn--primary c-btn--sm action-run-btn" data-action-name="${esc(name)}" title="Run ${esc(name)}">
              <span class="c-btn__icon">${ICONS.play}</span>
              Run
            </button>
          ` : ''}

          <!-- Loading spinner while running -->
          ${resultState && resultState.loading ? html`
            <button class="c-btn c-btn--primary c-btn--sm" disabled style="opacity: 0.7;">
              <span class="c-spinner c-spinner--sm" style="display: inline-flex; align-items: center; justify-content: center;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <circle cx="12" cy="12" r="10" stroke-dasharray="31.4 31.4" stroke-linecap="round" />
                </svg>
              </span>
              Running…
            </button>
          ` : ''}
          </div>
        </div>

        <!-- Inline Confirmation Section -->
        ${isConfirming ? html`
          <div style="margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px solid var(--border-subtle);">
            <div style="font-size: var(--font-size-xs); font-weight: var(--font-weight-medium); color: var(--text-primary); margin-bottom: var(--space-2);">
              Run "${esc(name)}"
            </div>

            <!-- Dry-run toggle -->
            <label class="c-toggle" style="margin-bottom: var(--space-3);">
              <input type="checkbox" class="c-toggle__input action-dry-run-toggle" data-action-name="${esc(name)}" />
              <span class="c-toggle__track">
                <span class="c-toggle__thumb"></span>
              </span>
              <span class="c-toggle__label">Dry run (simulate without side effects)</span>
            </label>

            <!-- Action buttons -->
            <div class="action-confirm-actions" style="display: flex; gap: var(--space-2);">
              <button class="c-btn c-btn--sm c-btn--ghost action-cancel-btn" data-action-name="${esc(name)}">
                Cancel
              </button>
              <button class="c-btn c-btn--sm c-btn--primary action-confirm-run-btn" data-action-name="${esc(name)}">
                <span class="c-btn__icon">${ICONS.play}</span>
                Run
              </button>
            </div>
          </div>
        ` : ''}

        <!-- Result Display -->
        ${hasResult ? html`
          <div style="margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px solid var(--border-subtle);">
            <!-- Result meta -->
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-2);">
              <div style="display: flex; align-items: center; gap: var(--space-2);">
                ${resultState.result.status === 'success' || resultState.result.status === 'completed'
                  ? html`<span style="color: var(--success); display: flex;">${ICONS.check}</span>`
                  : html`<span style="color: var(--danger); display: flex;">${ICONS.error}</span>`
                }
                <span class="c-badge ${statusBadgeClass(resultState.result.status)}" style="font-size: 9px; padding: 0 6px;">
                  ${esc(statusLabel(resultState.result.status))}
                </span>
                ${resultState.result.duration_ms != null ? html`
                  <span style="font-size: var(--font-size-xxs); color: var(--text-muted);">
                    ${formatDuration(resultState.result.duration_ms)}
                  </span>
                ` : ''}
              </div>
              <button class="c-btn c-btn--icon c-btn--sm c-btn--ghost action-result-toggle" data-action-name="${esc(name)}" title="Toggle result details">
                ${isExpanded ? ICONS.chevronUp : ICONS.chevronDown}
              </button>
            </div>

            <!-- Expandable result output -->
            ${isExpanded ? html`
              <pre style="margin: 0; padding: var(--space-3); background: var(--bg-primary); border: 1px solid var(--border); border-radius: var(--radius-md);
                         font-family: var(--font-mono); font-size: var(--font-size-xs); line-height: 1.6;
                         max-height: 400px; overflow: auto; white-space: pre-wrap; word-break: break-all;
                         scrollbar-width: thin; color: var(--text-primary);">
${esc(formatResultOutput(resultState.result))}
              </pre>
            ` : ''}

            <!-- Error message if run failed -->
            ${resultState.result.status === 'failure' || resultState.result.status === 'error' || resultState.result.status === 'failed' ? html`
              <div style="margin-top: var(--space-2); display: flex; gap: var(--space-2);">
                <button class="c-btn c-btn--sm c-btn--ghost action-run-btn" data-action-name="${esc(name)}" style="color: var(--danger);">
                  <span class="c-btn__icon">${ICONS.refresh}</span>
                  Retry
                </button>
              </div>
            ` : ''}
          </div>
        ` : ''}

        <!-- Error state from result -->
        ${resultState && resultState.error && !resultState.result ? html`
          <div style="margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px solid var(--border-subtle);">
            <div class="c-alert c-alert--danger" style="margin: 0;">
              <span class="c-alert__icon">${ICONS.error}</span>
              <div class="c-alert__content">
                <div class="c-alert__title">Run Failed</div>
                ${esc(resultState.error)}
              </div>
            </div>
            <div style="margin-top: var(--space-2); display: flex; gap: var(--space-2);">
              <button class="c-btn c-btn--sm c-btn--ghost action-run-btn" data-action-name="${esc(name)}" style="color: var(--danger);">
                <span class="c-btn__icon">${ICONS.refresh}</span>
                Retry
              </button>
            </div>
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

/* ── History Tab ──────────────────────────────────────────────────────────── */

function renderHistoryTab() {
  const items = _state.history;

  return html`
    <div id="history-tab-content">
      ${items.length === 0 ? html`
        <div class="actions-empty-state" style="text-align: center; padding: var(--space-12); color: var(--text-muted);">
          <div style="font-size: 36px; margin-bottom: var(--space-4); opacity: 0.3;">${ICONS.clock}</div>
          <div style="font-size: var(--font-size-md); font-weight: var(--font-weight-medium); margin-bottom: var(--space-2);">No execution history</div>
          <div style="font-size: var(--font-size-sm); color: var(--text-muted);">
            Run an action to see its history here.
          </div>
        </div>
      ` : html`
        <div style="display: flex; flex-direction: column; gap: var(--space-2);">
          ${html.raw(items.map((event, idx) => renderHistoryItem(event, idx)).join(''))}
        </div>
      `}
    </div>
  `;
}

function renderHistoryItem(event, index) {
  const eventId = event.id || `hist-${index}`;
  const actionName = event.action_name || event.name || 'Unknown';
  const status = event.status || 'completed';
  const timestamp = event.timestamp || event.created_at || event.completed_at || Date.now();
  const duration = event.duration_ms || event.elapsed_ms || null;
  const isExpanded = _state.expandedHistory.has(eventId);
  const result = event.result || event.output || event.data || null;
  const hasResult = result != null;
  const dryRun = event.dry_run === true;

  return html`
    <div class="c-card history-card" data-history-id="${esc(eventId)}" style="margin-bottom: 0;">
      <div class="c-card__body" style="padding: var(--space-3) var(--space-4);">
        <div class="history-card-main" style="display: flex; align-items: center; gap: var(--space-3);">
          <!-- Timestamp -->
          <div class="history-timestamp" style="flex-shrink: 0; min-width: 70px;">
            <div style="font-size: var(--font-size-xs); font-weight: var(--font-weight-medium); color: var(--text-primary); font-variant-numeric: tabular-nums;">
              ${esc(formatTimestamp(timestamp))}
            </div>
            <div style="font-size: var(--font-size-xxs); color: var(--text-muted);">
              ${timeAgo(timestamp)}
            </div>
          </div>

          <!-- Action Name -->
          <div style="flex: 1; min-width: 0;">
            <div style="font-size: var(--font-size-sm); font-weight: var(--font-weight-medium); color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
              ${esc(actionName)}
            </div>
            ${dryRun ? html`
              <div style="font-size: var(--font-size-xxs); color: var(--warning);">Dry run</div>
            ` : ''}
          </div>

          <!-- Duration -->
          <div class="history-duration" style="font-size: var(--font-size-xxs); color: var(--text-muted); flex-shrink: 0; font-variant-numeric: tabular-nums; min-width: 50px; text-align: right;">
            ${formatDuration(duration)}
          </div>

          <!-- Status Badge -->
          <span class="c-badge ${statusBadgeClass(status)}" style="font-size: 9px; padding: 0 6px; flex-shrink: 0; min-width: 48px; text-align: center;">
            ${esc(statusLabel(status))}
          </span>

          <!-- View Result Toggle -->
          ${hasResult ? html`
            <button class="c-btn c-btn--icon c-btn--sm c-btn--ghost history-result-toggle" data-history-id="${esc(eventId)}" title="Toggle result details">
              ${isExpanded ? ICONS.chevronUp : ICONS.chevronDown}
            </button>
          ` : ''}
        </div>

        <!-- Expandable result output -->
        ${isExpanded && hasResult ? html`
          <div style="margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px solid var(--border-subtle);">
            <pre style="margin: 0; padding: var(--space-3); background: var(--bg-primary); border: 1px solid var(--border); border-radius: var(--radius-md);
                       font-family: var(--font-mono); font-size: var(--font-size-xs); line-height: 1.6;
                       max-height: 300px; overflow: auto; white-space: pre-wrap; word-break: break-all;
                       scrollbar-width: thin; color: var(--text-primary);">
${esc(formatResultOutput(result))}
            </pre>
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

/* ── Skeleton & Error States ──────────────────────────────────────────────── */

function renderSkeletons(container) {
  container.innerHTML = html`
    <div style="padding: var(--space-2);">
      <div style="margin-bottom: var(--space-5);">
        ${skeletonHeading({ width: '180px' })}
        ${skeletonText({ width: '200px' })}
      </div>
      <div style="margin-bottom: var(--space-4); display: flex; gap: var(--space-2);">
        <div class="c-skeleton" style="width: 120px; height: 34px; border-radius: var(--radius-md);"></div>
        <div class="c-skeleton" style="width: 120px; height: 34px; border-radius: var(--radius-md);"></div>
      </div>
      <div style="display: flex; flex-direction: column; gap: var(--space-3);">
        ${Array.from({ length: 4 }, () => skeletonCard({ height: '100px' }))}
      </div>
    </div>
  `;
}

function renderError(container) {
  container.innerHTML = html`
    <div class="empty-state" style="margin-top: 10vh;">
      <div class="empty-state__icon" style="color: var(--danger);">
        ${ICONS.error}
      </div>
      <div class="empty-state__title">Failed to Load Actions</div>
      <div class="empty-state__description">
        ${esc(_state.errorMessage || 'Unable to fetch actions from the backend.')}
      </div>
      <button class="c-btn c-btn--primary" id="actions-retry-btn" style="margin-top: var(--space-4);">
        <span class="c-btn__icon">${ICONS.refresh}</span>
        Retry
      </button>
    </div>
  `;

  const retryBtn = container.querySelector('#actions-retry-btn');
  if (retryBtn) {
    retryBtn.addEventListener('click', () => {
      _state.error = false;
      _state.loading = true;
      renderSkeletons(container);
      loadData();
    });
  }
}

/* ── Component Mounting / Event Binding ───────────────────────────────────── */

function mountComponents(container) {
  const listeners = [];

  // Tab switching (delegated)
  const tabsContainer = container.querySelector('.c-tabs');
  if (tabsContainer) {
    const handler = async (e) => {
      const tab = e.target.closest('.c-tab');
      if (!tab) return;
      const tabName = tab.dataset.tab;
      if (tabName && tabName !== _state.activeTab) {
        _state.activeTab = tabName;
        await renderPage(container);
      }
    };
    tabsContainer.addEventListener('click', handler);
    listeners.push(() => tabsContainer.removeEventListener('click', handler));
  }

  // Search input (debounced)
  const searchEl = container.querySelector('#actions-search-input');
  if (searchEl) {
    const handler = (e) => {
      _state.searchQuery = e.target.value;
      if (_state.searchTimer) clearTimeout(_state.searchTimer);
      _state.searchTimer = setTimeout(() => {
        // Re-render only the actions tab content, not the whole page
        const tabContent = container.querySelector('#actions-tab-content');
        if (tabContent && _state.activeTab === 'actions') {
          tabContent.innerHTML = renderActionsTab();
        }
      }, 200);
    };
    searchEl.addEventListener('input', handler);
    listeners.push(() => searchEl.removeEventListener('input', handler));
  }

  // Delegate events from the actions tab content area
  const tabContent = container.querySelector('#actions-tab-content');
  if (tabContent) {
    // Run button clicks (delegated)
    const runClickHandler = async (e) => {
      const btn = e.target.closest('.action-run-btn');
      if (!btn) return;
      const actionName = btn.dataset.actionName;
      if (actionName) {
        // Clear any previous result for this action
        delete _state.actionResults[actionName];
        _state.expandedResults.delete(actionName);
        _state.confirmingAction = actionName;
        await renderPage(container);
      }
    };
    tabContent.addEventListener('click', runClickHandler);
    listeners.push(() => tabContent.removeEventListener('click', runClickHandler));

    // Cancel button clicks
    const cancelClickHandler = async (e) => {
      const btn = e.target.closest('.action-cancel-btn');
      if (!btn) return;
      const actionName = btn.dataset.actionName;
      if (actionName) {
        _state.confirmingAction = null;
        await renderPage(container);
      }
    };
    tabContent.addEventListener('click', cancelClickHandler);
    listeners.push(() => tabContent.removeEventListener('click', cancelClickHandler));

    // Confirm run button clicks
    const confirmRunHandler = (e) => {
      const btn = e.target.closest('.action-confirm-run-btn');
      if (!btn) return;
      const actionName = btn.dataset.actionName;
      if (!actionName) return;

      // Read dry-run toggle state — traverse up to parent card, then find toggle
      const card = btn.closest('.action-card');
      const toggle = card ? card.querySelector('.action-dry-run-toggle') : null;
      const dryRun = toggle ? toggle.checked : false;

      _state.confirmingAction = null;
      runAction(actionName, dryRun);
    };
    tabContent.addEventListener('click', confirmRunHandler);
    listeners.push(() => tabContent.removeEventListener('click', confirmRunHandler));

    // Result expand/collapse toggle
    const resultToggleHandler = async (e) => {
      const btn = e.target.closest('.action-result-toggle');
      if (!btn) return;
      const actionName = btn.dataset.actionName;
      if (!actionName) return;
      if (_state.expandedResults.has(actionName)) {
        _state.expandedResults.delete(actionName);
      } else {
        _state.expandedResults.add(actionName);
      }
      await renderPage(container);
    };
    tabContent.addEventListener('click', resultToggleHandler);
    listeners.push(() => tabContent.removeEventListener('click', resultToggleHandler));
  }

  // History result toggle (if history tab content is rendered)
  const historyContent = container.querySelector('#history-tab-content');
  if (historyContent) {
    const historyToggleHandler = async (e) => {
      const btn = e.target.closest('.history-result-toggle');
      if (!btn) return;
      const histId = btn.dataset.historyId;
      if (!histId) return;
      if (_state.expandedHistory.has(histId)) {
        _state.expandedHistory.delete(histId);
      } else {
        _state.expandedHistory.add(histId);
      }
      await renderPage(container);
    };
    historyContent.addEventListener('click', historyToggleHandler);
    listeners.push(() => historyContent.removeEventListener('click', historyToggleHandler));
  }

  _state._boundListeners = listeners;

  // Delegate events for the library tab content (rendered into #actions-tab-content)
  const libContent = container.querySelector('#actions-tab-content');
  if (libContent) {
    // Library: Run action directly
    const libRunHandler = async (e) => {
      const btn = e.target.closest('[data-lib-action="run"]');
      if (!btn) return;
      const name = btn.dataset.actionName;
      if (name) {
        _state.confirmingAction = null;
        runAction(name, false);
      }
    };
    libContent.addEventListener('click', libRunHandler);
    listeners.push(() => libContent.removeEventListener('click', libRunHandler));

    // Library: Edit action (open editor modal)
    const libEditHandler = (e) => {
      const btn = e.target.closest('[data-lib-action="edit"]');
      if (!btn) return;
      const filename = btn.dataset.filename;
      const action = _state.actions.find(
        (a) => a.source === 'file' && a.filename === filename
      );
      if (action) openEditorForExisting(action);
    };
    libContent.addEventListener('click', libEditHandler);
    listeners.push(() => libContent.removeEventListener('click', libEditHandler));

    // Library: Toggle enabled status
    const libToggleHandler = async (e) => {
      const btn = e.target.closest('[data-lib-action="toggle"]');
      if (!btn) return;
      const filename = btn.dataset.filename;
      if (filename) await handleLibraryToggle(filename);
    };
    libContent.addEventListener('click', libToggleHandler);
    listeners.push(() => libContent.removeEventListener('click', libToggleHandler));

    // Library: Duplicate action
    const libDupHandler = async (e) => {
      const btn = e.target.closest('[data-lib-action="duplicate"]');
      if (!btn) return;
      const filename = btn.dataset.filename;
      if (filename) await handleLibraryDuplicate(filename);
    };
    libContent.addEventListener('click', libDupHandler);
    listeners.push(() => libContent.removeEventListener('click', libDupHandler));

    // Library: Delete action
    const libDelHandler = async (e) => {
      const btn = e.target.closest('[data-lib-action="delete"]');
      if (!btn) return;
      const filename = btn.dataset.filename;
      if (filename) await handleLibraryDelete(filename);
    };
    libContent.addEventListener('click', libDelHandler);
    listeners.push(() => libContent.removeEventListener('click', libDelHandler));

    // Library: Create new action button
    const libCreateHandler = () => {
      openEditorForNew();
    };
    libContent.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-lib-action="create"]');
      if (btn) libCreateHandler();
    });
    // We keep a persistent reference for cleanup
    const createRef = (e) => {
      const btn = e.target.closest('[data-lib-action="create"]');
      if (btn) libCreateHandler();
    };
    libContent.addEventListener('click', createRef);
    listeners.push(() => libContent.removeEventListener('click', createRef));
  }
}

/* ── Library Tab ──────────────────────────────────────────────────────────── */

/**
 * Render the Library tab content — list of file-based actions or editor view.
 */
function renderLibraryView() {
  const fileActions = _state.actions.filter((a) => a.source === 'file');

  if (fileActions.length === 0) {
    return renderLibraryEmptyState();
  }

  return html`
    <div class="library-create-btn-wrap" style="display: flex; justify-content: flex-end; margin-bottom: var(--space-4);">
      <button class="c-btn c-btn--primary c-btn--sm library-create-btn" data-lib-action="create">
        <span class="c-btn__icon">${ICONS.plus}</span>
        Create New Action
      </button>
    </div>
    <div style="display: flex; flex-direction: column; gap: var(--space-3);">
      ${html.raw(fileActions.map((action) => renderLibraryCard(action)).join(''))}
    </div>
  `;
}

/**
 * Render the empty state for the Library tab.
 */
function renderLibraryEmptyState() {
  return html`
    <div class="actions-empty-state" style="text-align: center; padding: var(--space-12); color: var(--text-muted);">
      <div style="font-size: 36px; margin-bottom: var(--space-4); opacity: 0.3;">
        ${ICONS.folder}
      </div>
      <div style="font-size: var(--font-size-md); font-weight: var(--font-weight-medium); margin-bottom: var(--space-2);">
        No file-based actions found
      </div>
      <div style="font-size: var(--font-size-sm); color: var(--text-muted); margin-bottom: var(--space-6);">
        Create your first reusable action in the actions library.
      </div>
      <button class="c-btn c-btn--primary library-create-btn" data-lib-action="create" style="min-width: 200px;">
        <span class="c-btn__icon">${ICONS.plus}</span>
        Create your first action
      </button>
    </div>
  `;
}

/**
 * Render a single library action card.
 * @param {Object} action
 */
function renderLibraryCard(action) {
  const name = action.name || action.filename || 'unnamed';
  const filename = action.filename || '';
  const description = action.description || '';
  const tags = Array.isArray(action.tags) ? action.tags : [];
  const enabled = action.enabled !== false;
  const isRunning = _state.actionResults[name] && _state.actionResults[name].loading;

  return html`
    <div class="c-card library-card" style="margin-bottom: 0;">
      <div class="c-card__body" style="padding: var(--space-4);">
        <div class="library-card-main" style="display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-3);">
          <!-- Left: Info -->
          <div style="flex: 1; min-width: 0;">
            <div style="display: flex; align-items: center; gap: var(--space-2); margin-bottom: 2px;">
              <span style="font-size: var(--font-size-md); font-weight: var(--font-weight-semibold); color: var(--text-primary);">
                ${esc(name)}
              </span>
              <span class="c-badge ${enabled ? 'c-badge--success' : 'c-badge--default'}" style="font-size: 9px; padding: 0 6px; text-transform: none; letter-spacing: 0;">
                ${enabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>
            ${description ? html`
              <div style="font-size: var(--font-size-xs); color: var(--text-secondary); margin-bottom: var(--space-1);">
                ${esc(description)}
              </div>
            ` : ''}
            <div style="font-size: var(--font-size-xxs); color: var(--text-muted); font-family: var(--font-mono);">
              ${esc(filename)}
            </div>
            ${tags.length > 0 ? html`
              <div class="action-tags-wrap" style="display: flex; flex-wrap: wrap; gap: var(--space-1); margin-top: var(--space-2);">
                ${html.raw(tags.map((tag) => html`
                  <span class="c-badge c-badge--default" style="font-size: 9px; padding: 0 6px; text-transform: none; letter-spacing: 0; background: var(--bg-secondary);">
                    ${esc(tag)}
                  </span>
                `).join(''))}
              </div>
            ` : ''}
          </div>

          <!-- Right: Action Buttons -->
          <div class="library-card-actions" style="display: flex; align-items: center; gap: var(--space-1); flex-shrink: 0;">
            <button class="c-btn c-btn--icon c-btn--sm c-btn--ghost" data-lib-action="run" data-action-name="${esc(name)}" title="Run ${esc(name)}" ?disabled="${isRunning}">
              ${isRunning ? html`<span class="c-spinner c-spinner--sm" style="display: flex;">${ICONS.bolt}</span>` : ICONS.play}
            </button>
            <button class="c-btn c-btn--icon c-btn--sm c-btn--ghost" data-lib-action="edit" data-filename="${esc(filename)}" title="Edit ${esc(filename)}">
              ${ICONS.edit}
            </button>
            <button class="c-btn c-btn--icon c-btn--sm c-btn--ghost" data-lib-action="toggle" data-filename="${esc(filename)}" title="${enabled ? 'Disable' : 'Enable'} ${esc(filename)}">
              ${enabled ? ICONS.checkCircle : ICONS.close}
            </button>
            <button class="c-btn c-btn--icon c-btn--sm c-btn--ghost" data-lib-action="duplicate" data-filename="${esc(filename)}" title="Duplicate ${esc(filename)}">
              ${ICONS.copy}
            </button>
            <button class="c-btn c-btn--icon c-btn--sm c-btn--ghost" data-lib-action="delete" data-filename="${esc(filename)}" title="Delete ${esc(filename)}" style="color: var(--danger);">
              ${ICONS.trash}
            </button>
          </div>
        </div>
      </div>
    </div>
  `;
}

/* ── Editor Modal ──────────────────────────────────────────────────────────── */

/**
 * Open the editor modal for creating a new action.
 */
async function openEditorForNew() {
  _state.editorIsNew = true;
  _state.editorAction = null;
  _state.editorCode = '';
  _state.editorDescription = '';
  _state.editorTags = '';
  _state.editorFilename = '';

  await _showEditorModal();
}

/**
 * Open the editor modal for editing an existing action.
 * @param {Object} action
 */
async function openEditorForExisting(action) {
  _state.editorIsNew = false;
  _state.editorAction = action;
  _state.editorFilename = action.filename || '';

  // Load the file content
  const api = getApi();
  if (!api) {
    toast.showToast('error', 'Error', 'API client not available.');
    return;
  }

  try {
    const result = await api.get('/api/v1/actions/file/get', {
      filename: _state.editorFilename,
    });
    const data = result?.data || result;
    _state.editorCode = data.code || '';
    _state.editorDescription = data.description || '';
    _state.editorTags = Array.isArray(data.tags) ? data.tags.join(', ') : (data.tags || '');
  } catch (err) {
    toast.showToast('error', 'Load Failed', `Failed to load action file: ${err.message || 'Unknown error'}`);
    _state.editorCode = '';
    _state.editorDescription = action.description || '';
    _state.editorTags = Array.isArray(action.tags) ? action.tags.join(', ') : '';
  }

  await _showEditorModal();
}

/**
 * Build and show the editor modal.
 */
async function _showEditorModal() {
  const isNew = _state.editorIsNew;
  const fileActions = _state.actions.filter((a) => a.source === 'file');
  const content = buildEditorHTML(isNew, fileActions);

  // Show the modal
  await modal.showModal({
    title: isNew ? 'Create New Action' : `Edit: ${_state.editorFilename || 'Action'}`,
    content,
    size: 'xl',
    closeable: true,
    closeOnBackdrop: false,
  });

  // Bind events inside the modal after it's rendered
  bindEditorEvents(isNew);
}

/**
 * Build the editor modal HTML content.
 * @param {boolean} isNew
 * @param {Array} fileActions
 * @returns {string}
 */
function buildEditorHTML(isNew, fileActions) {
  const filename = _state.editorFilename || '';
  const code = _state.editorCode || '';
  const description = _state.editorDescription || '';
  const tags = _state.editorTags || '';
  const name = filename ? filename.replace(/\.py$/, '') : '';

  const fileOptions = fileActions.map((a) => html`
    <option value="${esc(a.filename)}" ${a.filename === filename ? 'selected' : ''}>
      ${esc(a.filename)}
    </option>
  `).join('');

  return html`
    <div class="action-editor" style="display: flex; flex-direction: column; gap: var(--space-4);">
      <!-- File Selector -->
      <div>
        <label style="display: block; font-size: var(--font-size-xs); font-weight: var(--font-weight-medium); color: var(--text-secondary); margin-bottom: var(--space-1);">
          Action File
        </label>
        <select id="editor-file-select" class="c-input" style="width: 100%;">
          <option value="">-- New File --</option>
          ${html.raw(fileOptions)}
        </select>
      </div>

      <!-- Filename Input (visible only when creating new) -->
      <div id="editor-filename-group" style="${isNew ? '' : 'display: none;'}">
        <label style="display: block; font-size: var(--font-size-xs); font-weight: var(--font-weight-medium); color: var(--text-secondary); margin-bottom: var(--space-1);">
          Filename <span style="color: var(--danger);">*</span>
        </label>
        <input type="text" id="editor-filename-input" class="c-input" style="width: 100%; font-family: var(--font-mono);"
               placeholder="my_action.py" value="${esc(isNew ? '' : filename)}" />
      </div>

      <!-- Name (auto-derived, read-only) -->
      <div>
        <label style="display: block; font-size: var(--font-size-xs); font-weight: var(--font-weight-medium); color: var(--text-secondary); margin-bottom: var(--space-1);">
          Name <span style="color: var(--text-muted); font-weight: var(--font-weight-normal);">(auto-derived from filename)</span>
        </label>
        <input type="text" id="editor-name" class="c-input" style="width: 100%;" readonly value="${esc(name)}" />
      </div>

      <!-- Description -->
      <div>
        <label style="display: block; font-size: var(--font-size-xs); font-weight: var(--font-weight-medium); color: var(--text-secondary); margin-bottom: var(--space-1);">
          Description
        </label>
        <input type="text" id="editor-description" class="c-input" style="width: 100%;"
               placeholder="Brief description of what this action does"
               value="${esc(description)}" />
      </div>

      <!-- Tags -->
      <div>
        <label style="display: block; font-size: var(--font-size-xs); font-weight: var(--font-weight-medium); color: var(--text-secondary); margin-bottom: var(--space-1);">
          Tags <span style="color: var(--text-muted); font-weight: var(--font-weight-normal);">(comma-separated)</span>
        </label>
        <input type="text" id="editor-tags" class="c-input" style="width: 100%;"
               placeholder="tag1, tag2, tag3"
               value="${esc(tags)}" />
      </div>

      <!-- Code Editor -->
      <div>
        <label style="display: block; font-size: var(--font-size-xs); font-weight: var(--font-weight-medium); color: var(--text-secondary); margin-bottom: var(--space-1);">
          Python Code <span style="color: var(--danger);">*</span>
        </label>
        <textarea id="editor-code" class="c-input"
                  style="width: 100%; min-height: 320px; font-family: var(--font-mono); font-size: var(--font-size-sm);
                         line-height: 1.5; padding: var(--space-3); resize: vertical; white-space: pre;
                         overflow-wrap: normal; overflow-x: auto; tab-size: 2;"
                  placeholder="# Write your Python action code here...">${code}</textarea>
      </div>

      <!-- Buttons -->
      <div style="display: flex; gap: var(--space-2); justify-content: flex-end; border-top: 1px solid var(--border-subtle); padding-top: var(--space-4);">
        <button id="editor-cancel-btn" class="c-btn c-btn--ghost">Cancel</button>
        ${!isNew ? html`
          <button id="editor-delete-btn" class="c-btn c-btn--danger" style="margin-right: auto;">
            <span class="c-btn__icon">${ICONS.trash}</span>
            Delete
          </button>
        ` : ''}
        <button id="editor-save-btn" class="c-btn c-btn--primary">
          <span class="c-btn__icon">${ICONS.check}</span>
          Save
        </button>
      </div>
    </div>
  `;
}

/**
 * Bind events for the editor modal.
 * @param {boolean} isNew
 */
function bindEditorEvents(isNew) {
  const fileSelect = document.getElementById('editor-file-select');
  const filenameInput = document.getElementById('editor-filename-input');
  const nameInput = document.getElementById('editor-name');
  const codeTextarea = document.getElementById('editor-code');
  const descriptionInput = document.getElementById('editor-description');
  const tagsInput = document.getElementById('editor-tags');
  const saveBtn = document.getElementById('editor-save-btn');
  const deleteBtn = document.getElementById('editor-delete-btn');
  const cancelBtn = document.getElementById('editor-cancel-btn');

  // File selector change: load selected file or clear for new
  if (fileSelect) {
    fileSelect.addEventListener('change', async () => {
      const selected = fileSelect.value;
      const filenameGroup = document.getElementById('editor-filename-group');
      if (!selected) {
        // New File
        if (filenameGroup) filenameGroup.style.display = '';
        if (filenameInput) filenameInput.value = '';
        if (nameInput) nameInput.value = '';
        if (codeTextarea) codeTextarea.value = '';
        if (descriptionInput) descriptionInput.value = '';
        if (tagsInput) tagsInput.value = '';
        _state.editorIsNew = true;
        _state.editorAction = null;
        _state.editorFilename = '';
        _state.editorCode = '';
        _state.editorDescription = '';
        _state.editorTags = '';
        // Update modal title
        const titleEl = document.querySelector('.c-modal__title');
        if (titleEl) titleEl.textContent = 'Create New Action';
      } else {
        // Existing file — load its data
        if (filenameGroup) filenameGroup.style.display = 'none';
        const api = getApi();
        if (!api) return;
        try {
          const result = await api.get('/api/v1/actions/file/get', {
            filename: selected,
          });
          const data = result?.data || result;
          _state.editorIsNew = false;
          _state.editorAction = data;
          _state.editorFilename = selected;
          _state.editorCode = data.code || '';
          _state.editorDescription = data.description || '';
          _state.editorTags = Array.isArray(data.tags) ? data.tags.join(', ') : (data.tags || '');

          if (nameInput) nameInput.value = selected.replace(/\.py$/, '');
          if (codeTextarea) codeTextarea.value = _state.editorCode;
          if (descriptionInput) descriptionInput.value = _state.editorDescription;
          if (tagsInput) tagsInput.value = _state.editorTags;

          // Update modal title
          const titleEl = document.querySelector('.c-modal__title');
          if (titleEl) titleEl.textContent = `Edit: ${selected}`;

          // Show/hide delete button
          const delBtn = document.getElementById('editor-delete-btn');
          if (delBtn) delBtn.style.display = '';
        } catch (err) {
          toast.showToast('error', 'Load Failed', `Failed to load action: ${err.message || 'Unknown error'}`);
        }
      }
    });
  }

  // Filename input change: auto-update name
  if (filenameInput) {
    const updateName = () => {
      const val = filenameInput.value.trim();
      if (nameInput) nameInput.value = val.replace(/\.py$/i, '');
    };
    filenameInput.addEventListener('input', updateName);
  }

  // Save button
  if (saveBtn) {
    saveBtn.addEventListener('click', async () => {
      // Determine filename
      const fileSelectVal = fileSelect ? fileSelect.value : '';
      let saveFilename;
      if (!fileSelectVal) {
        // New file — use filename input
        saveFilename = filenameInput ? filenameInput.value.trim() : '';
      } else {
        saveFilename = fileSelectVal;
      }

      if (!saveFilename) {
        toast.showToast('warning', 'Validation Error', 'Please provide a filename.');
        if (filenameInput) filenameInput.focus();
        return;
      }
      if (!saveFilename.endsWith('.py')) {
        saveFilename += '.py';
      }

      const saveCode = codeTextarea ? codeTextarea.value : '';
      if (!saveCode.trim()) {
        toast.showToast('warning', 'Validation Error', 'Please provide Python code for the action.');
        if (codeTextarea) codeTextarea.focus();
        return;
      }

      const saveDescription = descriptionInput ? descriptionInput.value.trim() : '';
      const saveTags = tagsInput ? tagsInput.value.trim() : '';

      const api = getApi();
      if (!api) {
        toast.showToast('error', 'Error', 'API client not available.');
        return;
      }

      try {
        const result = await api.post('/api/v1/actions/file/save', {
          filename: saveFilename,
          code: saveCode,
          description: saveDescription,
          tags: saveTags,
        });
        toast.showToast('success', 'Saved', `Action "${saveFilename}" saved successfully.`);
        modal.closeModal('saved');
        // Refresh data after save
        await refreshActions();
      } catch (err) {
        toast.showToast('error', 'Save Failed', `Failed to save action: ${err.message || 'Unknown error'}`);
      }
    });
  }

  // Delete button
  if (deleteBtn) {
    deleteBtn.addEventListener('click', async () => {
      const delFilename = _state.editorFilename;
      if (!delFilename) return;

      const confirmed = await modal.showModal({
        title: 'Delete Action',
        content: `<p>Are you sure you want to delete <strong>${esc(delFilename)}</strong>? This cannot be undone.</p>`,
        size: 'sm',
        buttons: [
          { label: 'Cancel', value: 'cancel', variant: 'ghost' },
          { label: 'Delete', value: 'delete', variant: 'danger' },
        ],
      });

      if (confirmed !== 'delete') return;

      const api = getApi();
      if (!api) {
        toast.showToast('error', 'Error', 'API client not available.');
        return;
      }

      try {
        await api.post('/api/v1/actions/file/delete', {
          filename: delFilename,
        });
        toast.showToast('success', 'Deleted', `Action "${delFilename}" deleted.`);
        modal.closeModal('deleted');
        await refreshActions();
      } catch (err) {
        toast.showToast('error', 'Delete Failed', `Failed to delete action: ${err.message || 'Unknown error'}`);
      }
    });
  }

  // Cancel button
  if (cancelBtn) {
    cancelBtn.addEventListener('click', () => {
      modal.closeModal('cancel');
    });
  }
}

/* ── Library CRUD Operations ──────────────────────────────────────────────── */

/**
 * Toggle the enabled status of a file-based action.
 * @param {string} filename
 */
async function handleLibraryToggle(filename) {
  const api = getApi();
  if (!api) {
    toast.showToast('error', 'Error', 'API client not available.');
    return;
  }

  try {
    const result = await api.post('/api/v1/actions/file/toggle', { filename });
    const action = result?.data || result;
    const status = action.enabled ? 'enabled' : 'disabled';
    toast.showToast('success', 'Toggled', `Action "${filename}" ${status}.`);
    await refreshActions();
  } catch (err) {
    toast.showToast('error', 'Toggle Failed', err.message || 'Failed to toggle action.');
  }
}

/**
 * Duplicate a file-based action with an auto-generated name.
 * @param {string} filename
 */
async function handleLibraryDuplicate(filename) {
  const api = getApi();
  if (!api) {
    toast.showToast('error', 'Error', 'API client not available.');
    return;
  }

  // Generate a unique copy name
  const stem = filename.replace(/\.py$/, '');
  let newName = `${stem}_copy`;
  let counter = 1;
  while (_state.actions.some((a) => a.source === 'file' && a.filename === `${newName}.py`)) {
    counter++;
    newName = `${stem}_copy_${counter}`;
  }

  try {
    const result = await api.post('/api/v1/actions/file/duplicate', {
      filename,
      new_name: newName,
    });
    const newAction = result?.data || result;
    toast.showToast('success', 'Duplicated', `Action duplicated as "${newAction.filename}".`);
    await refreshActions();
  } catch (err) {
    toast.showToast('error', 'Duplicate Failed', err.message || 'Failed to duplicate action.');
  }
}

/**
 * Delete a file-based action after confirmation.
 * @param {string} filename
 */
async function handleLibraryDelete(filename) {
  const confirmed = await modal.showModal({
    title: 'Delete Action',
    content: `<p>Are you sure you want to delete <strong>${esc(filename)}</strong>? This cannot be undone.</p>`,
    size: 'sm',
    buttons: [
      { label: 'Cancel', value: 'cancel', variant: 'ghost' },
      { label: 'Delete', value: 'delete', variant: 'danger' },
    ],
  });

  if (confirmed !== 'delete') return;

  const api = getApi();
  if (!api) {
    toast.showToast('error', 'Error', 'API client not available.');
    return;
  }

  try {
    await api.post('/api/v1/actions/file/delete', { filename });
    toast.showToast('success', 'Deleted', `Action "${filename}" deleted.`);
    await refreshActions();
  } catch (err) {
    toast.showToast('error', 'Delete Failed', err.message || 'Failed to delete action.');
  }
}

/**
 * Refresh the actions list from the backend and re-render.
 */
async function refreshActions() {
  const api = getApi();
  if (!api) return;

  try {
    const result = await api.get('/api/v1/actions');
    const actions = Array.isArray(result?.data)
      ? result.data
      : Array.isArray(result)
        ? result
        : [];
    _state.actions = actions;

    if (!_state.destroyed && _state.container) {
      await renderPage(_state.container);
    }
  } catch (err) {
    console.error('[actions] Failed to refresh actions:', err);
  }
}

/* ── Data Loading ─────────────────────────────────────────────────────────── */

async function loadData() {
  if (_state.destroyed) return;
  const api = getApi();
  if (!api) {
    _state.error = true;
    _state.errorMessage = 'API client not available.';
    _state.loading = false;
    if (_state.container) await renderPage(_state.container);
    return;
  }

  try {
    const [actionsResult, historyResult] = await Promise.all([
      api.get('/api/v1/actions'),
      api.get(`/api/v1/actions/history?limit=${HISTORY_LIMIT}`),
    ]);

    const actions = Array.isArray(actionsResult?.data)
      ? actionsResult.data
      : Array.isArray(actionsResult)
        ? actionsResult
        : [];

    const history = Array.isArray(historyResult?.data)
      ? historyResult.data
      : Array.isArray(historyResult)
        ? historyResult
        : [];

    _state.actions = actions;
    _state.history = history;
    _state.error = false;
    _state.loading = false;

    if (!_state.destroyed && _state.container) {
      await renderPage(_state.container);
    }
  } catch (err) {
    console.error('[actions] Failed to load data:', err);
    _state.error = true;
    _state.errorMessage = err.message || 'Failed to fetch actions.';
    _state.loading = false;
    if (!_state.destroyed && _state.container) {
      await renderPage(_state.container);
    }
  }
}

async function runAction(actionName, dryRun) {
  if (_state.destroyed) return;
  const api = getApi();
  if (!api) {
    toast.showToast('error', 'Error', 'API client not available.');
    return;
  }

  // Find the action to get optional source/profile
  const action = _state.actions.find((a) => a.name === actionName);

  // Set loading state
  _state.actionResults[actionName] = { loading: true, result: null, error: null };
  if (_state.container) await renderPage(_state.container);

  const body = {
    name: actionName,
    dry_run: dryRun,
  };
  if (action && action.source) {
    body.source = action.source;
  }
  if (action && action.profile) {
    body.profile = action.profile;
  }

  try {
    const result = await api.post('/api/v1/actions/run', body);
    const data = result?.data || result;

    _state.actionResults[actionName] = {
      loading: false,
      result: data,
      error: null,
    };

    // Auto-expand the result
    _state.expandedResults.add(actionName);

    // Show toast based on status
    const status = data?.status || 'completed';
    if (status === 'success' || status === 'completed') {
      toast.showToast(
        'success',
        'Action Completed',
        `"${actionName}" ${dryRun ? '(dry run) ' : ''}finished successfully.`
      );
    } else {
      toast.showToast(
        'warning',
        'Action Completed',
        `"${actionName}" finished with status: ${statusLabel(status)}.`
      );
    }

    // Also refresh history in the background
    loadHistorySilently();

    if (!_state.destroyed && _state.container) {
      await renderPage(_state.container);
    }
  } catch (err) {
    console.error(`[actions] Failed to run action "${actionName}":`, err);

    _state.actionResults[actionName] = {
      loading: false,
      result: null,
      error: err.message || 'Failed to run action.',
    };

    // Auto-expand to show error
    _state.expandedResults.add(actionName);

    toast.showToast('error', 'Run Failed', `"${actionName}" — ${err.message || 'Unknown error'}.`);

    if (!_state.destroyed && _state.container) {
      await renderPage(_state.container);
    }
  }
}

async function loadHistorySilently() {
  if (_state.destroyed) return;
  const api = getApi();
  if (!api) return;

  try {
    const result = await api.get(`/api/v1/actions/history?limit=${HISTORY_LIMIT}`);
    const history = Array.isArray(result?.data)
      ? result.data
      : Array.isArray(result)
        ? result
        : [];
    _state.history = history;
    // If history tab is active, re-render to show updated data
    if (!_state.destroyed && _state.container && _state.activeTab === 'history') {
      await renderPage(_state.container);
    }
  } catch {
    // Silent fail for background refresh
  }
}

/* ── Lifecycle ─────────────────────────────────────────────────────────────── */

/**
 * Full render — called from outside the router or from mount().
 * @param {Element} container
 */
export function render(container) {
  _state.destroyed = false;
  _state.loading = true;
  _state.error = false;
  _state.errorMessage = '';
  _state.container = container;

  renderSkeletons(container);
  loadData();
}

/**
 * Cleanup — called when navigating away.
 */
export function destroy() {
  _state.destroyed = true;

  if (_state.searchTimer) {
    clearTimeout(_state.searchTimer);
    _state.searchTimer = null;
  }

  for (const fn of _state._boundListeners) {
    try { fn(); } catch (e) { /* ignore */ }
  }
  _state._boundListeners = [];

  _state.container = null;
  _state.actions = [];
  _state.history = [];
  _state.actionResults = {};
  _state.expandedResults = new Set();
  _state.expandedHistory = new Set();
  _state.confirmingAction = null;

  // Reset library / editor state
  _state.activeLibraryView = 'list';
  _state.editorAction = null;
  _state.editorCode = '';
  _state.editorDescription = '';
  _state.editorTags = '';
  _state.editorFilename = '';
  _state.editorIsNew = false;
}

/* ── Router-compatible default export ────────────────────────────────────── */

/**
 * Factory function for the SPA router.
 * Returns { render, mount, destroy } lifecycle object.
 * @param {Object} _routeInfo
 * @returns {{ render: Function, mount: Function, destroy: Function }}
 */
export default function createPage(_routeInfo) {
  return {
    render() {
      return '<div id="actions-root"></div>';
    },
    mount(container) {
      const root = container.querySelector('#actions-root') || container;
      render(root);
    },
    destroy,
  };
}
