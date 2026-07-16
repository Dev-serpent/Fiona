/* ==========================================================================
   macros.js — Macro Runner Page
   ==========================================================================
   Displays defined macros with expandable step lists, run/dry-run execution,
   inline result display, and search/filter by macro name.

   NEW FEATURES (June 2026):
   • Recording UI — start/stop, pulsing indicator, step capture via UI
   • Macro editing — reorder steps, remove/insert steps, inline command editing
   • Macro chaining — step type selector including "run_macro" with macro picker
   • Import / Export — JSON download and file upload
   • Keyboard shortcut assignment — listen for key combos

   Backend APIs:
     GET    /api/v1/macros        → { ok, data: { name: [steps] }, shortcuts: {...} }
     POST   /api/v1/macros/run    → { ok, data: [{ step, command, returncode, stdout, stderr }] }
     POST   /api/v1/macros/save   → { ok, data: { name, step_count } }
     DELETE /api/v1/macros/delete → { ok, data: { name, deleted } }
     GET    /api/v1/macros/export → downloadable JSON file
     POST   /api/v1/macros/import → { ok, data: { count, imported } }

   Exports: { render(container?), mount(container), destroy() }
   ========================================================================== */

import { html } from '../js/components/BaseComponent.js';
import { ICONS } from '../js/components/_icons.js';
import {
  skeletonCard,
  skeletonText,
  skeletonHeading,
} from '../js/components/LoadingSkeleton.js';
import { toast } from '../js/components/Toast.js';
import { contextMenu } from '../js/components/ContextMenu.js';
import { loadTemplate } from '../js/template-loader.js';

/* ── Constants ──────────────────────────────────────────────────────────── */

const STORAGE_KEY = 'fiona_macros_state';

/* ── Module-level State ─────────────────────────────────────────────────── */

const _state = {
  container: null,
  destroyed: false,
  loading: true,
  error: false,
  errorMessage: '',

  // Raw data: { macroName: [{ step, command, ... }, ...] }
  macros: {},
  // Processed: [{ name, steps }]
  macrosArray: [],

  // UI state
  expanded: new Set(),
  searchQuery: '',

  // Per-macro execution results: { name: { loading, data, error } }
  results: {},

  // Per-macro dry-run toggle: { name: true/false }
  dryRunEnabled: {},

  // ── Recording state ──────────────────────────────────────────────────
  isRecording: false,
  recordingName: '',
  recordingSteps: [], // [{ action, description }]

  // ── Editing state ────────────────────────────────────────────────────
  editing: new Set(),          // macro names currently in edit mode
  editData: {},                // { macroName: { steps: [{ type, action, description }] } }

  // ── Shortcuts ────────────────────────────────────────────────────────
  shortcuts: {},               // { macroName: 'Ctrl+Shift+K' }
  capturingShortcut: null,     // macro name whose shortcut is being captured

  _boundListeners: [],
};

/* ── Helpers ────────────────────────────────────────────────────────────── */

function getApi() {
  return window.fiona?.api;
}

function esc(str) {
  if (str == null) return '';
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  };
  return String(str).replace(/[&<>"']/g, (ch) => map[ch]);
}

function persistState() {
  try {
    const data = { searchQuery: _state.searchQuery };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch (e) {
    // Silently fail
  }
}

function loadPersistedState() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const data = JSON.parse(stored);
      _state.searchQuery = data.searchQuery || '';
    }
  } catch (e) {
    // Silently fail
  }
}

/** Convert a step dict from the backend to the edit format. */
function stepToEditFormat(step) {
  const action = step.action || step.command || '';
  let type = 'command';
  let commandVal = action;
  if (action.startsWith('GOTO:')) {
    type = 'run_macro';
    commandVal = action.slice(5);
  }
  return {
    type,
    action: commandVal,
    description: step.description || step.desc || '',
  };
}

/** Convert edit-format steps to backend-compatible dicts. */
function stepsToBackendFormat(editSteps) {
  return editSteps.map((s) => ({
    action: s.type === 'run_macro' ? `GOTO:${s.action}` : s.action,
    description: s.description || '',
  }));
}

/** Get a unique list of macro names (for the macro-chain picker). */
function getMacroNames() {
  return _state.macrosArray.map((e) => e.name);
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

  // Filter by search query
  const query = _state.searchQuery.toLowerCase().trim();
  const filtered = query
    ? _state.macrosArray.filter((entry) =>
        entry.name.toLowerCase().includes(query)
      )
    : _state.macrosArray;

  const totalCount = _state.macrosArray.length;

  // Build macros list content
  let macrosListContent = '';
  if (filtered.length === 0) {
    if (totalCount === 0) {
      macrosListContent = renderEmptyState();
    } else {
      macrosListContent = html`
        <div class="macro-empty-state" style="text-align: center; padding: var(--space-8); color: var(--text-muted);">
          <div style="font-size: 28px; margin-bottom: var(--space-3); opacity: 0.3;">${ICONS.search}</div>
          <div style="font-size: var(--font-size-md);">No macros match "${esc(query)}"</div>
        </div>
      `;
    }
  } else {
    macrosListContent = filtered.map((entry) => renderMacroCard(entry)).join('');
  }

  // Recording steps HTML
  const recordingStepsHtml = _state.recordingSteps.length === 0
    ? html`<div style="color: var(--text-muted); font-style: italic;">No steps recorded yet. Add a step below.</div>`
    : _state.recordingSteps.map((s, i) => html`
        <div style="display: flex; align-items: center; gap: var(--space-2); padding: var(--space-1) 0; border-bottom: 1px solid var(--border-subtle);">
          <span class="c-badge" style="flex-shrink: 0; min-width: 20px; text-align: center; font-size: var(--font-size-xxs);">${i + 1}</span>
          <span style="flex: 1; font-family: var(--font-mono); font-size: var(--font-size-xs); color: var(--text-primary);">${esc(s.action)}</span>
          <button class="c-btn c-btn--icon c-btn--xs c-btn--ghost" data-action="remove-recording-step" data-step-idx="${i}" title="Remove step" style="color: var(--danger);">${ICONS.close}</button>
        </div>
      `).join('');

  const data = {
    // Toolbar
    plusIcon: ICONS.plus.html,
    isRecording: _state.isRecording,
    recordingName: esc(_state.recordingName),
    stopIcon: ICONS.pause.html,
    recordIcon: ICONS.playCircle.html,
    importIcon: ICONS.upload.html,
    exportIcon: ICONS.download.html,
    addIcon: ICONS.plus.html,
    recordingStepCount: _state.recordingSteps.length,
    recordingStepsHtml,

    // Search
    searchIcon: ICONS.search.html,
    searchQuery: esc(_state.searchQuery),
    hasTotalCount: totalCount > 0,
    totalCount,
    singular: totalCount === 1,

    // Macros list
    macrosListContent,
  };

  container.innerHTML = await loadTemplate('macros', data);
  mountComponents(container);
}

