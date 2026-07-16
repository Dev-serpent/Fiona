/* ==========================================================================
   file-explorer.js — File Explorer Page
   ==========================================================================
   A file browser for navigating the Fiona project filesystem with split
   panel (directory tree | file preview), breadcrumb navigation, toolbar
   actions, context menus, file search, grid/list view toggle, drag-and-
   drop upload, and syntax-highlighted file preview.

   Exports: { render(routeInfo), mount(container), destroy() }
   ========================================================================== */

import { html } from '../js/components/BaseComponent.js';
import { ICONS } from '../js/components/_icons.js';
import { contextMenu } from '../js/components/ContextMenu.js';
import { modal } from '../js/components/Modal.js';
import { toast } from '../js/components/Toast.js';
import { loadTemplate } from '../js/template-loader.js';

/* ── API Helper ─────────────────────────────────────────────────────────── */

function getApi() {
  return window.fiona?.api || window.__fiona?.api;
}

/* ── Constants ──────────────────────────────────────────────────────────── */

const DEFAULT_ROOT = '/home/Dhruv/Documents/Projects/Fiona';
const TEXT_EXTENSIONS = new Set([
  'py', 'js', 'ts', 'jsx', 'tsx', 'css', 'scss', 'less', 'html', 'htm',
  'md', 'markdown', 'json', 'yaml', 'yml', 'toml', 'txt', 'cfg', 'conf',
  'ini', 'env', 'sh', 'bash', 'zsh', 'rb', 'go', 'rs', 'java', 'c', 'cpp',
  'h', 'hpp', 'sql', 'r', 'm', 'swift', 'kt', 'dockerfile', 'makefile',
  'xml', 'svg', 'vue', 'svelte', 'astro', 'php',
]);
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp', 'ico']);
const MAX_TEXT_PREVIEW = 50000; // max chars to preview
const MOBILE_BREAKPOINT = 768; // px

/* ─── Page State ──────────────────────────────────────────────────────────── */

let _container = null;
let _state = {
  currentPath: '',
  entries: [],
  selectedPath: null,
  selectedEntry: null,
  fileContent: null,
  fileInfo: null,
  isLoading: false,
  hasError: false,
  errorMessage: '',
  viewMode: 'list',        // 'list' | 'grid'
  searchQuery: '',
  expandedDirs: new Set(),
  breadcrumb: [],
  isDragging: false,
  previewType: null,        // 'text' | 'image' | 'metadata' | 'loading' | null
  rootPath: DEFAULT_ROOT,
  isMobile: window.innerWidth <= MOBILE_BREAKPOINT,
  treeVisible: false,       // mobile: tree panel toggle
  previewOpen: false,       // mobile: preview sheet toggle
};

let _unbindFns = [];
let _isDestroyed = false;

// Debounce timers
let _searchTimer = null;
let _resizeTimer = null;

/* ── Helper Functions ─────────────────────────────────────────────────────── */