function renderEmptyState() {
  return html`
    <div class="macro-empty-state" style="text-align: center; padding: var(--space-12); color: var(--text-muted);">
      <div style="font-size: 36px; margin-bottom: var(--space-4); opacity: 0.3;">${ICONS.play}</div>
      <div style="font-size: var(--font-size-md); font-weight: var(--font-weight-medium); margin-bottom: var(--space-2);">No macros defined</div>
      <div style="font-size: var(--font-size-sm); color: var(--text-muted);">Create a macro to see it here.</div>
    </div>
  `;
}

function renderMacroCard(entry) {
  const { name, steps } = entry;
  const isExpanded = _state.expanded.has(name);
  const stepCount = Array.isArray(steps) ? steps.length : 0;
  const result = _state.results[name];
  const hasResult = result && result.data && !result.loading;
  const isLoading = result && result.loading;
  const isDryRun = _state.dryRunEnabled[name] || false;
  const hasError = result && result.error && !result.loading;
  const isEditing = _state.editing.has(name);
  const shortcut = _state.shortcuts[name] || '';
  const isCapturing = _state.capturingShortcut === name;

  return html`
    <div class="c-card macro-card" data-macro-name="${esc(name)}" style="margin-bottom: var(--space-3); ${isEditing ? 'border-color: var(--accent);' : ''}">
      <!-- Card Header — always visible, clickable to expand -->
      <div class="c-card__header macro-card-header"
           style="cursor: pointer; display: flex; align-items: center; justify-content: space-between; padding: var(--space-3) var(--space-4);"
           data-action="toggle-expand" data-macro-name="${esc(name)}">
        <div style="display: flex; align-items: center; gap: var(--space-3); min-width: 0;">
          <div class="macro-card-icon" style="width: 32px; height: 32px; display: grid; place-items: center; border-radius: var(--radius-md); background: var(--accent-muted); color: var(--accent); flex-shrink: 0;">
            ${ICONS.play}
          </div>
          <div style="min-width: 0;">
            <div style="display: flex; align-items: center; gap: var(--space-2);">
              <span class="macro-card-name" style="font-size: var(--font-size-sm); font-weight: var(--font-weight-medium); color: var(--text-primary);">
                ${esc(name)}
              </span>
              ${shortcut ? html`<span style="font-size: var(--font-size-xxs); padding: 1px 6px; border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); color: var(--text-muted); font-family: var(--font-mono);">${esc(shortcut)}</span>` : ''}
            </div>
            <div style="font-size: var(--font-size-xxs); color: var(--text-muted);">
              ${stepCount} step${stepCount !== 1 ? 's' : ''}
              ${isEditing ? html`<span style="color: var(--accent); margin-left: var(--space-2);">(editing…)</span>` : ''}
            </div>
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: var(--space-2); flex-shrink: 0;">
          ${isLoading ? html`<span class="c-spinner" style="width: 16px; height: 16px;"></span>` : ''}
          <button class="c-btn c-btn--icon c-btn--sm c-btn--ghost expand-btn"
                  data-action="toggle-expand" data-macro-name="${esc(name)}"
                  title="${isExpanded ? 'Collapse' : 'Expand'}"
                  style="pointer-events: none;">
            ${isExpanded ? ICONS.chevronUp : ICONS.chevronDown}
          </button>
        </div>
      </div>

      <!-- Expandable Content -->
      ${isExpanded ? html`
        <div class="macro-expanded-content">
          <!-- Steps List -->
          <div class="c-card__body" style="padding-top: 0; padding-bottom: var(--space-3);">
            ${stepCount > 0 ? html`
              <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-2);">
                <span style="font-size: var(--font-size-xs); font-weight: var(--font-weight-medium); color: var(--text-muted);">
                  ${isEditing ? 'Edit Steps' : 'Steps'}
                </span>
              </div>
              ${isEditing
                ? html.raw(renderEditSteps(name, _state.editData[name]?.steps || []))
                : html.raw(steps.map((step, idx) => renderStepItem(step, idx)).join(''))
              }
            ` : html`
              <div style="font-size: var(--font-size-xs); color: var(--text-muted); padding: var(--space-2) 0;">
                No steps defined.
              </div>
            `}
          </div>

          <!-- Action Buttons -->
          <div class="c-card__footer macro-card-footer" style="border-top: 1px solid var(--border-subtle); padding: var(--space-3) var(--space-4);">
            ${isEditing ? html`
              <div class="macro-footer-row" style="display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap;">
                <button class="c-btn c-btn--primary c-btn--sm" data-action="save-macro-edits" data-macro-name="${esc(name)}">
                  <span class="c-btn__icon">${ICONS.check}</span>
                  Save
                </button>
                <button class="c-btn c-btn--sm c-btn--ghost" data-action="cancel-macro-edits" data-macro-name="${esc(name)}">
                  <span class="c-btn__icon">${ICONS.close}</span>
                  Cancel
                </button>
                <button class="c-btn c-btn--sm c-btn--ghost" data-action="add-step" data-macro-name="${esc(name)}">
                  <span class="c-btn__icon">${ICONS.plus}</span>
                  Add Step
                </button>
                <span style="flex: 1;"></span>
                <span style="font-size: var(--font-size-xxs); color: var(--text-muted);">Drag handle or use arrows to reorder</span>
              </div>
            ` : html`
              <div class="macro-footer-row" style="display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap;">
                <button class="c-btn c-btn--primary c-btn--sm macro-run-btn"
                        data-action="run-macro" data-macro-name="${esc(name)}"
                        ${isLoading ? 'disabled' : ''}>
                  <span class="c-btn__icon">${isLoading ? html`<span class="c-spinner c-spinner--sm"></span>` : ICONS.play}</span>
                  ${isDryRun ? 'Preview' : 'Run'}
                </button>

                <label class="macro-dryrun-label" style="display: flex; align-items: center; gap: var(--space-1); font-size: var(--font-size-xs); color: var(--text-muted); cursor: pointer; user-select: none;">
                  <input type="checkbox" class="macro-dryrun-toggle" data-macro-name="${esc(name)}"
                         ${isDryRun ? 'checked' : ''}
                         style="accent-color: var(--accent);" />
                  Dry Run
                </label>

                <button class="c-btn c-btn--sm c-btn--ghost macro-dryrun-btn"
                        data-action="dryrun-macro" data-macro-name="${esc(name)}"
                        ${isLoading ? 'disabled' : ''}>
                  <span class="c-btn__icon">${ICONS.eye}</span>
                  Dry Run
                </button>

                <!-- Edit button -->
                <button class="c-btn c-btn--sm c-btn--ghost" data-action="edit-macro" data-macro-name="${esc(name)}">
                  <span class="c-btn__icon">${ICONS.edit}</span>
                  Edit
                </button>

                <!-- Shortcut button -->
                <button class="c-btn c-btn--sm c-btn--ghost" data-action="assign-shortcut" data-macro-name="${esc(name)}">
                  <span class="c-btn__icon">${ICONS.keyboard}</span>
                  ${shortcut ? esc(shortcut) : 'Shortcut'}
                </button>

                <!-- Delete button -->
                <button class="c-btn c-btn--sm c-btn--ghost" data-action="delete-macro" data-macro-name="${esc(name)}" style="color: var(--danger);" title="Delete macro">
                  <span class="c-btn__icon">${ICONS.trash}</span>
                </button>

                ${isLoading ? html`
                  <span style="font-size: var(--font-size-xs); color: var(--text-muted); display: flex; align-items: center; gap: var(--space-1);">
                    <span class="c-spinner c-spinner--sm"></span>
                    Running…
                  </span>
                ` : ''}
              </div>
            `}
          </div>

          <!-- Shortcut capture overlay -->
          ${isCapturing ? html`
            <div style="border-top: 1px solid var(--border-subtle); padding: var(--space-3) var(--space-4); background: var(--surface-alt);">
              <div style="font-size: var(--font-size-xs); color: var(--text-muted); margin-bottom: var(--space-2);">Press a key combination for this macro…</div>
              <div class="macro-shortcut-capture" style="display: flex; align-items: center; gap: var(--space-2);">
                <input type="text" class="c-input shortcut-capture-input"
                       data-macro-name="${esc(name)}"
                       placeholder="Press keys…"
                       readonly
                       style="width: 200px; height: 34px; font-family: var(--font-mono); cursor: pointer;" />
                <button class="c-btn c-btn--sm c-btn--ghost" data-action="clear-shortcut" data-macro-name="${esc(name)}">
                  Clear
                </button>
                <button class="c-btn c-btn--sm c-btn--ghost" data-action="cancel-shortcut" data-macro-name="${esc(name)}">
                  Cancel
                </button>
              </div>
            </div>
          ` : ''}

          <!-- Results Section -->
          ${hasResult ? html`
            <div style="border-top: 1px solid var(--border-subtle);">
              ${html.raw(renderResults(result.data, name))}
            </div>
          ` : ''}

          ${hasError ? html`
            <div class="c-card__body" style="border-top: 1px solid var(--border-subtle); color: var(--danger); font-size: var(--font-size-sm); padding-top: var(--space-3);">
              <div style="display: flex; align-items: center; gap: var(--space-2);">
                ${ICONS.error}
                <span>${esc(result.error)}</span>
              </div>
            </div>
          ` : ''}
        </div>
      ` : ''}
    </div>
  `;
}

function renderStepItem(step, idx) {
  const stepNum = step.step || step.step_number || (idx + 1);
  const command = step.command || step.action || '';
  const description = step.description || step.desc || '';

  return html`
    <div class="macro-step-item" style="display: flex; gap: var(--space-3); padding: var(--space-2) 0; border-bottom: 1px solid var(--border-subtle); align-items: flex-start;">
      <span class="c-badge" style="flex-shrink: 0; min-width: 24px; text-align: center; font-size: var(--font-size-xxs);">${stepNum}</span>
      <div style="min-width: 0; flex: 1;">
        <div style="font-family: var(--font-mono); font-size: var(--font-size-xs); color: var(--text-primary); white-space: pre-wrap; word-break: break-all;">
          ${esc(command)}
        </div>
        ${description ? html`
          <div style="font-size: var(--font-size-xxs); color: var(--text-muted); margin-top: 2px;">
            ${esc(description)}
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

/** Render editable steps for a macro in edit mode. */
function renderEditSteps(macroName, steps) {
  if (!steps || steps.length === 0) {
    return html`<div style="font-size: var(--font-size-xs); color: var(--text-muted); font-style: italic;">No steps. Click "Add Step" to start.</div>`;
  }

  const macroNames = getMacroNames().filter((n) => n !== macroName);

  return steps.map((step, idx) => {
    const isFirst = idx === 0;
    const isLast = idx === steps.length - 1;
    return html`
      <div class="macro-edit-step" data-step-idx="${idx}" style="display: flex; gap: var(--space-2); padding: var(--space-2) 0; border-bottom: 1px solid var(--border-subtle); align-items: center;">
        <!-- Grip / Move buttons -->
        <div style="display: flex; flex-direction: column; gap: 2px; flex-shrink: 0;">
          <button class="c-btn c-btn--icon c-btn--xs c-btn--ghost" data-action="step-move-up" data-macro-name="${esc(macroName)}" data-step-idx="${idx}" title="Move up" ${isFirst ? 'disabled' : ''} style="padding: 0; line-height: 1;">
            ${ICONS.chevronUp}
          </button>
          <button class="c-btn c-btn--icon c-btn--xs c-btn--ghost" data-action="step-move-down" data-macro-name="${esc(macroName)}" data-step-idx="${idx}" title="Move down" ${isLast ? 'disabled' : ''} style="padding: 0; line-height: 1;">
            ${ICONS.chevronDown}
          </button>
        </div>

        <!-- Step number -->
        <span class="c-badge" style="flex-shrink: 0; min-width: 22px; text-align: center; font-size: var(--font-size-xxs);">${idx + 1}</span>

        <!-- Type selector -->
        <select class="c-input macro-edit-type-select" data-macro-name="${esc(macroName)}" data-step-idx="${idx}" style="width: 130px; height: 30px; font-size: var(--font-size-xs); padding: 0 var(--space-2); flex-shrink: 0;">
          <option value="command" ${step.type === 'command' ? 'selected' : ''}>Command</option>
          <option value="run_macro" ${step.type === 'run_macro' ? 'selected' : ''}>Run Macro</option>
        </select>

        <!-- Value: text input for command, select for run_macro -->
        ${step.type === 'command' ? html`
          <input type="text" class="c-input macro-edit-input" data-macro-name="${esc(macroName)}" data-step-idx="${idx}" data-field="action"
                 value="${esc(step.action)}" placeholder="shell command…"
                 style="flex: 1; height: 30px; font-family: var(--font-mono); font-size: var(--font-size-xs);" autocomplete="off" />
        ` : html`
          <select class="c-input macro-edit-macro-select" data-macro-name="${esc(macroName)}" data-step-idx="${idx}" style="flex: 1; height: 30px; font-size: var(--font-size-xs); padding: 0 var(--space-2);">
            ${macroNames.length === 0 ? html`<option value="" disabled>No other macros</option>` : ''}
            <option value="" ${!step.action ? 'selected' : ''} disabled>Select macro…</option>
            ${macroNames.map((m) => html`
              <option value="${esc(m)}" ${step.action === m ? 'selected' : ''}>${esc(m)}</option>
            `).join('')}
          </select>
        `}

        <!-- Remove button -->
        <button class="c-btn c-btn--icon c-btn--xs c-btn--ghost" data-action="remove-step" data-macro-name="${esc(macroName)}" data-step-idx="${idx}" title="Remove step" style="color: var(--danger); flex-shrink: 0;">
          ${ICONS.trash}
        </button>
      </div>
    `;
  }).join('');
}

function renderResults(data, macroName) {
  const steps = Array.isArray(data) ? data : [];

  if (steps.length === 0) {
    return html`
      <div class="c-card__body macro-results" style="padding: var(--space-3); background: var(--surface-alt);">
        <div style="font-size: var(--font-size-xs); color: var(--text-muted);">No output returned.</div>
      </div>
    `;
  }

  return html`
    <div class="c-card__body macro-results" style="padding-top: var(--space-3); padding-bottom: var(--space-3); background: var(--surface-alt);">
      <div style="font-size: var(--font-size-xs); font-weight: var(--font-weight-medium); color: var(--text-muted); margin-bottom: var(--space-2);">
        Results
      </div>
      ${html.raw(steps.map((step, idx) => renderResultRow(step, idx)).join(''))}
    </div>
  `;
}

function renderResultRow(step, idx) {
  const returnCode = step.returncode != null ? step.returncode : step.return_code;
  const command = step.command || '';
  const stdout = step.stdout || '';
  const stderr = step.stderr || '';
  const isSuccess = returnCode === 0;
  const stepLabel = step.step || step.step_number || (idx + 1);
  const stdoutLines = stdout ? stdout.split('\n').length : 0;
  const stderrLines = stderr ? stderr.split('\n').length : 0;

  return html`
    <div style="margin-bottom: var(--space-2); padding: var(--space-2); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--surface);">
      <!-- Result Header -->
      <div style="display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-1);">
        <span class="c-badge c-badge--${isSuccess ? 'success' : 'danger'}" style="flex-shrink: 0; display: flex; align-items: center; gap: 2px; font-size: var(--font-size-xxs);">
          ${isSuccess ? ICONS.check : ICONS.close}
          ${returnCode}
        </span>
        <span style="font-family: var(--font-mono); font-size: var(--font-size-xs); color: var(--text-primary); flex: 1; white-space: pre-wrap; word-break: break-all;">
          ${esc(command)}
        </span>
        <span style="font-size: var(--font-size-xxs); color: var(--text-muted); flex-shrink: 0;">Step ${esc(String(stepLabel))}</span>
      </div>

      <!-- Stdout -->
      ${stdout ? html`
        <details style="margin-top: var(--space-1);">
          <summary style="font-size: var(--font-size-xxs); color: var(--text-muted); cursor: pointer; padding: 2px 0; user-select: none;">
            stdout (${stdoutLines} line${stdoutLines !== 1 ? 's' : ''})
          </summary>
          <pre style="margin: var(--space-1) 0 0 0; padding: var(--space-2); background: var(--surface-alt); border-radius: var(--radius-sm); font-size: var(--font-size-xxs); max-height: 200px; overflow: auto; white-space: pre-wrap; word-break: break-all; color: var(--text-secondary);">${esc(stdout)}</pre>
        </details>
      ` : ''}

      <!-- Stderr -->
      ${stderr ? html`
        <details style="margin-top: var(--space-1);">
          <summary style="font-size: var(--font-size-xxs); color: ${isSuccess ? 'var(--text-muted)' : 'var(--danger)'}; cursor: pointer; padding: 2px 0; user-select: none;">
            stderr (${stderrLines} line${stderrLines !== 1 ? 's' : ''})
          </summary>
          <pre style="margin: var(--space-1) 0 0 0; padding: var(--space-2); background: var(--surface-alt); border-radius: var(--radius-sm); font-size: var(--font-size-xxs); max-height: 200px; overflow: auto; white-space: pre-wrap; word-break: break-all; color: var(--danger);">${esc(stderr)}</pre>
        </details>
      ` : ''}
    </div>
  `;
}

function renderSkeletons(container) {
  container.innerHTML = html`
    <div style="padding: var(--space-2);">
      <div style="margin-bottom: var(--space-5);">
        ${skeletonHeading({ width: '200px' })}
        ${skeletonText({ width: '140px' })}
      </div>
      <div style="margin-bottom: var(--space-4); max-width: 360px;">
        ${skeletonText({ width: '100%' })}
      </div>
      ${Array.from({ length: 3 }, () => skeletonCard({ height: '72px' }))}
    </div>
  `;
}

function renderError(container) {
  container.innerHTML = html`
    <div class="empty-state" style="margin-top: 10vh;">
      <div class="empty-state__icon" style="color: var(--danger);">
        ${ICONS.error}
      </div>
      <div class="empty-state__title">Connection Error</div>
      <div class="empty-state__description">
        ${esc(_state.errorMessage || 'Unable to fetch macros from backend.')}
      </div>
      <button class="c-btn c-btn--primary" id="macros-retry-btn" style="margin-top: var(--space-4);">
        <span class="c-btn__icon">${ICONS.refresh}</span>
        Retry
      </button>
    </div>
  `;

  const retryBtn = container.querySelector('#macros-retry-btn');
  if (retryBtn) {
    retryBtn.addEventListener('click', () => {
      _state.error = false;
      _state.loading = true;
      renderSkeletons(container);
      loadData();
    });
  }
}

/* ── Component Mounting ─────────────────────────────────────────────────── */

function mountComponents(container) {
  const listeners = [];

  // ── Search input ────────────────────────────────────────────────────
  const searchEl = container.querySelector('#macros-search-input');
  if (searchEl) {
    const handler = async (e) => {
      _state.searchQuery = e.target.value;
      persistState();
      await renderPage(container);
    };
    searchEl.addEventListener('input', handler);
    listeners.push(() => searchEl.removeEventListener('input', handler));
  }

  // ── Toggle expand ───────────────────────────────────────────────────
  const toggleEls = container.querySelectorAll('[data-action="toggle-expand"]');
  toggleEls.forEach((el) => {
    const handler = async () => {
      const name = el.dataset.macroName;
      if (!name) return;
      if (_state.expanded.has(name)) {
        _state.expanded.delete(name);
      } else {
        _state.expanded.add(name);
      }
      await renderPage(container);
    };
    el.addEventListener('click', handler);
    listeners.push(() => el.removeEventListener('click', handler));
  });

  // ── Dry-run toggle checkboxes ───────────────────────────────────────
  container.querySelectorAll('.macro-dryrun-toggle').forEach((cb) => {
    const handler = async () => {
      const name = cb.dataset.macroName;
      if (!name) return;
      _state.dryRunEnabled[name] = cb.checked;
      await renderPage(container);
    };
    cb.addEventListener('change', handler);
    listeners.push(() => cb.removeEventListener('change', handler));
  });

  // ── Run buttons ─────────────────────────────────────────────────────
  container.querySelectorAll('.macro-run-btn').forEach((btn) => {
    const handler = () => {
      const name = btn.dataset.macroName;
      if (!name) return;
      const isDryRun = _state.dryRunEnabled[name] || false;
      executeMacro(name, isDryRun);
    };
    btn.addEventListener('click', handler);
    listeners.push(() => btn.removeEventListener('click', handler));
  });

  // ── Dry Run buttons ─────────────────────────────────────────────────
  container.querySelectorAll('.macro-dryrun-btn').forEach((btn) => {
    const handler = () => {
      const name = btn.dataset.macroName;
      if (!name) return;
      executeMacro(name, true);
    };
    btn.addEventListener('click', handler);
    listeners.push(() => btn.removeEventListener('click', handler));
  });

  // ── Recording: Start Recording ──────────────────────────────────────
  const startRecBtn = container.querySelector('[data-action="start-recording"]');
  if (startRecBtn) {
    const handler = () => {
      _state.isRecording = true;
      _state.recordingName = '';
      _state.recordingSteps = [];
      renderPage(container);
    };
    startRecBtn.addEventListener('click', handler);
    listeners.push(() => startRecBtn.removeEventListener('click', handler));
  }

  // ── Recording: Stop Recording ───────────────────────────────────────
  const stopRecBtn = container.querySelector('[data-action="stop-recording"]');
  if (stopRecBtn) {
    const handler = () => {
      const name = _state.recordingName.trim();
      if (!name) {
        toast.showToast('warning', 'Name Required', 'Enter a name for the macro before saving.');
        return;
      }
      if (_state.recordingSteps.length === 0) {
        toast.showToast('warning', 'No Steps', 'Add at least one step before saving.');
        return;
      }
      // Save the recorded macro
      saveNewMacro(name, _state.recordingSteps);
    };
    stopRecBtn.addEventListener('click', handler);
    listeners.push(() => stopRecBtn.removeEventListener('click', handler));
  }

  // ── Recording: Capture Step ─────────────────────────────────────────
  const captureBtn = container.querySelector('[data-action="capture-step"]');
  const captureInput = container.querySelector('#macro-recording-command');
  if (captureBtn && captureInput) {
    const capture = () => {
      const cmd = captureInput.value.trim();
      if (!cmd) {
        toast.showToast('warning', 'Empty Command', 'Enter a command for the step.');
        return;
      }
      _state.recordingSteps.push({ action: cmd, description: '' });
      captureInput.value = '';
      captureInput.focus();
      renderPage(container);
    };
    captureBtn.addEventListener('click', capture);
    listeners.push(() => captureBtn.removeEventListener('click', capture));
    // Also capture on Enter key
    captureInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') capture();
    });
    listeners.push(() => captureInput.removeEventListener('keydown', capture));
  }

  // ── Recording: Name input sync ──────────────────────────────────────
  const recNameInput = container.querySelector('#macro-recording-name');
  if (recNameInput) {
    const handler = (e) => {
      _state.recordingName = e.target.value;
    };
    recNameInput.addEventListener('input', handler);
    listeners.push(() => recNameInput.removeEventListener('input', handler));
  }

  // ── Recording: Remove step from recording list ──────────────────────
  container.querySelectorAll('[data-action="remove-recording-step"]').forEach((btn) => {
    const handler = () => {
      const idx = parseInt(btn.dataset.stepIdx, 10);
      if (!isNaN(idx) && idx >= 0 && idx < _state.recordingSteps.length) {
        _state.recordingSteps.splice(idx, 1);
        renderPage(container);
      }
    };
    btn.addEventListener('click', handler);
    listeners.push(() => btn.removeEventListener('click', handler));
  });

  // ── Editing: Enter edit mode ────────────────────────────────────────
  container.querySelectorAll('[data-action="edit-macro"]').forEach((btn) => {
    const handler = () => {
      const name = btn.dataset.macroName;
      if (!name) return;
      enterEditMode(name);
      renderPage(container);
    };
    btn.addEventListener('click', handler);
    listeners.push(() => btn.removeEventListener('click', handler));
  });

  // ── Editing: Cancel edits ───────────────────────────────────────────
  container.querySelectorAll('[data-action="cancel-macro-edits"]').forEach((btn) => {
    const handler = () => {
      const name = btn.dataset.macroName;
      if (!name) return;
      cancelEditMode(name);
      renderPage(container);
    };
    btn.addEventListener('click', handler);
    listeners.push(() => btn.removeEventListener('click', handler));
  });

  // ── Editing: Save edits ─────────────────────────────────────────────
  container.querySelectorAll('[data-action="save-macro-edits"]').forEach((btn) => {
    const handler = async () => {
      const name = btn.dataset.macroName;
      if (!name) return;
      await saveMacroEdits(name);
    };
    btn.addEventListener('click', handler);
    listeners.push(() => btn.removeEventListener('click', handler));
  });

  // ── Editing: Add step ───────────────────────────────────────────────
  container.querySelectorAll('[data-action="add-step"]').forEach((btn) => {
    const handler = () => {
      const name = btn.dataset.macroName;
      if (!name || !_state.editData[name]) return;
      _state.editData[name].steps.push({ type: 'command', action: '', description: '' });
      renderPage(container);
    };
    btn.addEventListener('click', handler);
    listeners.push(() => btn.removeEventListener('click', handler));
  });

  // ── Editing: Remove step ────────────────────────────────────────────
  container.querySelectorAll('[data-action="remove-step"]').forEach((btn) => {
    const handler = () => {
      const name = btn.dataset.macroName;
      const idx = parseInt(btn.dataset.stepIdx, 10);
      if (!name || !_state.editData[name]) return;
      _state.editData[name].steps.splice(idx, 1);
      renderPage(container);
    };
    btn.addEventListener('click', handler);
    listeners.push(() => btn.removeEventListener('click', handler));
  });

  // ── Editing: Move step up ───────────────────────────────────────────
  container.querySelectorAll('[data-action="step-move-up"]').forEach((btn) => {
    const handler = () => {
      const name = btn.dataset.macroName;
      const idx = parseInt(btn.dataset.stepIdx, 10);
      if (!name || !_state.editData[name] || idx <= 0) return;
      const steps = _state.editData[name].steps;
      [steps[idx - 1], steps[idx]] = [steps[idx], steps[idx - 1]];
      renderPage(container);
    };
    btn.addEventListener('click', handler);
    listeners.push(() => btn.removeEventListener('click', handler));
  });

  // ── Editing: Move step down ─────────────────────────────────────────
  container.querySelectorAll('[data-action="step-move-down"]').forEach((btn) => {
    const handler = () => {
      const name = btn.dataset.macroName;
      const idx = parseInt(btn.dataset.stepIdx, 10);
      if (!name || !_state.editData[name]) return;
      const steps = _state.editData[name].steps;
      if (idx >= steps.length - 1) return;
      [steps[idx], steps[idx + 1]] = [steps[idx + 1], steps[idx]];
      renderPage(container);
    };
    btn.addEventListener('click', handler);
    listeners.push(() => btn.removeEventListener('click', handler));
  });

  // ── Editing: Inline command input (update state without re-render) ──
  container.querySelectorAll('.macro-edit-input').forEach((input) => {
    const handler = () => {
      const name = input.dataset.macroName;
      const idx = parseInt(input.dataset.stepIdx, 10);
      const field = input.dataset.field || 'action';
      if (_state.editData[name] && _state.editData[name].steps[idx]) {
        _state.editData[name].steps[idx][field] = input.value;
      }
    };
    input.addEventListener('input', handler);
    listeners.push(() => input.removeEventListener('input', handler));
  });

  // ── Editing: Type selector ──────────────────────────────────────────
  container.querySelectorAll('.macro-edit-type-select').forEach((select) => {
    const handler = () => {
      const name = select.dataset.macroName;
      const idx = parseInt(select.dataset.stepIdx, 10);
      if (_state.editData[name] && _state.editData[name].steps[idx]) {
        _state.editData[name].steps[idx].type = select.value;
        // If switching to run_macro, pre-fill with first available macro
        if (select.value === 'run_macro') {
          const names = getMacroNames().filter((n) => n !== name);
          if (names.length > 0 && !_state.editData[name].steps[idx].action) {
            _state.editData[name].steps[idx].action = names[0];
          }
        }
        renderPage(container);
      }
    };
    select.addEventListener('change', handler);
    listeners.push(() => select.removeEventListener('change', handler));
  });

  // ── Editing: Macro select for chaining ──────────────────────────────
  container.querySelectorAll('.macro-edit-macro-select').forEach((select) => {
    const handler = () => {
      const name = select.dataset.macroName;
      const idx = parseInt(select.dataset.stepIdx, 10);
      if (_state.editData[name] && _state.editData[name].steps[idx]) {
        _state.editData[name].steps[idx].action = select.value;
      }
    };
    select.addEventListener('change', handler);
    listeners.push(() => select.removeEventListener('change', handler));
  });

  // ── Shortcut: Assign shortcut button ────────────────────────────────
  container.querySelectorAll('[data-action="assign-shortcut"]').forEach((btn) => {
    const handler = () => {
      const name = btn.dataset.macroName;
      if (!name) return;
      _state.capturingShortcut = name;
      _state.expanded.add(name);
      renderPage(container);
    };
    btn.addEventListener('click', handler);
    listeners.push(() => btn.removeEventListener('click', handler));
  });

  // ── Shortcut: Cancel shortcut capture ───────────────────────────────
  container.querySelectorAll('[data-action="cancel-shortcut"]').forEach((btn) => {
    const handler = () => {
      _state.capturingShortcut = null;
      renderPage(container);
    };
    btn.addEventListener('click', handler);
    listeners.push(() => btn.removeEventListener('click', handler));
  });

  // ── Shortcut: Clear shortcut ────────────────────────────────────────
  container.querySelectorAll('[data-action="clear-shortcut"]').forEach((btn) => {
    const handler = () => {
      const name = btn.dataset.macroName;
      if (!name) return;
      _state.shortcuts[name] = '';
      _state.capturingShortcut = null;
      renderPage(container);
    };
    btn.addEventListener('click', handler);
    listeners.push(() => btn.removeEventListener('click', handler));
  });

  // ── Shortcut: Capture keydown on shortcut input ─────────────────────
  container.querySelectorAll('.shortcut-capture-input').forEach((input) => {
    const handler = (e) => {
      e.preventDefault();
      const name = input.dataset.macroName;
      if (!name) return;

      const parts = [];
      if (e.ctrlKey || e.metaKey) parts.push(e.metaKey ? 'Meta' : 'Ctrl');
      if (e.altKey) parts.push('Alt');
      if (e.shiftKey) parts.push('Shift');

      // Ignore modifier-only presses
      const key = e.key;
      if (key === 'Control' || key === 'Alt' || key === 'Shift' || key === 'Meta') return;

      // Map common keys
      let displayKey = key;
      if (key === ' ') displayKey = 'Space';
      else if (key.length === 1) displayKey = key.toUpperCase();
      else displayKey = key;

      parts.push(displayKey);
      const combo = parts.join('+');

      _state.shortcuts[name] = combo;
      _state.capturingShortcut = null;
      renderPage(container);
    };
    input.addEventListener('keydown', handler);
    // Focus the input on mount so user can immediately press keys
    setTimeout(() => input.focus(), 50);
    listeners.push(() => input.removeEventListener('keydown', handler));
  });

  // ── Delete macro ────────────────────────────────────────────────────
  container.querySelectorAll('[data-action="delete-macro"]').forEach((btn) => {
    const handler = async () => {
      const name = btn.dataset.macroName;
      if (!name) return;
      if (!confirm(`Delete macro "${name}"? This cannot be undone.`)) return;
      await deleteMacro(name);
    };
    btn.addEventListener('click', handler);
    listeners.push(() => btn.removeEventListener('click', handler));
  });

  // ── New Macro ───────────────────────────────────────────────────────
  const newMacroBtn = container.querySelector('[data-action="new-macro"]');
  if (newMacroBtn) {
    const handler = () => {
      _state.isRecording = true;
      _state.recordingName = '';
      _state.recordingSteps = [];
      renderPage(container);
    };
    newMacroBtn.addEventListener('click', handler);
    listeners.push(() => newMacroBtn.removeEventListener('click', handler));
  }

  // ── Import Macros ───────────────────────────────────────────────────
  const importBtn = container.querySelector('[data-action="import-macros"]');
  const importFileInput = container.querySelector('#macro-import-file-input');
  if (importBtn && importFileInput) {
    importBtn.addEventListener('click', () => importFileInput.click());
    listeners.push(() => {}); // file input lives in DOM
    importFileInput.addEventListener('change', async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      await importMacrosFromFile(file);
      importFileInput.value = ''; // reset
    });
    listeners.push(() => importFileInput.removeEventListener('change', importFileInput));
  }

  // ── Export Macros ───────────────────────────────────────────────────
  const exportBtn = container.querySelector('[data-action="export-macros"]');
  if (exportBtn) {
    const handler = () => exportMacros();
    exportBtn.addEventListener('click', handler);
    listeners.push(() => exportBtn.removeEventListener('click', handler));
  }

  // ── Long-press on macro cards (mobile context menu) ──
  const macrosList = container.querySelector('#macros-list');
  if (macrosList) {
    let longPressTimer = null;

    const touchStart = (e) => {
      const card = e.target.closest('.macro-card');
      if (!card) return;
      longPressTimer = setTimeout(() => {
        e.preventDefault();
        const touch = e.touches[0];
        const macroName = card.dataset.macroName;
        if (!macroName) return;
        const isExpanded = _state.expanded.has(macroName);
        contextMenu.showContextMenu(touch.clientX, touch.clientY, [
          {
            label: isExpanded ? 'Collapse' : 'Expand',
            icon: 'chevronDown',
            handler: () => {
              if (isExpanded) _state.expanded.delete(macroName);
              else _state.expanded.add(macroName);
              renderPage(container);
            },
          },
          { divider: true },
          {
            label: 'Run',
            icon: 'play',
            handler: () => runMacro(macroName, _state.dryRunEnabled[macroName]),
          },
          {
            label: 'Edit',
            icon: 'edit',
            handler: () => enterEditMode(macroName),
          },
          { divider: true },
          {
            label: 'Copy Name',
            icon: 'copy',
            handler: () => navigator.clipboard.writeText(macroName).catch(() => {}),
          },
          {
            label: 'Delete',
            icon: 'trash',
            danger: true,
            handler: () => {
              if (!confirm(`Delete macro "${macroName}"?`)) return;
              deleteMacro(macroName);
            },
          },
        ]);
      }, 500);
    };

    const touchEnd = () => { if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; } };
    const touchMove = () => { if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; } };

    macrosList.addEventListener('touchstart', touchStart, { passive: false });
    macrosList.addEventListener('touchend', touchEnd);
    macrosList.addEventListener('touchmove', touchMove);
    listeners.push(() => {
      macrosList.removeEventListener('touchstart', touchStart);
      macrosList.removeEventListener('touchend', touchEnd);
      macrosList.removeEventListener('touchmove', touchMove);
    });
  }

  _state._boundListeners = listeners;
}