function _escapeHtml(str) {
  if (str == null) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return String(str).replace(/[&<>"']/g, (ch) => map[ch]);
}

function formatFileSize(bytes) {
  if (bytes == null) return '';
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const size = (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0);
  return `${size} ${units[i]}`;
}

function formatDate(timestamp) {
  if (!timestamp) return '';
  const date = new Date(timestamp * 1000);
  const now = new Date();
  const diff = now - date;
  if (diff < 60000) return 'Just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function getFileExtension(filename) {
  const dot = filename.lastIndexOf('.');
  if (dot === -1) return '';
  return filename.slice(dot + 1).toLowerCase();
}

function isTextFile(filename) {
  const ext = getFileExtension(filename);
  return TEXT_EXTENSIONS.has(ext);
}

function isImageFile(filename) {
  const ext = getFileExtension(filename);
  return IMAGE_EXTENSIONS.has(ext);
}

function getFileTypeIcon(entry) {
  if (entry.type === 'directory') {
    return ICONS.folder;
  }
  const ext = getFileExtension(entry.name);
  if (['js', 'ts', 'jsx', 'tsx', 'py', 'go', 'rs', 'java', 'c', 'cpp'].includes(ext)) {
    return ICONS.fileCode;
  }
  if (['json', 'yaml', 'yml', 'toml', 'xml'].includes(ext)) {
    return ICONS.fileJson;
  }
  if (['md', 'txt', 'cfg', 'conf', 'ini', 'env'].includes(ext)) {
    return ICONS.fileText;
  }
  if (IMAGE_EXTENSIONS.has(ext)) {
    return ICONS.file;
  }
  return ICONS.file;
}

/* ── Breadcrumb ──────────────────────────────────────────────────────────── */

function buildBreadcrumb(path) {
  if (!path) return [];
  const parts = path.split('/').filter(Boolean);
  const crumbs = [];
  let accumulated = '';
  for (const part of parts) {
    accumulated += '/' + part;
    crumbs.push({ label: part, path: accumulated });
  }
  return crumbs;
}

/* ── API Calls ────────────────────────────────────────────────────────────── */

async function fetchDirList(path) {
  const api = getApi();
  if (!api) throw new Error('API not available');
  return api.get('/api/v1/files/list', { path });
}

async function fetchFileContent(path) {
  const api = getApi();
  if (!api) throw new Error('API not available');
  return api.get('/api/v1/files/read', { path });
}

async function fetchFileInfo(path) {
  const api = getApi();
  if (!api) throw new Error('API not available');
  return api.get('/api/v1/files/info', { path });
}

async function writeFile(path, content) {
  const api = getApi();
  if (!api) throw new Error('API not available');
  return api.post('/api/v1/files/write', { path, content });
}

async function renameFileApi(path, newName) {
  const api = getApi();
  if (!api) throw new Error('API not available');
  return api.post('/api/v1/files/rename', { path, newName });
}

async function deleteFileApi(path) {
  const api = getApi();
  if (!api) throw new Error('API not available');
  return api.delete('/api/v1/files/delete', { body: { path } });
}

/* ── Workspace Integration ──────────────────────────────────────────────── */

/**
 * Read the current workspace path from the global store, if available.
 * Falls back to the hardcoded DEFAULT_ROOT if no workspace is set.
 */
function getWorkspaceRoot() {
  try {
    const store = window.fiona?.store;
    if (store && typeof store.get === 'function') {
      return store.get('workspace.currentPath') || store.get('workspace.path') || '';
    }
  } catch (e) {
    // Store not available — ignore
  }
  return '';
}

/* ── Navigation ──────────────────────────────────────────────────────────── */

async function navigateTo(path) {
  if (_isDestroyed) return;
  _state.isLoading = true;
  _state.hasError = false;
  _state.errorMessage = '';
  _state.selectedPath = null;
  _state.selectedEntry = null;
  _state.fileContent = null;
  _state.fileInfo = null;
  _state.previewType = null;
  _state.searchQuery = '';

  renderContent();

  try {
    const entries = await fetchDirList(path);
    _state.currentPath = path;
    _state.breadcrumb = buildBreadcrumb(path);
    _state.entries = entries || [];
    _state.isLoading = false;
  } catch (err) {
    _state.isLoading = false;
    _state.hasError = true;
    _state.errorMessage = err.message || 'Failed to load directory';
    console.error('[FileExplorer] navigate error:', err);
  }

  renderContent();
  renderBreadcrumb();
  renderToolbar();
}

/* ── File Selection ───────────────────────────────────────────────────────── */

async function selectFile(path, entry) {
  if (_isDestroyed) return;
  _state.selectedPath = path;
  _state.selectedEntry = entry;
  // On mobile, auto-open preview sheet when selecting a file
  if (_state.isMobile && entry.type !== 'directory') {
    _state.previewOpen = true;
  }

  // Update tree highlight
  _highlightTreeNode(path);

  if (entry.type === 'directory') {
    navigateTo(path);
    return;
  }

  // Show loading preview
  _state.previewType = 'loading';
  renderPreview();

  try {
    if (isImageFile(entry.name)) {
      // Images: just show metadata + img tag
      _state.fileContent = null;
      _state.fileInfo = await fetchFileInfo(path);
      _state.previewType = 'image';
    } else if (isTextFile(entry.name)) {
      // Text files: read content
      const result = await fetchFileContent(path);
      _state.fileContent = result?.content || '';
      _state.fileInfo = await fetchFileInfo(path);
      _state.previewType = 'text';
    } else {
      // Other files: just metadata
      _state.fileContent = null;
      _state.fileInfo = await fetchFileInfo(path);
      _state.previewType = 'metadata';
    }
  } catch (err) {
    console.error('[FileExplorer] selectFile error:', err);
    _state.previewType = 'metadata';
    _state.fileInfo = _state.fileInfo || { name: entry.name, size: entry.size, modified: entry.modified, type: 'file' };
  }

  renderPreview();
}

/* ── Render Functions ──────────────────────────────────────────────────────── */

function renderLoadingSkeleton() {
  return html`
    <div class="fe-skeleton">
      <div class="fe-skeleton__toolbar">
        <div class="c-skeleton c-skeleton--button" style="width: 80px;"></div>
        <div class="c-skeleton c-skeleton--button" style="width: 80px;"></div>
        <div class="c-skeleton c-skeleton--button" style="width: 80px;"></div>
      </div>
      <div class="fe-skeleton__body">
        <div class="fe-skeleton__tree">
          <div class="c-skeleton c-skeleton--text" style="width: 60%;"></div>
          <div class="c-skeleton c-skeleton--text" style="width: 80%;"></div>
          <div class="c-skeleton c-skeleton--text" style="width: 45%;"></div>
          <div class="c-skeleton c-skeleton--text" style="width: 70%;"></div>
          <div class="c-skeleton c-skeleton--text" style="width: 55%;"></div>
        </div>
        <div class="fe-skeleton__preview">
          <div class="c-skeleton c-skeleton--heading" style="width: 30%;"></div>
          <div class="c-skeleton c-skeleton--text"></div>
          <div class="c-skeleton c-skeleton--text"></div>
          <div class="c-skeleton c-skeleton--text" style="width: 60%;"></div>
          <div class="c-skeleton c-skeleton--rect" style="height: 200px; margin-top: 12px;"></div>
        </div>
      </div>
    </div>
  `;
}

function renderErrorState() {
  return html`
    <div class="fe-error">
      <div class="fe-error__icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.5" width="48" height="48"
             stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="15" y1="9" x2="9" y2="15"/>
          <line x1="9" y1="9" x2="15" y2="15"/>
        </svg>
      </div>
      <div class="fe-error__title">Failed to Load Directory</div>
      <div class="fe-error__desc">${_escapeHtml(_state.errorMessage)}</div>
      <button class="c-btn c-btn--primary" data-action="fe-retry" style="margin-top: 16px;">
        Retry
      </button>
    </div>
  `;
}

/**
 * Render the main page content.
 */
function renderContent() {
  if (!_container) return;
  const contentEl = _container.querySelector('.fe-content-panel');
  if (!contentEl) return;

  if (_state.isLoading) {
    contentEl.innerHTML = renderLoadingSkeleton();
    return;
  }

  if (_state.hasError) {
    contentEl.innerHTML = renderErrorState();
    return;
  }

  const filtered = _state.searchQuery
    ? _state.entries.filter((e) =>
        e.name.toLowerCase().includes(_state.searchQuery.toLowerCase())
      )
    : _state.entries;

  const viewClass = _state.viewMode === 'grid' ? 'fe-file-grid' : 'fe-file-list';

  contentEl.innerHTML = html`
    <div class="fe-file-toolbar">
      ${_state.isMobile ? html`
        <button class="fe-tree-toggle" data-action="fe-toggle-tree"
                title="Toggle file tree" aria-label="Toggle file tree">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" width="16" height="16"
               stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
        </button>
      ` : ''}
      <div class="fe-file-search">
        <span class="fe-file-search__icon">${ICONS.search}</span>
        <input type="text" class="fe-file-search__input"
               id="fe-search-input"
               placeholder="Search in this directory…"
               value="${_escapeHtml(_state.searchQuery)}"
               autocomplete="off" />
      </div>
      <div class="fe-file-actions">
        <button class="c-btn c-btn--icon c-btn--sm ${_state.viewMode === 'list' ? 'c-btn--primary' : ''}"
                data-action="fe-view-list" title="List view">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" width="14" height="14"
               stroke-linecap="round" stroke-linejoin="round">
            <line x1="8" y1="6" x2="21" y2="6"/>
            <line x1="8" y1="12" x2="21" y2="12"/>
            <line x1="8" y1="18" x2="21" y2="18"/>
            <line x1="3" y1="6" x2="3.01" y2="6"/>
            <line x1="3" y1="12" x2="3.01" y2="12"/>
            <line x1="3" y1="18" x2="3.01" y2="18"/>
          </svg>
        </button>
        <button class="c-btn c-btn--icon c-btn--sm ${_state.viewMode === 'grid' ? 'c-btn--primary' : ''}"
                data-action="fe-view-grid" title="Grid view">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" width="14" height="14"
               stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="7" height="7"/>
            <rect x="14" y="3" width="7" height="7"/>
            <rect x="14" y="14" width="7" height="7"/>
            <rect x="3" y="14" width="7" height="7"/>
          </svg>
        </button>
      </div>
    </div>

    <div class="${viewClass}" id="fe-file-container">
      ${filtered.length === 0
        ? html`
            <div class="fe-empty">
              <div class="fe-empty__icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     stroke-width="1.5" width="36" height="36"
                     stroke-linecap="round" stroke-linejoin="round">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                </svg>
              </div>
              <div class="fe-empty__text">
                ${_state.searchQuery ? 'No files match your search.' : 'This directory is empty.'}
              </div>
            </div>
          `
        : html.raw(filtered.map((entry) => _renderFileEntry(entry)).join(''))
      }
    </div>
  `;
}

/**
 * Render a single file/directory entry.
 */
function _renderFileEntry(entry) {
  const isDir = entry.type === 'directory';
  const icon = getFileTypeIcon(entry);
  const isSelected = entry.path === _state.selectedPath;

  if (_state.viewMode === 'grid') {
    return html`
      <div class="fe-file-item fe-file-item--grid ${isSelected ? 'fe-file-item--selected' : ''}"
           data-path="${_escapeHtml(entry.path)}"
           data-type="${entry.type}"
           data-name="${_escapeHtml(entry.name)}"
           draggable="true">
        <div class="fe-file-item__icon fe-file-item__icon--grid">
          ${isDir
            ? html`<span style="width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;">${icon}</span>`
            : html`<span style="width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;">${icon}</span>`
          }
        </div>
        <div class="fe-file-item__name fe-file-item__name--grid">${_escapeHtml(entry.name)}</div>
        <div class="fe-file-item__meta">${isDir ? '' : formatFileSize(entry.size)}</div>
      </div>
    `;
  }

  return html`
    <div class="fe-file-item fe-file-item--list ${isSelected ? 'fe-file-item--selected' : ''}"
         data-path="${_escapeHtml(entry.path)}"
         data-type="${entry.type}"
         data-name="${_escapeHtml(entry.name)}"
         draggable="true">
      <span class="fe-file-item__icon">${icon}</span>
      <span class="fe-file-item__name">${_escapeHtml(entry.name)}</span>
      <span class="fe-file-item__meta fe-file-item__size">${isDir ? '—' : formatFileSize(entry.size)}</span>
      <span class="fe-file-item__meta fe-file-item__date">${formatDate(entry.modified)}</span>
    </div>
  `;
}

/**
 * Render the preview pane.
 */
function renderPreview() {
  const previewEl = _container?.querySelector('.fe-preview');
  if (!previewEl) return;

  // On mobile, always sync preview open/closed state
  if (_state.isMobile) {
    previewEl.classList.toggle('fe-preview--open', _state.previewOpen);
  }

  if (!_state.selectedEntry) {
    previewEl.innerHTML = html`
      ${_state.isMobile ? html`
        <div class="fe-preview__handle" data-action="fe-toggle-preview"></div>
      ` : ''}
      <div class="fe-preview__empty">
        <div class="fe-preview__empty-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.5" width="36" height="36"
               stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
        </div>
        <div class="fe-preview__empty-text">Select a file to preview</div>
      </div>
    `;
    return;
  }

  if (_state.previewType === 'loading') {
    previewEl.innerHTML = html`
      <div style="padding: 24px;">
        <div class="c-skeleton c-skeleton--heading" style="width: 40%;"></div>
        <div class="c-skeleton c-skeleton--text" style="margin-top: 12px;"></div>
        <div class="c-skeleton c-skeleton--text"></div>
        <div class="c-skeleton c-skeleton--text" style="width: 70%;"></div>
        <div class="c-skeleton c-skeleton--rect" style="height: 200px; margin-top: 16px;"></div>
      </div>
    `;
    return;
  }

  if (_state.previewType === 'text' && _state.fileContent != null) {
    const ext = getFileExtension(_state.selectedEntry.name);
    const content = _state.fileContent.length > MAX_TEXT_PREVIEW
      ? _state.fileContent.slice(0, MAX_TEXT_PREVIEW) + '\n\n… [truncated]'
      : _state.fileContent;
    const highlighted = highlightCode(content, ext);

    previewEl.innerHTML = html`
      ${_state.isMobile ? html`<div class="fe-preview__handle" data-action="fe-toggle-preview"></div>` : ''}
      <div class="fe-preview__header">
        <span class="fe-preview__filename">${_escapeHtml(_state.selectedEntry.name)}</span>
        <span class="fe-preview__filemeta">
          ${formatFileSize(_state.selectedEntry.size)} · ${(_state.fileContent.length / 1024).toFixed(1)} KB
        </span>
      </div>
      <div class="fe-preview__code">
        <pre><code>${html.raw(highlighted)}</code></pre>
      </div>
    `;
    return;
  }

  if (_state.previewType === 'image') {
    // Image files: show preview via API endpoint
    const imgPath = _state.selectedEntry.path;
    previewEl.innerHTML = html`
      ${_state.isMobile ? html`<div class="fe-preview__handle" data-action="fe-toggle-preview"></div>` : ''}
      <div class="fe-preview__header">
        <span class="fe-preview__filename">${_escapeHtml(_state.selectedEntry.name)}</span>
        <span class="fe-preview__filemeta">${formatFileSize(_state.selectedEntry.size)}</span>
      </div>
      <div class="fe-preview__image">
        <img src="/api/v1/files/read?path=${encodeURIComponent(imgPath)}"
             alt="${_escapeHtml(_state.selectedEntry.name)}"
             style="max-width: 100%; max-height: 60vh; object-fit: contain;"
             onerror="this.parentElement.innerHTML='<div class=\\'fe-preview__error\\'>Image preview unavailable</div>'" />
      </div>
    `;
    return;
  }

  // Default: metadata view
  const info = _state.fileInfo || _state.selectedEntry;
  previewEl.innerHTML = html`
    ${_state.isMobile ? html`<div class="fe-preview__handle" data-action="fe-toggle-preview"></div>` : ''}
    <div class="fe-preview__header">
      <span class="fe-preview__filename">${_escapeHtml(_state.selectedEntry.name)}</span>
    </div>
    <div class="fe-preview__metadata">
      <div class="fe-preview__meta-row">
        <span class="fe-preview__meta-label">Type</span>
        <span class="fe-preview__meta-value">
          ${info.type || _state.selectedEntry.type}
          ${info.type === 'directory' ? '' : `.${getFileExtension(_state.selectedEntry.name)}`}
        </span>
      </div>
      <div class="fe-preview__meta-row">
        <span class="fe-preview__meta-label">Size</span>
        <span class="fe-preview__meta-value">${formatFileSize(info.size ?? _state.selectedEntry.size)}</span>
      </div>
      <div class="fe-preview__meta-row">
        <span class="fe-preview__meta-label">Modified</span>
        <span class="fe-preview__meta-value">${info.modified ? new Date(info.modified * 1000).toLocaleString() : formatDate(info.modified ?? _state.selectedEntry.modified)}</span>
      </div>
      ${info.created ? html`
      <div class="fe-preview__meta-row">
        <span class="fe-preview__meta-label">Created</span>
        <span class="fe-preview__meta-value">${new Date(info.created * 1000).toLocaleString()}</span>
      </div>
      ` : ''}
      ${info.permissions ? html`
      <div class="fe-preview__meta-row">
        <span class="fe-preview__meta-label">Permissions</span>
        <span class="fe-preview__meta-value">${_escapeHtml(info.permissions)}</span>
      </div>
      ` : ''}
      ${info.owner != null ? html`
      <div class="fe-preview__meta-row">
        <span class="fe-preview__meta-label">Owner (UID)</span>
        <span class="fe-preview__meta-value">${_escapeHtml(String(info.owner))}</span>
      </div>
      ` : ''}
      ${info.path ? html`
      <div class="fe-preview__meta-row" style="align-items: flex-start;">
        <span class="fe-preview__meta-label" style="padding-top: 2px;">Path</span>
        <span class="fe-preview__meta-value fe-preview__meta-value--path">${_escapeHtml(info.path)}</span>
      </div>
      ` : ''}
    </div>
  `;
}

/**
 * Render the breadcrumb navigation.
 */
function renderBreadcrumb() {
  const el = _container?.querySelector('.fe-breadcrumb');
  if (!el) return;

  el.innerHTML = html.raw(_state.breadcrumb.map((crumb, i) => html`
    ${i > 0 ? html`<span class="fe-breadcrumb__sep">${ICONS.chevronRight}</span>` : ''}
    <span class="fe-breadcrumb__item ${i === _state.breadcrumb.length - 1 ? 'fe-breadcrumb__item--active' : ''}"
          data-breadcrumb-path="${_escapeHtml(crumb.path)}">
      ${_escapeHtml(crumb.label)}
    </span>
  `).join(''));
}

/**
 * Render the toolbar actions.
 */
function renderToolbar() {
  const el = _container?.querySelector('.fe-toolbar-actions');
  if (!el) return;

  // Toolbar is already in the HTML, just update the refresh visibility etc.
}

/**
 * Highlight a tree node by path.
 */
function _highlightTreeNode(path) {
  const tree = _container?.querySelector('.fe-tree');
  if (!tree) return;
  tree.querySelectorAll('.fe-tree-item').forEach((el) => {
    el.classList.toggle('fe-tree-item--selected', el.dataset.path === path);
  });
}

/* ── Syntax Highlighting ──────────────────────────────────────────────────── */

/**
 * Basic syntax highlighting for common file types.
 * Returns HTML with <span class="hl-*"> tags.
 */
function highlightCode(code, ext) {
  if (!code) return '';

  const escaped = _escapeHtml(code);

  // Simple line-by-line highlighting for common patterns
  const lines = escaped.split('\n');
  const highlighted = lines.map((line) => {
    let result = line;

    // Comments (single line)
    if (['py', 'rb', 'sh', 'bash', 'yaml', 'yml', 'toml', 'r', 'makefile'].includes(ext)) {
      result = result.replace(/(#.*)$/g, '<span class="hl-comment">$1</span>');
    } else if (['js', 'ts', 'jsx', 'tsx', 'go', 'rs', 'java', 'c', 'cpp', 'h', 'hpp', 'css', 'scss', 'less', 'php', 'swift', 'kt'].includes(ext)) {
      result = result.replace(/(\/\/.*)$/g, '<span class="hl-comment">$1</span>');
      result = result.replace(/(\/\*[\s\S]*?\*\/)/g, '<span class="hl-comment">$1</span>');
    } else if (['html', 'htm', 'xml', 'svg', 'vue', 'svelte', 'astro'].includes(ext)) {
      result = result.replace(/(&lt;!--[\s\S]*?--&gt;)/g, '<span class="hl-comment">$1</span>');
    }

    // Strings (double quotes)
    result = result.replace(/(&quot;[^&quot;]*&quot;)/g, '<span class="hl-string">$1</span>');
    // Strings (single quotes)
    result = result.replace(/(&#39;[^&#39;]*&#39;)/g, '<span class="hl-string">$1</span>');
    // Template literals
    result = result.replace(/(`[^`]*`)/g, '<span class="hl-string">$1</span>');

    // Keywords
    const keywords = [
      '\\b(import|export|from|default|as|const|let|var|function|return|if|else|for|while|do|switch|case|break|continue|new|delete|typeof|instanceof|class|extends|super|this|async|await|yield|try|catch|finally|throw|in|of|with|void|null|undefined|true|false|static|get|set|private|protected|public|readonly|enum|interface|type|implements|abstract|namespace|module|declare)\\b',
      '\\b(def|class|return|if|elif|else|for|while|import|from|as|try|except|finally|raise|with|pass|break|continue|lambda|yield|and|or|not|is|in|True|False|None|self|async|await|global|nonlocal|assert|del|print|len|range|map|filter|zip|enumerate|sorted|reversed|open|with|if|else|elif)\\b',
      '\\b(func|var|if|else|for|range|return|import|package|nil|true|false|defer|go|chan|select|switch|case|break|continue|fallthrough|default|map|struct|interface|type|const)\\b',
    ];

    for (const kwPattern of keywords) {
      try {
        result = result.replace(new RegExp(kwPattern, 'g'), '<span class="hl-keyword">$1</span>');
      } catch { /* skip bad patterns */ }
    }

    // Numbers
    result = result.replace(/\b(\d+\.?\d*)\b/g, '<span class="hl-number">$1</span>');

    // Function calls
    result = result.replace(/\b([a-zA-Z_$][\w$]*)\s*(\()/g, '<span class="hl-function">$1</span>$2');

    return result;
  });

  return highlighted.join('\n');
}

/* ── Tree Rendering ────────────────────────────────────────────────────────── */

async function renderTree() {
  const treeEl = _container?.querySelector('.fe-tree');
  if (!treeEl) return;

  const path = _state.rootPath;

  try {
    const entries = await fetchDirList(path);

    treeEl.innerHTML = html`
      <div class="fe-tree-item fe-tree-item--root"
           data-path="${_escapeHtml(path)}"
           data-type="directory">
        <span class="fe-tree-item__icon">${ICONS.folder}</span>
        <span class="fe-tree-item__label">Project Root</span>
        <span class="fe-tree-item__chevron ${_state.expandedDirs.has(path) ? 'fe-tree-item__chevron--open' : ''}">
          ${ICONS.chevronDown}
        </span>
      </div>
      ${_state.expandedDirs.has(path)
        ? html.raw(renderTreeChildren(entries || [], path, 1))
        : ''
      }
    `;

    bindTreeEvents();
  } catch (err) {
    console.error('[FileExplorer] Failed to load tree root:', err);
    treeEl.innerHTML = html`
      <div class="fe-tree__error">Failed to load file tree</div>
    `;
  }
}

function renderTreeChildren(entries, parentPath, depth) {
  const sorted = [...entries].sort((a, b) => {
    if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
    return a.name.localeCompare(b.name);
  });

  return sorted.map((entry) => {
    const isDir = entry.type === 'directory';
    const isExpanded = _state.expandedDirs.has(entry.path);
    const icon = isDir ? ICONS.folder : getFileTypeIcon(entry);

    return html`
      <div class="fe-tree-item ${_state.selectedPath === entry.path ? 'fe-tree-item--selected' : ''}"
           data-path="${_escapeHtml(entry.path)}"
           data-type="${entry.type}"
           data-name="${_escapeHtml(entry.name)}"
           style="padding-left: ${12 + depth * 16}px;">
        <span class="fe-tree-item__icon">${icon}</span>
        <span class="fe-tree-item__label">${_escapeHtml(entry.name)}</span>
        ${isDir ? html`
          <span class="fe-tree-item__chevron ${isExpanded ? 'fe-tree-item__chevron--open' : ''}">
            ${ICONS.chevronDown}
          </span>
        ` : ''}
      </div>
      ${isDir && isExpanded
        ? html`<div class="fe-tree-children" data-dir="${_escapeHtml(entry.path)}">${renderTreeChildrenPlaceholder(entry.path, depth + 1)}</div>`
        : ''
      }
    `;
  }).join(''));
}

function renderTreeChildrenPlaceholder(dirPath, depth) {
  // Will be lazily loaded
  return html`
    <div style="padding: 8px ${12 + depth * 16}px; color: #484f58; font-size: 11px;">
      Loading…
    </div>
  `;
}

async function expandTreeNode(dirPath) {
  if (_state.expandedDirs.has(dirPath)) {
    _state.expandedDirs.delete(dirPath);
    renderTree();
    return;
  }

  _state.expandedDirs.add(dirPath);

  try {
    const entries = await fetchDirList(dirPath);
    // After loading, re-render the tree
    renderTree();
  } catch (err) {
    console.error('[FileExplorer] expand error:', err);
    _state.expandedDirs.delete(dirPath);
  }
}

/* ── Tree Events ──────────────────────────────────────────────────────────── */

function bindTreeEvents() {
  const treeEl = _container?.querySelector('.fe-tree');
  if (!treeEl) return;

  treeEl.querySelectorAll('.fe-tree-item').forEach((item) => {
    // Click: select / expand
    item.addEventListener('click', async (e) => {
      const path = item.dataset.path;
      const type = item.dataset.type;

      if (!path) return;

      if (type === 'directory') {
        // Don't navigate to root if already there, just expand
        if (path === _state.rootPath) {
          // Toggle root expansion
          _state.expandedDirs.has(path)
            ? _state.expandedDirs.delete(path)
            : _state.expandedDirs.add(path);
          renderTree();
          return;
        }
        navigateTo(path);
      } else {
        // Find the entry and select it
        const name = item.dataset.name;
        selectFile(path, { name, path, type, size: 0 });
        renderTree(); // to update selection highlighting
      }
    });

    // Context menu
    item.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      const path = item.dataset.path;
      const type = item.dataset.type;
      const name = item.dataset.name;

      showFileContextMenu(e.clientX, e.clientY, { name, path, type });
    });
  });
}

/* ── Context Menu ──────────────────────────────────────────────────────────── */

function showFileContextMenu(x, y, entry) {
  const items = [
    {
      label: 'Copy Path',
      icon: 'copy',
      handler: () => {
        navigator.clipboard.writeText(entry.path).catch(() => {});
      },
    },
    {
      label: 'Download',
      icon: 'download',
      disabled: entry.type === 'directory',
      handler: () => {
        downloadFile(entry.path, entry.name);
      },
    },
    { divider: true },
    {
      label: 'Rename',
      icon: 'edit',
      handler: () => {
        showRenameDialog(entry);
      },
    },
    {
      label: 'Delete',
      icon: 'trash',
      danger: true,
      handler: () => {
        showDeleteDialog(entry);
      },
    },
  ];

  // Workspace-related options for directories
  if (entry.type === 'directory') {
    items.push({ divider: true });
    items.push({
      label: 'Set as Workspace Root',
      icon: 'folder',
      handler: () => {
        setWorkspaceRoot(entry.path);
      },
    });
    items.push({
      label: 'Open in Workspace',
      icon: 'externalLink',
      handler: () => {
        openInWorkspace(entry.path);
      },
    });
  }

  contextMenu.showContextMenu(x, y, items);
}

function setWorkspaceRoot(dirPath) {
  const store = window.fiona?.store;
  if (store && typeof store.set === 'function') {
    store.set('workspace.currentPath', dirPath);
    toast.showToast('success', 'Workspace Root Set', `Root changed to "${dirPath.split('/').pop()}"`);
    // Reload the file explorer with the new root
    _state.rootPath = dirPath;
    navigateTo(dirPath);
    renderTree();
  } else {
    toast.showToast('warning', 'Not Available', 'Workspace store is not available');
  }
}

function openInWorkspace(dirPath) {
  const router = window.fiona?.router;
  if (router && typeof router.navigate === 'function') {
    // Navigate to the workspace tab, optionally passing the path
    router.navigate('/workspace');
    // Set the workspace path for the workspace page to pick up
    const store = window.fiona?.store;
    if (store && typeof store.set === 'function') {
      store.set('workspace.currentPath', dirPath);
    }
  } else {
    toast.showToast('warning', 'Not Available', 'Router is not available');
  }
}

function downloadFile(path, name) {
  // Trigger download via API
  const api = getApi();
  if (!api) return;
  // Since we can't easily download through the API client, open in new tab
  const baseUrl = api._getBaseURL ? api._getBaseURL() : 'http://localhost:8765';
  window.open(`${baseUrl}/api/v1/files/read?path=${encodeURIComponent(path)}`, '_blank');
}

async function showRenameDialog(entry) {
  const oldName = entry.name;
  const result = await modal.showModal({
    title: 'Rename',
    content: html`
      <div class="c-form-group">
        <label class="c-form-group__label">New name</label>
        <input type="text" class="c-input" id="fe-rename-input"
               value="${_escapeHtml(oldName)}"
               style="margin-top: 8px;" />
      </div>
    `,
    size: 'sm',
    buttons: [
      { label: 'Cancel', value: 'cancel', variant: 'ghost' },
      { label: 'Rename', value: 'rename', variant: 'primary' },
    ],
  });

  if (result !== 'rename') return;

  const renameInput = document.getElementById('fe-rename-input');
  if (!renameInput) return;

  const newName = renameInput.value.trim();
  if (!newName || newName === oldName) return;

  try {
    await renameFileApi(entry.path, newName);
    toast.showToast('success', 'Renamed', `Renamed to "${newName}"`);
    // Refresh current directory
    navigateTo(_state.currentPath);
  } catch (err) {
    console.error('[FileExplorer] rename failed:', err);
    toast.showToast('error', 'Rename Failed', err.message || 'Could not rename file');
  }
}

async function showDeleteDialog(entry) {
  const isDir = entry.type === 'directory';
  const result = await modal.showModal({
    title: 'Delete',
    content: html`
      <p>Are you sure you want to delete <strong>${_escapeHtml(entry.name)}</strong>?</p>
      ${isDir ? '<p style="margin-top: 8px; color: var(--warning);">Only empty directories can be deleted. Files inside must be removed first.</p>' : ''}
    `,
    size: 'sm',
    buttons: [
      { label: 'Cancel', value: 'cancel', variant: 'ghost' },
      { label: 'Delete', value: 'delete', variant: 'danger-solid' },
    ],
  });

  if (result !== 'delete') return;

  try {
    await deleteFileApi(entry.path);
    toast.showToast('success', 'Deleted', `"${entry.name}" has been deleted`);
    // Refresh current directory
    navigateTo(_state.currentPath);
  } catch (err) {
    console.error('[FileExplorer] delete failed:', err);
    toast.showToast('error', 'Delete Failed', err.message || 'Could not delete file');
  }
}

/* ── New File / Folder ────────────────────────────────────────────────────── */

async function showNewFileDialog() {
  const result = await modal.showModal({
    title: 'New File',
    content: html`
      <div class="c-form-group">
        <label class="c-form-group__label">File name</label>
        <input type="text" class="c-input" id="fe-newfile-input"
               placeholder="e.g. example.txt"
               style="margin-top: 8px;" />
      </div>
    `,
    size: 'sm',
    buttons: [
      { label: 'Cancel', value: 'cancel', variant: 'ghost' },
      { label: 'Create', value: 'create', variant: 'primary' },
    ],
  });

  if (result !== 'create') return;

  const input = document.getElementById('fe-newfile-input');
  if (!input) return;

  const name = input.value.trim();
  if (!name) return;

  const path = (_state.currentPath || _state.rootPath) + '/' + name;

  try {
    await writeFile(path, '');
    navigateTo(_state.currentPath || _state.rootPath);
  } catch (err) {
    console.error('[FileExplorer] create file failed:', err);
  }
}

async function showNewFolderDialog() {
  const result = await modal.showModal({
    title: 'New Folder',
    content: html`
      <div class="c-form-group">
        <label class="c-form-group__label">Folder name</label>
        <input type="text" class="c-input" id="fe-newfolder-input"
               placeholder="e.g. new-folder"
               style="margin-top: 8px;" />
      </div>
    `,
    size: 'sm',
    buttons: [
      { label: 'Cancel', value: 'cancel', variant: 'ghost' },
      { label: 'Create', value: 'create', variant: 'primary' },
    ],
  });

  if (result !== 'create') return;

  const input = document.getElementById('fe-newfolder-input');
  if (!input) return;

  const name = input.value.trim();
  if (!name) return;

  const path = (_state.currentPath || _state.rootPath) + '/' + name;
  // For directories, write a .gitkeep equivalent
  try {
    await writeFile(path + '/.gitkeep', '');
    navigateTo(_state.currentPath || _state.rootPath);
  } catch (err) {
    console.error('[FileExplorer] create folder failed:', err);
  }
}

/* ── Event Bindings ────────────────────────────────────────────────────────── */

function bindEvents() {
  if (!_container) return;

  const cleanups = [];

  // ── Breadcrumb clicks ──
  const breadcrumb = _container.querySelector('.fe-breadcrumb');
  if (breadcrumb) {
    const handler = (e) => {
      const item = e.target.closest('[data-breadcrumb-path]');
      if (item) {
        navigateTo(item.dataset.breadcrumbPath);
      }
    };
    breadcrumb.addEventListener('click', handler);
    cleanups.push(() => breadcrumb.removeEventListener('click', handler));
  }

  // ── File container clicks (delegated) ──
  const fileContainer = _container.querySelector('#fe-file-container');
  if (fileContainer) {
    const handler = (e) => {
      const item = e.target.closest('.fe-file-item');
      if (!item) return;
      const path = item.dataset.path;
      const type = item.dataset.type;
      const name = item.dataset.name;
      if (!path) return;

      selectFile(path, { name, path, type, size: 0 });
      renderContent(); // re-render to show selection
    };
    fileContainer.addEventListener('click', handler);
    cleanups.push(() => fileContainer.removeEventListener('click', handler));

    // Context menu on files
    const ctxHandler = (e) => {
      const item = e.target.closest('.fe-file-item');
      if (!item) return;
      e.preventDefault();
      showFileContextMenu(e.clientX, e.clientY, {
        name: item.dataset.name,
        path: item.dataset.path,
        type: item.dataset.type,
      });
    };
    fileContainer.addEventListener('contextmenu', ctxHandler);
    cleanups.push(() => fileContainer.removeEventListener('contextmenu', ctxHandler));

    // Drag and drop file upload
    const dragHandler = _setupDragAndDrop(fileContainer);
    cleanups.push(dragHandler);
  }

  // ── File content toolbar (tree toggle, view toggle) ──
  const fileToolbar = _container.querySelector('.fe-file-toolbar');
  if (fileToolbar) {
    const handler = (e) => {
      const action = e.target.closest('[data-action]');
      if (!action) return;
      switch (action.dataset.action) {
        case 'fe-toggle-tree':
          _state.treeVisible = !_state.treeVisible;
          const treePanel = _container.querySelector('.fe-tree-panel');
          if (treePanel) {
            treePanel.classList.toggle('fe-tree-panel--visible', _state.treeVisible);
          }
          break;
        case 'fe-toggle-preview':
          _state.previewOpen = !_state.previewOpen;
          const previewEl = _container.querySelector('.fe-preview');
          if (previewEl) {
            previewEl.classList.toggle('fe-preview--open', _state.previewOpen);
          }
          break;
      }
    };
    fileToolbar.addEventListener('click', handler);
    cleanups.push(() => fileToolbar.removeEventListener('click', handler));
  }

  // ── Preview handle toggle (mobile) ──
  const previewEl = _container.querySelector('.fe-preview');
  if (previewEl) {
    const handler = (e) => {
      const handle = e.target.closest('.fe-preview__handle');
      if (!handle) return;
      _state.previewOpen = !_state.previewOpen;
      previewEl.classList.toggle('fe-preview--open', _state.previewOpen);
    };
    previewEl.addEventListener('click', handler);
    cleanups.push(() => previewEl.removeEventListener('click', handler));
  }

  // ── Click outside mobile tree panel to close ──
  const treePanel = _container.querySelector('.fe-tree-panel');
  const contentPanel = _container.querySelector('#fe-file-content');
  if (treePanel && contentPanel) {
    const handler = (e) => {
      if (!_state.isMobile || !_state.treeVisible) return;
      if (!treePanel.contains(e.target) && !e.target.closest('.fe-tree-toggle')) {
        _state.treeVisible = false;
        treePanel.classList.remove('fe-tree-panel--visible');
      }
    };
    contentPanel.addEventListener('click', handler);
    cleanups.push(() => contentPanel.removeEventListener('click', handler));
  }

  // ── Long-press on file items (mobile context menu) ──
  const fileContainerEl = _container.querySelector('#fe-file-container');
  if (fileContainerEl) {
    let longPressTimer = null;
    let longPressTriggered = false;

    const touchStart = (e) => {
      const item = e.target.closest('.fe-file-item');
      if (!item) return;
      longPressTriggered = false;
      longPressTimer = setTimeout(() => {
        longPressTriggered = true;
        e.preventDefault();
        const touch = e.touches[0];
        showFileContextMenu(touch.clientX, touch.clientY, {
          name: item.dataset.name,
          path: item.dataset.path,
          type: item.dataset.type,
        });
      }, 500);
    };

    const touchEnd = (e) => {
      if (longPressTimer) {
        clearTimeout(longPressTimer);
        longPressTimer = null;
      }
    };

    const touchMove = () => {
      if (longPressTimer) {
        clearTimeout(longPressTimer);
        longPressTimer = null;
      }
    };

    fileContainerEl.addEventListener('touchstart', touchStart, { passive: false });
    fileContainerEl.addEventListener('touchend', touchEnd);
    fileContainerEl.addEventListener('touchmove', touchMove);
    cleanups.push(() => {
      fileContainerEl.removeEventListener('touchstart', touchStart);
      fileContainerEl.removeEventListener('touchend', touchEnd);
      fileContainerEl.removeEventListener('touchmove', touchMove);
    });
  }

  // ── Search input ──
  const searchInput = _container.querySelector('#fe-search-input');
  if (searchInput) {
    const handler = (e) => {
      clearTimeout(_searchTimer);
      _searchTimer = setTimeout(() => {
        _state.searchQuery = e.target.value;
        renderContent();
      }, 200);
    };
    searchInput.addEventListener('input', handler);
    cleanups.push(() => searchInput.removeEventListener('input', handler));
  }

  // ── Toolbar actions ──
  const toolbar = _container.querySelector('.fe-toolbar');
  if (toolbar) {
    const handler = (e) => {
      const action = e.target.closest('[data-action]');
      if (!action) return;
      const actionName = action.dataset.action;

      switch (actionName) {
        case 'fe-refresh':
          navigateTo(_state.currentPath || _state.rootPath);
          break;
        case 'fe-new-file':
          showNewFileDialog();
          break;
        case 'fe-new-folder':
          showNewFolderDialog();
          break;
        case 'fe-view-list':
          _state.viewMode = 'list';
          renderContent();
          _updateViewToggleButtons();
          break;
        case 'fe-view-grid':
          _state.viewMode = 'grid';
          renderContent();
          _updateViewToggleButtons();
          break;
        case 'fe-retry':
          navigateTo(_state.rootPath);
          break;
      }
    };
    toolbar.addEventListener('click', handler);
    cleanups.push(() => toolbar.removeEventListener('click', handler));
  }

  // ── Resize handler ──
  const resizeHandler = () => {
    clearTimeout(_resizeTimer);
    _resizeTimer = setTimeout(() => {
      const wasMobile = _state.isMobile;
      _state.isMobile = window.innerWidth <= MOBILE_BREAKPOINT;
      if (_state.isMobile !== wasMobile) {
        // Re-render content to add/remove tree toggle, preview handle
        renderContent();
        renderPreview();
        if (!_state.isMobile) {
          // Reset mobile-only states on resize to desktop
          _state.treeVisible = false;
          _state.previewOpen = false;
        }
      }
    }, 150);
  };
  window.addEventListener('resize', resizeHandler);
  cleanups.push(() => window.removeEventListener('resize', resizeHandler));

  _unbindFns = cleanups;
}

function _updateViewToggleButtons() {
  if (!_container) return;
  const listBtn = _container.querySelector('[data-action="fe-view-list"]');
  const gridBtn = _container.querySelector('[data-action="fe-view-grid"]');
  if (listBtn) listBtn.classList.toggle('c-btn--primary', _state.viewMode === 'list');
  if (gridBtn) gridBtn.classList.toggle('c-btn--primary', _state.viewMode === 'grid');
}

function _setupDragAndDrop(container) {
  // Simple drag-over highlight
  let dragCounter = 0;

  const dragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter++;
    container.classList.add('fe-file-container--drag-over');
  };

  const dragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter--;
    if (dragCounter === 0) {
      container.classList.remove('fe-file-container--drag-over');
    }
  };

  const dragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
  };

  const drop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter = 0;
    container.classList.remove('fe-file-container--drag-over');

    const files = Array.from(e.dataTransfer.files);
    if (files.length === 0) return;

    // Upload files to current directory
    for (const file of files) {
      try {
        const text = await file.text();
        const targetPath = (_state.currentPath || _state.rootPath) + '/' + file.name;
        await writeFile(targetPath, text);
      } catch (err) {
        console.error('[FileExplorer] upload failed:', file.name, err);
      }
    }

    // Refresh
    navigateTo(_state.currentPath || _state.rootPath);
  };

  container.addEventListener('dragenter', dragEnter);
  container.addEventListener('dragleave', dragLeave);
  container.addEventListener('dragover', dragOver);
  container.addEventListener('drop', drop);

  return () => {
    container.removeEventListener('dragenter', dragEnter);
    container.removeEventListener('dragleave', dragLeave);
    container.removeEventListener('dragover', dragOver);
    container.removeEventListener('drop', drop);
  };
}

/* ── Global Keybindings ────────────────────────────────────────────────────── */

function bindGlobalKeys() {
  const handler = (e) => {
    // F5 or Ctrl+R = refresh
    if (e.key === 'F5' || (e.key === 'r' && e.ctrlKey)) {
      e.preventDefault();
      navigateTo(_state.currentPath || _state.rootPath);
    }
  };
  document.addEventListener('keydown', handler);
  return () => document.removeEventListener('keydown', handler);
}

/* ── Page Lifecycle ────────────────────────────────────────────────────────── */

/**
 * Render the file explorer page HTML.
 * @param {Object} routeInfo - Route info from router
 * @returns {string} HTML string
 */
function render(routeInfo) {
  // Detect workspace root path from the global store
  const wsPath = getWorkspaceRoot();
  const root = wsPath || DEFAULT_ROOT;

  // Initialize state
  _state.rootPath = root;
  _state.currentPath = root;
  _state.breadcrumb = buildBreadcrumb(root);
  _state.expandedDirs = new Set();
  _state.isLoading = false;
  _state.hasError = false;
  _state.viewMode = 'list';

  // Return mount point; template loaded by mount()
  return '<div id="file-explorer-root"></div>';
}

/**
 * Mount the file explorer page.
 * Loads the HTML template, initializes state, renders tree and content, binds events.
 * @param {Element} container - The page container
 */
async function mount(container) {
  _container = container;
  _isDestroyed = false;

  // Detect workspace root path from the global store
  const wsPath = getWorkspaceRoot();
  const root = wsPath || DEFAULT_ROOT;

  // Load and inject the HTML template
  try {
    const rootEl = container.querySelector('#file-explorer-root') || container;
    const templateHtml = await loadTemplate('file-explorer', {
      rootPath: root,
    });
    rootEl.innerHTML = templateHtml;
  } catch (err) {
    console.error('[FileExplorer] Failed to load template:', err);
  }

  // Initialize rendering
  renderBreadcrumb();
  renderContent();
  renderPreview();

  // Load tree
  await renderTree();

  // Navigate to root for content
  await navigateTo(_state.rootPath);

  // Bind events
  bindEvents();

  // Bind global keys
  const keyCleanup = bindGlobalKeys();
  _unbindFns.push(keyCleanup);
}

/**
 * Destroy the file explorer page.
 * Cleans up all state, event listeners, and DOM references.
 */
function destroy() {
  _isDestroyed = true;

  // Run cleanup functions
  for (const fn of _unbindFns) {
    try { fn(); } catch (e) { /* ignore */ }
  }
  _unbindFns = [];

  // Clear timers
  if (_searchTimer) clearTimeout(_searchTimer);
  if (_resizeTimer) clearTimeout(_resizeTimer);

  // Reset state
  _state = {
    currentPath: '',
    entries: [],
    selectedPath: null,
    selectedEntry: null,
    fileContent: null,
    fileInfo: null,
    isLoading: false,
    hasError: false,
    errorMessage: '',
    viewMode: 'list',
    searchQuery: '',
    expandedDirs: new Set(),
    breadcrumb: [],
    isDragging: false,
    previewType: null,
    rootPath: DEFAULT_ROOT,
  };

  _container = null;
}

/* ── Exports ─────────────────────────────────────────────────────────────── */

export default {
  render,
  mount,
  destroy,
};