/* ── Recording Actions ──────────────────────────────────────────────────── */

async function saveNewMacro(name, steps) {
  const api = getApi();
  if (!api) {
    toast.showToast('error', 'Error', 'API client not available.');
    return;
  }

  try {
    const result = await api.post('/api/v1/macros/save', {
      name,
      steps: steps.map((s) => ({ action: s.action, description: s.description || '' })),
    });

    if (result && result.ok) {
      toast.showToast('success', 'Macro Created', `Macro "${name}" saved with ${steps.length} step(s).`);
      _state.isRecording = false;
      _state.recordingName = '';
      _state.recordingSteps = [];
      _state.expanded.add(name);
      await loadData();
    } else {
      const msg = (result && result.data && result.data.error) || 'Failed to save macro.';
      toast.showToast('error', 'Save Failed', msg);
    }
  } catch (err) {
    console.error('[macros] Save error:', err);
    toast.showToast('error', 'Save Failed', err.message || 'Could not save macro.');
  }
}

/* ── Editing Actions ────────────────────────────────────────────────────── */

function enterEditMode(name) {
  const entry = _state.macrosArray.find((e) => e.name === name);
  if (!entry) return;
  _state.editing.add(name);
  _state.editData[name] = {
    steps: (entry.steps || []).map((s) => stepToEditFormat(s)),
  };
}

function cancelEditMode(name) {
  _state.editing.delete(name);
  delete _state.editData[name];
}

async function saveMacroEdits(name) {
  const editEntry = _state.editData[name];
  if (!editEntry) return;

  const api = getApi();
  if (!api) {
    toast.showToast('error', 'Error', 'API client not available.');
    return;
  }

  // Validate steps
  const validSteps = editEntry.steps.filter((s) => {
    if (s.type === 'command') return s.action.trim().length > 0;
    if (s.type === 'run_macro') return s.action.trim().length > 0;
    return false;
  });

  if (validSteps.length === 0) {
    toast.showToast('warning', 'No Valid Steps', 'Add at least one step with a command or macro target.');
    return;
  }

  const backendSteps = stepsToBackendFormat(validSteps);
  const shortcut = _state.shortcuts[name] || '';

  try {
    const result = await api.post('/api/v1/macros/save', {
      name,
      steps: backendSteps,
      shortcut,
    });

    if (result && result.ok) {
      toast.showToast('success', 'Macro Saved', `Macro "${name}" updated.`);
      _state.editing.delete(name);
      delete _state.editData[name];
      await loadData();
    } else {
      const msg = (result && result.data && result.data.error) || 'Failed to save macro.';
      toast.showToast('error', 'Save Failed', msg);
    }
  } catch (err) {
    console.error('[macros] Save edits error:', err);
    toast.showToast('error', 'Save Failed', err.message || 'Could not save macro.');
  }
}

/* ── Delete Action ──────────────────────────────────────────────────────── */

async function deleteMacro(name) {
  const api = getApi();
  if (!api) {
    toast.showToast('error', 'Error', 'API client not available.');
    return;
  }

  try {
    const result = await api.del('/api/v1/macros/delete', { body: { name } });

    if (result && result.ok) {
      toast.showToast('success', 'Macro Deleted', `Macro "${name}" deleted.`);
      _state.expanded.delete(name);
      await loadData();
    } else {
      const msg = (result && result.data && result.data.error) || 'Failed to delete macro.';
      toast.showToast('error', 'Delete Failed', msg);
    }
  } catch (err) {
    console.error('[macros] Delete error:', err);
    toast.showToast('error', 'Delete Failed', err.message || 'Could not delete macro.');
  }
}

/* ── Import / Export ────────────────────────────────────────────────────── */

async function exportMacros() {
  const api = getApi();
  if (!api) {
    toast.showToast('error', 'Error', 'API client not available.');
    return;
  }

  try {
    // Fetch the export data as raw text
    const resp = await fetch('/api/v1/macros/export');
    if (!resp.ok) {
      toast.showToast('error', 'Export Failed', `Server returned ${resp.status}`);
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'fiona-macros.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.showToast('success', 'Exported', 'Macros exported successfully.');
  } catch (err) {
    console.error('[macros] Export error:', err);
    toast.showToast('error', 'Export Failed', err.message || 'Could not export macros.');
  }
}

async function importMacrosFromFile(file) {
  const api = getApi();
  if (!api) {
    toast.showToast('error', 'Error', 'API client not available.');
    return;
  }

  try {
    const text = await file.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      toast.showToast('error', 'Import Failed', 'File is not valid JSON.');
      return;
    }

    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      toast.showToast('error', 'Import Failed', 'File must contain a JSON object with macro definitions.');
      return;
    }

    const result = await api.post('/api/v1/macros/import', data);

    if (result && result.ok) {
      const count = result.data?.count || 0;
      toast.showToast('success', 'Imported', `${count} macro(s) imported.`);
      await loadData();
    } else {
      const msg = (result && result.data && result.data.error) || 'Failed to import macros.';
      toast.showToast('error', 'Import Failed', msg);
    }
  } catch (err) {
    console.error('[macros] Import error:', err);
    toast.showToast('error', 'Import Failed', err.message || 'Could not import macros.');
  }
}

/* ── Actions ────────────────────────────────────────────────────────────── */

async function executeMacro(name, dryRun = false) {
  const api = getApi();
  if (!api) {
    toast.showToast('error', 'Error', 'API client not available.');
    return;
  }

  // Set loading state
  _state.results[name] = { loading: true, data: null, error: null };
  // Ensure expanded so results are visible
  _state.expanded.add(name);

  if (_state.container) await renderPage(_state.container);

  try {
    const result = await api.post('/api/v1/macros/run', { name, dry_run: dryRun });

    if (result && result.ok) {
      _state.results[name] = {
        loading: false,
        data: result.data || [],
        error: null,
      };
      toast.showToast(
        'success',
        dryRun ? 'Preview Complete' : 'Macro Executed',
        dryRun
          ? `Dry run completed for "${name}".`
          : `Macro "${name}" executed successfully.`,
      );
    } else {
      const msg =
        (result && result.data && result.data.error) ||
        (result && result.message) ||
        'Unknown error';
      _state.results[name] = {
        loading: false,
        data: null,
        error: msg,
      };
      toast.showToast('error', 'Execution Failed', msg);
    }
  } catch (err) {
    console.error('[macros] Execute error:', err);
    _state.results[name] = {
      loading: false,
      data: null,
      error: err.message || 'Failed to execute macro.',
    };
    toast.showToast(
      'error',
      'Execution Failed',
      err.message || 'Could not run macro.',
    );
  }

  if (!_state.destroyed && _state.container) {
    await renderPage(_state.container);
  }
}

/* ── Data Loading ───────────────────────────────────────────────────────── */

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
    const result = await api.get('/api/v1/macros');

    // Expected: { ok: true, data: { macroName: [steps] }, shortcuts: { ... } }
    const rawMacros =
      result && result.ok && result.data ? result.data : {};
    const shortcuts =
      result && result.shortcuts ? result.shortcuts : {};

    // Store shortcuts
    _state.shortcuts = shortcuts;

    // Convert to sorted array
    const entries = Object.keys(rawMacros)
      .filter((name) => Array.isArray(rawMacros[name]))
      .map((name) => ({
        name,
        steps: rawMacros[name],
      }))
      .sort((a, b) => a.name.localeCompare(b.name));

    _state.macros = rawMacros;
    _state.macrosArray = entries;
    _state.error = false;
    _state.loading = false;

    if (!_state.destroyed && _state.container) {
      await renderPage(_state.container);
    }
  } catch (err) {
    console.error('[macros] Failed to load macros:', err);
    _state.error = true;
    _state.errorMessage = err.message || 'Failed to fetch macros.';
    _state.loading = false;
    if (!_state.destroyed && _state.container) {
      await renderPage(_state.container);
    }
  }
}

/* ── Lifecycle ───────────────────────────────────────────────────────────── */

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

  loadPersistedState();
  renderSkeletons(container);
  loadData();
}

/**
 * Cleanup — called when navigating away.
 */
export function destroy() {
  _state.destroyed = true;

  // Remove bound listeners
  for (const fn of _state._boundListeners) {
    try {
      fn();
    } catch (e) {
      /* ignore */
    }
  }
  _state._boundListeners = [];

  _state.container = null;
  _state.macros = {};
  _state.macrosArray = [];
  _state.results = {};
  _state.expanded = new Set();
  _state.dryRunEnabled = {};

  // Clean up new state
  _state.isRecording = false;
  _state.recordingName = '';
  _state.recordingSteps = [];
  _state.editing = new Set();
  _state.editData = {};
  _state.shortcuts = {};
  _state.capturingShortcut = null;
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
      return '<div id="macros-root"></div>';
    },
    mount(container) {
      const root = container.querySelector('#macros-root') || container;
      render(root);
    },
    destroy,
  };
}
