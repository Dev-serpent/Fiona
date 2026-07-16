/* ==========================================================================
   settings.js — Unified Settings Page for Fiona Configuration
   ==========================================================================
   Split-panel settings page with category navigation on the left and
   full form controls on the right.  Settings are persisted to
   localStorage and optionally synced to the backend.
   
   Exports: { render(container), mount(container), destroy() }
   Default export: factory for the SPA router.
   ========================================================================== */

import { html } from '../js/components/BaseComponent.js';
import { ICONS } from '../js/components/_icons.js';
import {
  skeletonCard,
  skeletonText,
  skeletonButton,
} from '../js/components/LoadingSkeleton.js';
import { loadTemplate } from '../js/template-loader.js';

/* ── Constants ──────────────────────────────────────────────────────────── */

const SETTINGS_KEY = 'fiona_settings';
const SETTINGS_VERSION = 2;

/** Default settings — built-in values used when nothing is stored. */
const DEFAULT_SETTINGS = {
  version: SETTINGS_VERSION,

  general: {
    theme: 'dark',
    language: 'en',
    startupBehavior: 'restore',
    sidebarDefaultOpen: true,
  },

  appearance: {
    accentColor: '#00f0ff',
    glassOpacity: 0.65,
    fontSize: 13,
    themeMode: 'dark',
    reducedMotion: false,
  },

  keyboard: {
    shortcuts: {
      'commandPalette': { key: 'k', ctrl: true, shift: false, alt: false, meta: true },
      'toggleSidebar':  { key: 'b', ctrl: true, shift: false, alt: false, meta: true },
      'openSettings':   { key: ',', ctrl: true, shift: false, alt: false, meta: true },
      'newChat':        { key: 'n', ctrl: true, shift: false, alt: false, meta: false },
      'focusTerminal':  { key: 't', ctrl: true, shift: false, alt: false, meta: false },
      'togglePanel':    { key: 'p', ctrl: true, shift: false, alt: false, meta: false },
      'saveFile':       { key: 's', ctrl: true, shift: false, alt: false, meta: false },
      'searchFiles':    { key: 'f', ctrl: true, shift: false, alt: false, meta: false },
    },
    _order: [
      'commandPalette', 'toggleSidebar', 'openSettings', 'newChat',
      'focusTerminal', 'togglePanel', 'saveFile', 'searchFiles',
    ],
  },

  notifications: {
    enabled: true,
    sound: true,
    types: {
      agentComplete:  true,
      taskFinished:   true,
      error:          true,
      updateAvailable: true,
      macroDone:      false,
      systemAlert:    true,
    },
  },

  privacy: {
    historyRetentionDays: 90,
    telemetry: false,
    crashReports: true,
    commandHistoryEnabled: true,
    logLevel: 'info',
  },

  agent: {
    defaultModel: 'gpt-4',
    temperature: 0.7,
    maxTokens: 4096,
    systemPrompt: 'You are Fiona, a helpful AI assistant integrated into the desktop.',
    streaming: true,
    contextWindow: 8192,
  },

  terminal: {
    shellPath: '/bin/zsh',
    fontSize: 13,
    scrollbackLines: 5000,
    fontFamily: 'JetBrains Mono',
    cursorStyle: 'block',
  },

  fileExplorer: {
    showHiddenFiles: false,
    defaultView: 'list',
    sortBy: 'name',
    sortAscending: true,
  },

  integrations: {
    ollamaUrl: 'http://localhost:11434',
    browserType: 'chromium',
    browserHeadless: true,
    gitEnabled: true,
    dockerEnabled: false,
  },

  /* ── ToolRuntime ──────────────────────────────────────────────────── */
  toolRuntime: {
    sandboxEnabled: true,
    executionTimeout: 30,
    maxParallelTools: 5,
    allowFileAccess: true,
    allowNetworkAccess: false,
    logExecution: true,
  },

  /* ── SciRetrieval ─────────────────────────────────────────────────── */
  sciRetrieval: {
    enabled: true,
    defaultProvider: 'auto',
    cacheEnabled: true,
    cacheTTL: 3600,
    maxResults: 10,
    enrichmentEnabled: true,
    apiTimeout: 15,
  },

  /* ── Plugins ──────────────────────────────────────────────────────── */
  plugins: {
    autoUpdate: true,
    allowThirdParty: false,
    pluginPath: '',
    developmentMode: false,
    strictMode: true,
  },

  /* ── Workspace ────────────────────────────────────────────────────── */
  workspace: {
    autoSave: true,
    autoSaveInterval: 60,
    defaultWorkspace: '',
    sessionRestore: true,
    maxRecentWorkspaces: 10,
  },

  /* ── Performance ──────────────────────────────────────────────────── */
  performance: {
    hardwareAcceleration: true,
    animationQuality: 'high',
    memoryLimit: 0,
    throttleCPU: false,
    throttlePercentage: 50,
    powerSaver: false,
  },

  /* ── Logging ──────────────────────────────────────────────────────── */
  logging: {
    level: 'info',
    maxFiles: 5,
    maxFileSize: 10485760,
    includeTimestamps: true,
    logToFile: true,
    logToConsole: true,
  },

  /* ── Key Bindings ─────────────────────────────────────────────────── */
  keyBindings: {
    enabled: true,
    globalShortcuts: true,
    showInMenu: true,
    conflictDetection: true,
  },

  /* ── PhiConnect ───────────────────────────────────────────────────── */
  phiConnect: {
    enabled: true,
    autoConnect: false,
    defaultTimeout: 30,
    encryptionEnabled: true,
    maxRetries: 3,
    heartbeatInterval: 15,
  },

  /* ── CamComs ──────────────────────────────────────────────────────── */
  camComs: {
    enabled: true,
    autoConnect: false,
    port: 0,
    encryptionEnabled: true,
    heartbeatInterval: 30,
    maxReconnectAttempts: 5,
    logLevel: 'info',
  },
};

/** Section definitions for the settings navigation. */
const SECTIONS = [
  { id: 'general',       label: 'General',            icon: 'gear' },
  { id: 'appearance',    label: 'Appearance',         icon: 'activity' },
  { id: 'keyboard',      label: 'Keyboard Shortcuts',  icon: 'keyboard' },
  { id: 'notifications', label: 'Notifications',       icon: 'bell' },
  { id: 'privacy',       label: 'Privacy',             icon: 'lock' },
  { id: 'terminal',      label: 'Terminal',            icon: 'terminal' },
  { id: 'agent',         label: 'Agent',               icon: 'bot' },
  { id: 'toolRuntime',   label: 'ToolRuntime',         icon: 'tool' },
  { id: 'sciRetrieval',  label: 'SciRetrieval',        icon: 'search' },
  { id: 'plugins',       label: 'Plugins',             icon: 'puzzle' },
  { id: 'workspace',     label: 'Workspace',           icon: 'folder' },
  { id: 'performance',   label: 'Performance',         icon: 'activity' },
  { id: 'logging',       label: 'Logging',             icon: 'fileText' },
  { id: 'keyBindings',   label: 'Key Bindings',        icon: 'keyboard' },
  { id: 'phiConnect',    label: 'PhiConnect',          icon: 'wifi' },
  { id: 'camComs',       label: 'CamComs',             icon: 'database' },
  { id: 'fileExplorer',  label: 'File Explorer',       icon: 'folder' },
  { id: 'integrations',  label: 'Integrations',        icon: 'globe' },
];

/**
 * Mapping of section IDs to available icon names.
 * Sections with duplicate icons use distinct icon keys.
 */
const SECTION_ICON_MAP = {
  general: 'gear',
  appearance: 'activity',
  keyboard: 'keyboard',
  notifications: 'bell',
  privacy: 'lock',
  terminal: 'terminal',
  agent: 'bot',
  toolRuntime: 'tool',
  sciRetrieval: 'search',
  plugins: 'puzzle',
  workspace: 'folderOpen',
  performance: 'trendingUp',
  logging: 'fileText',
  keyBindings: 'keyboard',
  phiConnect: 'wifi',
  camComs: 'database',
  fileExplorer: 'folder',
  integrations: 'globe',
};

/** Shortcut labels for the keyboard section. */
const SHORTCUT_LABELS = {
  commandPalette: 'Command Palette',
  toggleSidebar:  'Toggle Sidebar',
  openSettings:   'Open Settings',
  newChat:        'New Chat',
  focusTerminal:  'Focus Terminal',
  togglePanel:    'Toggle Right Panel',
  saveFile:       'Save File',
  searchFiles:    'Search Files',
};

/** Language options. */
const LANGUAGE_OPTIONS = [
  { value: 'en',  label: 'English' },
  { value: 'es',  label: 'Español' },
  { value: 'fr',  label: 'Français' },
  { value: 'de',  label: 'Deutsch' },
  { value: 'ja',  label: '日本語' },
  { value: 'zh',  label: '中文' },
];

/** Theme options. */
const THEME_OPTIONS = [
  { value: 'dark',  label: 'Dark' },
  { value: 'light', label: 'Light' },
  { value: 'system', label: 'System' },
];

/** Startup behavior options. */
const STARTUP_OPTIONS = [
  { value: 'restore', label: 'Restore previous session' },
  { value: 'dashboard', label: 'Open dashboard' },
  { value: 'chat', label: 'Open chat' },
  { value: 'blank', label: 'Blank page' },
];

/** File explorer view options. */
const VIEW_OPTIONS = [
  { value: 'list',  label: 'List' },
  { value: 'grid',  label: 'Grid' },
  { value: 'tree',  label: 'Tree' },
];

/** Browser type options. */
const BROWSER_OPTIONS = [
  { value: 'chromium',   label: 'Chromium' },
  { value: 'firefox',    label: 'Firefox' },
  { value: 'webkit',     label: 'WebKit' },
];

/** Retention options (days). */
const RETENTION_OPTIONS = [
  { value: 7,    label: '7 days' },
  { value: 30,   label: '30 days' },
  { value: 90,   label: '90 days' },
  { value: 180,  label: '180 days' },
  { value: 365,  label: '1 year' },
  { value: -1,   label: 'Forever' },
];

/** Log level options. */
const LOG_LEVEL_OPTIONS = [
  { value: 'debug',   label: 'Debug' },
  { value: 'info',    label: 'Info' },
  { value: 'warn',    label: 'Warning' },
  { value: 'error',   label: 'Error' },
];

const CURSOR_STYLE_OPTIONS = [
  { value: 'block',       label: 'Block' },
  { value: 'underline',   label: 'Underline' },
  { value: 'beam',        label: 'Beam' },
];

/* ── Module-level State ─────────────────────────────────────────────────── */

const _state = {
  container: null,
  settings: null,           // Deep clone of current settings
  originalSettings: null,   // Snapshot for unsaved detection
  activeSection: 'general',
  searchQuery: '',
  loading: true,
  destroyed: false,
  saveTimer: null,
  rebindingKey: null,       // id of shortcut currently being rebound
  showResetConfirm: false,
  showImportDialog: false,
  toastContainer: null,
  previewStyles: null,      // <style> element for instant preview
  /** Set of section IDs that have been modified since last save. */
  dirtySections: new Set(),
  /** Per-section save in progress flag. */
  savingSection: null,
};

/* ── Helpers ────────────────────────────────────────────────────────────── */

function getApi() {
  return window.fiona?.api;
}

function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

function esc(str) {
  if (!str) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return String(str).replace(/[&<>"']/g, (ch) => map[ch]);
}

function formatKey(key) {
  return key.charAt(0).toUpperCase() + key.slice(1);
}

function shortcutToLabel(shortcut) {
  const parts = [];
  if (shortcut.ctrl) parts.push('Ctrl');
  if (shortcut.meta) parts.push('⌘');
  if (shortcut.alt) parts.push('Alt');
  if (shortcut.shift) parts.push('Shift');
  parts.push(formatKey(shortcut.key));
  return parts.join(' + ');
}

/* ── Settings Persistence ───────────────────────────────────────────────── */

function _loadLocalSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return migrateSettings(parsed);
    }
  } catch (e) {
    console.warn('[settings] Failed to load settings from localStorage:', e);
  }
  return deepClone(DEFAULT_SETTINGS);
}

function saveSettings() {
  // Persist to localStorage
  try {
    const toStore = {
      ..._state.settings,
      version: SETTINGS_VERSION,
    };
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(toStore));
  } catch (e) {
    console.warn('[settings] Failed to save settings to localStorage:', e);
  }

  // Optional sync to backend
  const api = getApi();
  if (api) {
    api.put('/api/v1/settings', _state.settings).catch((err) => {
      console.warn('[settings] Server sync failed (non-fatal):', err);
    });
  }

  // Apply previews
  applyPreviews();
}

/**
 * Save a single section to the backend API and persist to localStorage.
 * Falls back to full localStorage save if the API is unavailable.
 */
async function saveSection(sectionId) {
  if (!_state.settings || !_state.settings[sectionId]) return;

  const api = getApi();
  if (api) {
    try {
      _state.savingSection = sectionId;
      renderSettingsPage(_state.container);
      await api.put(`/api/v1/settings/${sectionId}`, _state.settings[sectionId]);
    } catch (err) {
      console.warn(`[settings] Server save failed for section "${sectionId}" (non-fatal):`, err);
    } finally {
      _state.savingSection = null;
    }
  }

  // Persist to localStorage (full)
  try {
    const toStore = {
      ..._state.settings,
      version: SETTINGS_VERSION,
    };
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(toStore));
  } catch (e) {
    console.warn('[settings] Failed to save settings to localStorage:', e);
  }

  // Mark section as clean
  _state.dirtySections.delete(sectionId);
  applyPreviews();
  renderSettingsPage(_state.container);
}

function migrateSettings(settings) {
  const version = settings.version || 0;
  let migrated = { ...settings };

  if (version < 1) {
    // Migration v0 → v1: ensure all sections exist
    migrated = {
      ...deepClone(DEFAULT_SETTINGS),
      ...migrated,
      general:       { ...deepClone(DEFAULT_SETTINGS.general),       ...(migrated.general || {}) },
      appearance:    { ...deepClone(DEFAULT_SETTINGS.appearance),    ...(migrated.appearance || {}) },
      keyboard:      { ...deepClone(DEFAULT_SETTINGS.keyboard),      ...(migrated.keyboard || {}) },
      notifications: { ...deepClone(DEFAULT_SETTINGS.notifications), ...(migrated.notifications || {}) },
      privacy:       { ...deepClone(DEFAULT_SETTINGS.privacy),       ...(migrated.privacy || {}) },
      agent:         { ...deepClone(DEFAULT_SETTINGS.agent),         ...(migrated.agent || {}) },
      terminal:      { ...deepClone(DEFAULT_SETTINGS.terminal),      ...(migrated.terminal || {}) },
      fileExplorer:  { ...deepClone(DEFAULT_SETTINGS.fileExplorer),  ...(migrated.fileExplorer || {}) },
      integrations:  { ...deepClone(DEFAULT_SETTINGS.integrations),  ...(migrated.integrations || {}) },
      version: SETTINGS_VERSION,
    };
  }

  if (version < 2) {
    // Migration v1 → v2: add new sections with defaults merged
    const newSections = {
      toolRuntime:  deepClone(DEFAULT_SETTINGS.toolRuntime),
      sciRetrieval: deepClone(DEFAULT_SETTINGS.sciRetrieval),
      plugins:      deepClone(DEFAULT_SETTINGS.plugins),
      workspace:    deepClone(DEFAULT_SETTINGS.workspace),
      performance:  deepClone(DEFAULT_SETTINGS.performance),
      logging:      deepClone(DEFAULT_SETTINGS.logging),
      keyBindings:  deepClone(DEFAULT_SETTINGS.keyBindings),
      phiConnect:   deepClone(DEFAULT_SETTINGS.phiConnect),
      camComs:      deepClone(DEFAULT_SETTINGS.camComs),
    };
    for (const [key, defaults] of Object.entries(newSections)) {
      migrated[key] = { ...defaults, ...(migrated[key] || {}) };
    }
    migrated.version = SETTINGS_VERSION;
  }

  return migrated;
}

/* ── Preview Application ────────────────────────────────────────────────── */

function applyPreviews() {
  if (!_state.settings) return;

  const s = _state.settings;

  // Accent color — set CSS variable on root
  document.documentElement.style.setProperty('--accent', s.appearance.accentColor);
  document.documentElement.style.setProperty('--accent-hover', s.appearance.accentColor + 'cc');

  // Font size
  document.documentElement.style.setProperty('--font-size-base', s.appearance.fontSize + 'px');

  // Glass opacity
  const alpha = s.appearance.glassOpacity;
  document.documentElement.style.setProperty('--glass-bg', `rgba(30, 32, 43, ${alpha})`);

  // Theme mode
  document.documentElement.style.colorScheme = s.appearance.themeMode;
}

/* ── Unsaved Changes ────────────────────────────────────────────────────── */

function hasUnsavedChanges() {
  if (!_state.settings || !_state.originalSettings) return false;
  return JSON.stringify(_state.settings) !== JSON.stringify(_state.originalSettings);
}

function markSaved() {
  _state.originalSettings = deepClone(_state.settings);
}

function updateUnsavedIndicator() {
  const el = _state.container?.querySelector('#settings-unsaved');
  if (el) {
    const dirty = hasUnsavedChanges();
    el.style.display = dirty ? 'inline-flex' : 'none';
    const badge = el.querySelector('.settings-unsaved__count');
    if (badge) {
      badge.textContent = 'Unsaved changes';
    }
  }
}

/* ── Toast / Notification ───────────────────────────────────────────────── */

function showToast(type, message) {
  const toast = document.createElement('div');
  toast.className = `c-toast c-toast--${type || 'info'} animate-slide-right`;
  toast.style.cssText = 'position: fixed; bottom: 60px; right: 20px; z-index: 9999; max-width: 360px;';
  toast.innerHTML = `
    <div class="c-toast__icon">${ICONS[type === 'success' ? 'check' : type === 'error' ? 'error' : 'info']}</div>
    <div class="c-toast__content">
      <div class="c-toast__message">${esc(message)}</div>
    </div>
    <button class="c-toast__dismiss" data-toast-dismiss style="flex-shrink:0;">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
    </button>
  `;
  document.body.appendChild(toast);

  toast.querySelector('[data-toast-dismiss]')?.addEventListener('click', () => {
    toast.remove();
  });

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.2s';
    setTimeout(() => toast.remove(), 250);
  }, 3500);
}

/* ── Search / Filter ────────────────────────────────────────────────────── */

function filterSettingsByQuery(query) {
  if (!query) return SECTIONS;
  const q = query.toLowerCase();
  // Show sections that match directly or contain a matching setting
  return SECTIONS.filter((s) => {
    if (s.label.toLowerCase().includes(q)) return true;
    // Check setting values in section
    const sectionData = _state.settings?.[s.id];
    if (!sectionData || typeof sectionData !== 'object') return false;
    return Object.entries(sectionData).some(([key, val]) => {
      if (key === 'shortcuts' || key === '_order') return false;
      return key.toLowerCase().includes(q) ||
        String(val).toLowerCase().includes(q);
    });
  });
}

/* ── Export / Import ────────────────────────────────────────────────────── */

function exportSettingsJSON() {
  const blob = new Blob([JSON.stringify(_state.settings, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `fiona-settings-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function importSettingsJSON(file) {
  const reader = new FileReader();
  reader.onload = async (e) => {
    try {
      const parsed = JSON.parse(e.target.result);
      const migrated = migrateSettings(parsed);
      _state.settings = migrated;
      markSaved();
      saveSettings();
      await renderSettingsPage(_state.container);
      showToast('success', 'Settings imported successfully.');
    } catch (err) {
      showToast('error', `Failed to import settings: ${err.message}`);
    }
  };
  reader.readAsText(file);
}

/* ── HTML Renderers ─────────────────────────────────────────────────────── */

async function renderSettingsPage(container) {
  if (_state.destroyed) return;
  _state.container = container;

  if (_state.loading) {
    renderSkeletons(container);
    return;
  }

  const filteredSections = filterSettingsByQuery(_state.searchQuery);
  const activeSectionData = _state.settings?.[_state.activeSection];

  // Build nav content
  const navContent = renderSearchBar() + `
    <nav style="padding: var(--space-2) 0;">
      ${filteredSections.map((s) => {
        const isActive = s.id === _state.activeSection;
        const iconName = SECTION_ICON_MAP[s.id] || s.icon || 'gear';
        const iconSvg = ICONS[iconName] ? ICONS[iconName].html : ICONS.gear.html;
        return `
          <button class="settings-nav__item${isActive ? ' settings-nav__item--active' : ''}"
                  data-section="${s.id}" data-action="nav-section"
                  style="${isActive ? 'background: var(--accent-muted); color: var(--accent); font-weight: var(--font-weight-medium);' : ''}
                         border-right: 2px solid ${isActive ? 'var(--accent)' : 'transparent'};">
            <span class="settings-nav__icon">${iconSvg}</span>
            <span>${esc(s.label)}</span>
          </button>
        `;
      }).join('')}
    </nav>
    <div style="padding: var(--space-3) var(--space-4); border-top: 1px solid var(--border-subtle); margin-top: auto;">
      <div style="display: flex; gap: var(--space-2);">
        <button class="c-btn c-btn--sm c-btn--ghost" data-action="export-settings" title="Export settings JSON" style="flex:1;">
          <span class="c-btn__icon">${ICONS.download.html}</span>
          Export
        </button>
        <button class="c-btn c-btn--sm c-btn--ghost" data-action="import-settings" title="Import settings JSON" style="flex:1;">
          <span class="c-btn__icon">${ICONS.upload.html}</span>
          Import
        </button>
      </div>
    </div>
  `;

  // Build content HTML
  const sectionLabel = esc(SECTIONS.find(s => s.id === _state.activeSection)?.label || 'Settings');
  const sectionDesc = getSectionDescription(_state.activeSection);
  const formHtml = activeSectionData ? renderSectionControls(_state.activeSection, activeSectionData) : '<p style="color: var(--text-muted);">Select a category to view settings.</p>';

  const sectionDirty = _state.dirtySections.has(_state.activeSection);
  const sectionSaving = _state.savingSection === _state.activeSection;

  const contentHtml = `
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-6);">
      <div>
        <h2 style="font-size: var(--font-size-xl); font-weight: var(--font-weight-bold); color: var(--text-primary); margin: 0;">
          ${sectionLabel}
        </h2>
        <p style="font-size: var(--font-size-sm); color: var(--text-muted); margin: 2px 0 0 0;">
          ${sectionDesc}
        </p>
      </div>
      <div style="display: flex; align-items: center; gap: var(--space-3);">
        <span id="settings-unsaved" style="display: none; align-items: center; gap: var(--space-1); font-size: var(--font-size-xs); color: var(--warning);">
          <span style="width: 6px; height: 6px; border-radius: 50%; background: var(--warning);"></span>
          <span class="settings-unsaved__count">Unsaved changes</span>
        </span>
        <button class="c-btn c-btn--sm ${sectionDirty ? 'c-btn--primary' : 'c-btn--ghost'}"
                data-action="save-section"
                ${sectionSaving ? 'disabled' : ''}
                title="${sectionDirty ? 'Save this section to backend' : 'No changes'}">
          <span class="c-btn__icon">${ICONS.check.html}</span>
          ${sectionSaving ? 'Saving…' : 'Save'}
        </button>
        <button class="c-btn c-btn--sm c-btn--ghost" data-action="reset-section" title="Reset to defaults">
          <span class="c-btn__icon">${ICONS.refresh.html}</span>
          Reset
        </button>
      </div>
    </div>
    <div class="settings-form" style="max-width: 640px;">
      ${formHtml}
    </div>
  `;

  const data = {
    navContent,
    contentHtml,
  };

  container.innerHTML = await loadTemplate('settings', data);

  mountComponents(container);
}

function getSectionDescription(sectionId) {
  const descs = {
    general:       'Theme, language, and startup behavior preferences.',
    appearance:    'Visual customization: accent color, glass effect, font size, theme.',
    keyboard:      'Configure keyboard shortcuts. Click a shortcut to rebind it.',
    notifications: 'Control which events trigger notifications and sounds.',
    privacy:       'Manage data retention, telemetry, and crash reporting.',
    agent:         'Default AI model configuration, parameters, and system prompt.',
    terminal:      'Terminal emulator settings: shell, font, scrollback.',
    fileExplorer:  'File browsing preferences: hidden files, default view, sort order.',
    integrations:  'External service connections: Ollama, browser automation, etc.',
    toolRuntime:   'Tool execution sandbox, timeouts, and parallel execution limits.',
    sciRetrieval:  'Scientific literature retrieval providers, cache, and enrichment.',
    plugins:       'Plugin auto-update, third-party policy, and development mode.',
    workspace:     'Auto-save intervals, session restore, and recent workspaces.',
    performance:   'Hardware acceleration, animation quality, and CPU throttling.',
    logging:       'Log level, file rotation, and output destinations.',
    keyBindings:   'Global keyboard shortcut system and conflict detection.',
    phiConnect:    'PhiConnect peer-to-peer encrypted messaging configuration.',
    camComs:       'CamComs device communication and encryption settings.',
  };
  return descs[sectionId] || 'Configure Fiona settings.';
}

function renderSearchBar() {
  return html`
    <div style="padding: var(--space-3) var(--space-3); border-bottom: 1px solid var(--border-subtle);">
      <div class="c-input-wrapper">
        <span class="c-input-wrapper__icon c-input-wrapper__icon--left">${ICONS.search}</span>
        <input type="text" class="c-input c-input--sm" id="settings-search"
               placeholder="Search settings…"
               value="${esc(_state.searchQuery)}"
               style="padding-left: 32px; font-size: var(--font-size-xs);">
      </div>
    </div>
  `;
}

function renderSkeletons(container) {
  container.innerHTML = html`
    <div class="settings-skeleton" style="display: grid; grid-template-columns: 220px 1fr; height: 100%; gap: 0;">
      <div class="settings-skeleton__nav" style="padding: var(--space-3); border-right: 1px solid var(--border);">
        ${skeletonText({ width: '100%' })}
        ${html.raw(Array.from({ length: 8 }, () => skeletonText({ width: '80%' })).join(''))}
      </div>
      <div class="settings-skeleton__content" style="padding: var(--space-6);">
        ${skeletonCard({ height: '400px' })}
      </div>
    </div>
    <style>
      @media (max-width: 768px) {
        .settings-skeleton {
          grid-template-columns: 1fr !important;
        }
        .settings-skeleton__nav {
          display: none !important;
        }
        .settings-skeleton__content {
          padding: var(--space-4) !important;
        }
      }
    </style>
  `;
}

/* ── Section Control Renderers ──────────────────────────────────────────── */

function renderSectionControls(sectionId, data) {
  switch (sectionId) {
    case 'general':       return renderGeneralControls(data);
    case 'appearance':    return renderAppearanceControls(data);
    case 'keyboard':      return renderKeyboardControls(data);
    case 'notifications': return renderNotificationControls(data);
    case 'privacy':       return renderPrivacyControls(data);
    case 'agent':         return renderAgentControls(data);
    case 'terminal':      return renderTerminalControls(data);
    case 'fileExplorer':  return renderFileExplorerControls(data);
    case 'integrations':  return renderIntegrationControls(data);
    case 'toolRuntime':   return renderToolRuntimeControls(data);
    case 'sciRetrieval':  return renderSciRetrievalControls(data);
    case 'plugins':       return renderPluginsControls(data);
    case 'workspace':     return renderWorkspaceControls(data);
    case 'performance':   return renderPerformanceControls(data);
    case 'logging':       return renderLoggingControls(data);
    case 'keyBindings':   return renderKeyBindingsControls(data);
    case 'phiConnect':    return renderPhiConnectControls(data);
    case 'camComs':       return renderCamComsControls(data);
    default:              return html`<p style="color: var(--text-muted);">Unknown section.</p>`;
  }
}

function renderGeneralControls(data) {
  return html`
    ${toggleControl('general.themeMode', 'Dark Mode', 'Enable dark color scheme', data.themeMode === 'dark')}
    ${selectControl('general.theme', 'Theme', THEME_OPTIONS, data.theme)}
    ${selectControl('general.language', 'Language', LANGUAGE_OPTIONS, data.language)}
    ${selectControl('general.startupBehavior', 'Startup Behavior', STARTUP_OPTIONS, data.startupBehavior)}
    ${toggleControl('general.sidebarDefaultOpen', 'Sidebar Open by Default', 'Show sidebar on startup', data.sidebarDefaultOpen)}
  `;
}

function renderAppearanceControls(data) {
  return html`
    ${colorControl('appearance.accentColor', 'Accent Color', data.accentColor)}
    ${sliderControl('appearance.glassOpacity', 'Glass Opacity', data.glassOpacity, 0.2, 1, 0.05)}
    ${sliderControl('appearance.fontSize', 'Font Size (px)', data.fontSize, 10, 20, 1)}
    ${selectControl('appearance.themeMode', 'Theme Mode', THEME_OPTIONS, data.themeMode)}
    ${toggleControl('appearance.reducedMotion', 'Reduced Motion', 'Disable animations', data.reducedMotion)}
  `;
}

function renderKeyboardControls(data) {
  const order = data._order || Object.keys(data.shortcuts);
  return html`
    <div class="c-alert c-alert--info" style="margin-bottom: var(--space-4);">
      <span class="c-alert__icon">${ICONS.info}</span>
      <div class="c-alert__content">Click a shortcut to rebind it. Press Escape to cancel.</div>
    </div>
    <div style="display: flex; flex-direction: column; gap: 2px;">
      ${html.raw(order.map((id) => {
        const sc = data.shortcuts[id];
        if (!sc) return '';
        const label = SHORTCUT_LABELS[id] || formatKey(id);
        const isRebinding = _state.rebindingKey === id;
        return html`
          <div style="display: flex; align-items: center; justify-content: space-between; padding: var(--space-3) var(--space-4); background: var(--surface); border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
            <span style="font-size: var(--font-size-sm); color: var(--text-primary);">${esc(label)}</span>
            <div style="display: flex; align-items: center; gap: var(--space-2);">
              <kbd data-shortcut-id="${id}" data-action="rebind-shortcut"
                   style="cursor: pointer; min-width: 80px; justify-content: center;
                          ${isRebinding ? 'background: var(--accent-muted); color: var(--accent); border-color: var(--accent);' : ''}">
                ${isRebinding ? 'Press keys…' : esc(shortcutToLabel(sc))}
              </kbd>
              <button class="c-btn c-btn--sm c-btn--ghost" data-action="reset-shortcut" data-shortcut-id="${id}" title="Reset to default">
                <span class="c-btn__icon">${ICONS.refresh}</span>
              </button>
            </div>
          </div>
        `;
      }).join(''))}
    </div>
  `;
}

function renderNotificationControls(data) {
  const typeLabels = {
    agentComplete:   'Agent Task Complete',
    taskFinished:    'Task Finished',
    error:           'Errors',
    updateAvailable: 'Updates Available',
    macroDone:       'Macro Completed',
    systemAlert:     'System Alerts',
  };

  return html`
    ${toggleControl('notifications.enabled', 'Enable Notifications', 'Master switch for all notifications', data.enabled)}
    ${toggleControl('notifications.sound', 'Notification Sounds', 'Play sound on new notification', data.sound)}
    <div class="c-divider" style="margin: var(--space-4) 0;"></div>
    <p style="font-size: var(--font-size-sm); color: var(--text-secondary); margin-bottom: var(--space-3); font-weight: var(--font-weight-medium);">Notification Types</p>
    ${html.raw(Object.entries(data.types).map(([key, val]) => toggleControl(`notifications.types.${key}`, typeLabels[key] || formatKey(key), '', val)).join(''))}
  `;
}

function renderPrivacyControls(data) {
  return html`
    ${selectControl('privacy.historyRetentionDays', 'Command History Retention', RETENTION_OPTIONS, data.historyRetentionDays)}
    ${toggleControl('privacy.commandHistoryEnabled', 'Command History', 'Keep a record of executed commands', data.commandHistoryEnabled)}
    ${toggleControl('privacy.telemetry', 'Telemetry', 'Send anonymous usage data', data.telemetry)}
    ${toggleControl('privacy.crashReports', 'Crash Reports', 'Automatically send crash reports', data.crashReports)}
    ${selectControl('privacy.logLevel', 'Log Level', LOG_LEVEL_OPTIONS, data.logLevel)}
  `;
}

function renderAgentControls(data) {
  return html`
    ${textControl('agent.defaultModel', 'Default Model', data.defaultModel, 'e.g. gpt-4, claude-3-opus')}
    ${sliderControl('agent.temperature', 'Temperature', data.temperature, 0, 2, 0.1)}
    ${numberControl('agent.maxTokens', 'Max Output Tokens', data.maxTokens, 128, 32768)}
    ${numberControl('agent.contextWindow', 'Context Window', data.contextWindow, 2048, 128000)}
    ${toggleControl('agent.streaming', 'Streaming Responses', 'Tokens arrive as they are generated', data.streaming)}
    <div class="c-form-group" style="margin-bottom: var(--space-5);">
      <label class="c-form-group__label">System Prompt</label>
      <textarea class="c-textarea" data-setting="agent.systemPrompt"
                style="min-height: 100px; font-family: var(--font-mono); font-size: var(--font-size-xs);">${esc(data.systemPrompt)}</textarea>
      <p class="c-form-group__description">Instructions that define the agent's behavior and personality.</p>
    </div>
  `;
}

function renderTerminalControls(data) {
  return html`
    ${textControl('terminal.shellPath', 'Shell Path', data.shellPath, '/bin/zsh')}
    ${textControl('terminal.fontFamily', 'Font Family', data.fontFamily, 'JetBrains Mono')}
    ${sliderControl('terminal.fontSize', 'Font Size (px)', data.fontSize, 10, 24, 1)}
    ${numberControl('terminal.scrollbackLines', 'Scrollback Buffer', data.scrollbackLines, 500, 100000)}
    ${selectControl('terminal.cursorStyle', 'Cursor Style', CURSOR_STYLE_OPTIONS, data.cursorStyle)}
  `;
}

function renderFileExplorerControls(data) {
  return html`
    ${toggleControl('fileExplorer.showHiddenFiles', 'Show Hidden Files', 'Display files starting with a dot', data.showHiddenFiles)}
    ${selectControl('fileExplorer.defaultView', 'Default View', VIEW_OPTIONS, data.defaultView)}
    ${selectControl('fileExplorer.sortBy', 'Sort By', [
      { value: 'name', label: 'Name' },
      { value: 'size', label: 'Size' },
      { value: 'modified', label: 'Last Modified' },
      { value: 'type', label: 'Type' },
    ], data.sortBy)}
    ${toggleControl('fileExplorer.sortAscending', 'Sort Ascending', 'A→Z / small→large', data.sortAscending)}
  `;
}

function renderIntegrationControls(data) {
  return html`
    ${textControl('integrations.ollamaUrl', 'Ollama API URL', data.ollamaUrl, 'http://localhost:11434')}
    ${selectControl('integrations.browserType', 'Browser Type', BROWSER_OPTIONS, data.browserType)}
    ${toggleControl('integrations.browserHeadless', 'Headless Browser', 'Run browser without visible window', data.browserHeadless)}
    ${toggleControl('integrations.gitEnabled', 'Git Integration', 'Enable Git repository features', data.gitEnabled)}
    ${toggleControl('integrations.dockerEnabled', 'Docker Integration', 'Enable Docker container management', data.dockerEnabled)}
  `;
}

function renderToolRuntimeControls(data) {
  return html`
    ${toggleControl('toolRuntime.sandboxEnabled', 'Sandbox Mode', 'Run tools in isolated sandbox environment', data.sandboxEnabled)}
    ${numberControl('toolRuntime.executionTimeout', 'Execution Timeout (s)', data.executionTimeout, 1, 300)}
    ${numberControl('toolRuntime.maxParallelTools', 'Max Parallel Tools', data.maxParallelTools, 1, 50)}
    ${toggleControl('toolRuntime.allowFileAccess', 'File System Access', 'Allow tools to read/write files', data.allowFileAccess)}
    ${toggleControl('toolRuntime.allowNetworkAccess', 'Network Access', 'Allow tools to make network requests', data.allowNetworkAccess)}
    ${toggleControl('toolRuntime.logExecution', 'Log Execution', 'Record tool execution details to logs', data.logExecution)}
  `;
}

function renderSciRetrievalControls(data) {
  return html`
    ${toggleControl('sciRetrieval.enabled', 'Enable SciRetrieval', 'Master switch for scientific literature retrieval', data.enabled)}
    ${textControl('sciRetrieval.defaultProvider', 'Default Provider', data.defaultProvider, 'auto, arxiv, pubmed, crossref')}
    ${toggleControl('sciRetrieval.cacheEnabled', 'Enable Cache', 'Cache search results to reduce API calls', data.cacheEnabled)}
    ${numberControl('sciRetrieval.cacheTTL', 'Cache TTL (seconds)', data.cacheTTL, 60, 86400)}
    ${numberControl('sciRetrieval.maxResults', 'Max Results', data.maxResults, 1, 100)}
    ${toggleControl('sciRetrieval.enrichmentEnabled', 'Enrichment', 'Auto-enrich agent context with relevant literature', data.enrichmentEnabled)}
    ${numberControl('sciRetrieval.apiTimeout', 'API Timeout (s)', data.apiTimeout, 5, 120)}
  `;
}

function renderPluginsControls(data) {
  return html`
    ${toggleControl('plugins.autoUpdate', 'Auto-Update', 'Automatically check for and apply plugin updates', data.autoUpdate)}
    ${toggleControl('plugins.allowThirdParty', 'Allow Third-Party', 'Enable installation of third-party plugins', data.allowThirdParty)}
    ${textControl('plugins.pluginPath', 'Plugin Path', data.pluginPath, 'Custom plugin directory')}
    ${toggleControl('plugins.developmentMode', 'Development Mode', 'Enable plugin development features and hot-reload', data.developmentMode)}
    ${toggleControl('plugins.strictMode', 'Strict Mode', 'Enforce strict security policies on all plugins', data.strictMode)}
  `;
}

function renderWorkspaceControls(data) {
  return html`
    ${toggleControl('workspace.autoSave', 'Auto-Save', 'Automatically save workspace state at intervals', data.autoSave)}
    ${numberControl('workspace.autoSaveInterval', 'Auto-Save Interval (s)', data.autoSaveInterval, 10, 600)}
    ${textControl('workspace.defaultWorkspace', 'Default Workspace', data.defaultWorkspace, 'Path to default workspace')}
    ${toggleControl('workspace.sessionRestore', 'Session Restore', 'Restore last workspace on startup', data.sessionRestore)}
    ${numberControl('workspace.maxRecentWorkspaces', 'Max Recent Workspaces', data.maxRecentWorkspaces, 1, 50)}
  `;
}

function renderPerformanceControls(data) {
  return html`
    ${toggleControl('performance.hardwareAcceleration', 'Hardware Acceleration', 'Use GPU for rendering and computation', data.hardwareAcceleration)}
    ${selectControl('performance.animationQuality', 'Animation Quality', [
      { value: 'low', label: 'Low' },
      { value: 'medium', label: 'Medium' },
      { value: 'high', label: 'High' },
    ], data.animationQuality)}
    ${numberControl('performance.memoryLimit', 'Memory Limit (MB, 0 = unlimited)', data.memoryLimit, 0, 65536)}
    ${toggleControl('performance.throttleCPU', 'Throttle CPU', 'Limit CPU usage during background tasks', data.throttleCPU)}
    ${sliderControl('performance.throttlePercentage', 'Throttle Percentage', data.throttlePercentage, 10, 100, 5)}
    ${toggleControl('performance.powerSaver', 'Power Saver', 'Reduce resource usage on battery power', data.powerSaver)}
  `;
}

function renderLoggingControls(data) {
  return html`
    ${selectControl('logging.level', 'Log Level', [
      { value: 'debug', label: 'Debug' },
      { value: 'info', label: 'Info' },
      { value: 'warn', label: 'Warning' },
      { value: 'error', label: 'Error' },
    ], data.level)}
    ${numberControl('logging.maxFiles', 'Max Log Files', data.maxFiles, 1, 50)}
    ${numberControl('logging.maxFileSize', 'Max File Size (bytes)', data.maxFileSize, 102400, 104857600)}
    ${toggleControl('logging.includeTimestamps', 'Include Timestamps', 'Prepend timestamps to log entries', data.includeTimestamps)}
    ${toggleControl('logging.logToFile', 'Log to File', 'Write logs to rotating file on disk', data.logToFile)}
    ${toggleControl('logging.logToConsole', 'Log to Console', 'Output logs to terminal console', data.logToConsole)}
  `;
}

function renderKeyBindingsControls(data) {
  return html`
    <div class="c-alert c-alert--info" style="margin-bottom: var(--space-4);">
      <span class="c-alert__icon">${ICONS.info}</span>
      <div class="c-alert__content">Global key binding system for application launchers and shortcuts.</div>
    </div>
    ${toggleControl('keyBindings.enabled', 'Enable Key Bindings', 'Master switch for the key binding system', data.enabled)}
    ${toggleControl('keyBindings.globalShortcuts', 'Global Shortcuts', 'Allow shortcuts to work when Fiona is in background', data.globalShortcuts)}
    ${toggleControl('keyBindings.showInMenu', 'Show in Menu', 'Display available key bindings in the menu bar', data.showInMenu)}
    ${toggleControl('keyBindings.conflictDetection', 'Conflict Detection', 'Warn when two bindings use the same key combination', data.conflictDetection)}
  `;
}

function renderPhiConnectControls(data) {
  return html`
    <div class="c-alert c-alert--info" style="margin-bottom: var(--space-4);">
      <span class="c-alert__icon">${ICONS.info}</span>
      <div class="c-alert__content">Configure PhiConnect encrypted peer-to-peer messaging.</div>
    </div>
    ${toggleControl('phiConnect.enabled', 'Enable PhiConnect', 'Master switch for PhiConnect service', data.enabled)}
    ${toggleControl('phiConnect.autoConnect', 'Auto-Connect', 'Automatically connect to known peers on startup', data.autoConnect)}
    ${numberControl('phiConnect.defaultTimeout', 'Default Timeout (s)', data.defaultTimeout, 5, 300)}
    ${toggleControl('phiConnect.encryptionEnabled', 'End-to-End Encryption', 'Encrypt all messages between peers', data.encryptionEnabled)}
    ${numberControl('phiConnect.maxRetries', 'Max Retries', data.maxRetries, 0, 20)}
    ${numberControl('phiConnect.heartbeatInterval', 'Heartbeat Interval (s)', data.heartbeatInterval, 5, 120)}
  `;
}

function renderCamComsControls(data) {
  return html`
    <div class="c-alert c-alert--info" style="margin-bottom: var(--space-4);">
      <span class="c-alert__icon">${ICONS.info}</span>
      <div class="c-alert__content">Configure CamComs device communication settings.</div>
    </div>
    ${toggleControl('camComs.enabled', 'Enable CamComs', 'Master switch for CamComs device communication', data.enabled)}
    ${toggleControl('camComs.autoConnect', 'Auto-Connect', 'Automatically connect to paired devices', data.autoConnect)}
    ${numberControl('camComs.port', 'Port (0 = auto)', data.port, 0, 65535)}
    ${toggleControl('camComs.encryptionEnabled', 'Encryption', 'Encrypt device communication channels', data.encryptionEnabled)}
    ${numberControl('camComs.heartbeatInterval', 'Heartbeat Interval (s)', data.heartbeatInterval, 5, 120)}
    ${numberControl('camComs.maxReconnectAttempts', 'Max Reconnect Attempts', data.maxReconnectAttempts, 0, 50)}
    ${selectControl('camComs.logLevel', 'Log Level', [
      { value: 'debug', label: 'Debug' },
      { value: 'info', label: 'Info' },
      { value: 'warn', label: 'Warning' },
      { value: 'error', label: 'Error' },
    ], data.logLevel)}
  `;
}

/* ── Form Control Primitives ────────────────────────────────────────────── */

function toggleControl(settingPath, label, description, value) {
  const checked = value === true || value === 'true';
  return html`
    <div class="c-form-group c-form-group--horizontal" style="margin-bottom: var(--space-4); justify-content: space-between;">
      <div>
        <label class="c-form-group__label">${esc(label)}</label>
        ${description ? html`<p class="c-form-group__description">${esc(description)}</p>` : ''}
      </div>
      <label class="c-toggle" style="flex-shrink: 0;">
        <input type="checkbox" class="c-toggle__input" data-setting="${esc(settingPath)}"
               ${checked ? 'checked' : ''}>
        <span class="c-toggle__track"><span class="c-toggle__thumb"></span></span>
      </label>
    </div>
  `;
}

function sliderControl(settingPath, label, value, min, max, step) {
  const pct = ((value - min) / (max - min)) * 100;
  return html`
    <div class="c-form-group" style="margin-bottom: var(--space-5);">
      <div style="display: flex; align-items: center; justify-content: space-between;">
        <label class="c-form-group__label">${esc(label)}</label>
        <span style="font-size: var(--font-size-sm); color: var(--text-secondary); font-variant-numeric: tabular-nums; min-width: 40px; text-align: right;" id="slider-val-${esc(settingPath.replace(/\./g, '-'))}">
          ${typeof value === 'number' && step < 1 ? value.toFixed(2) : value}
        </span>
      </div>
      <input type="range" class="c-slider" data-setting="${esc(settingPath)}"
             value="${value}" min="${min}" max="${max}" step="${step}"
             style="width: 100%; accent-color: var(--accent);">
      <div style="display: flex; justify-content: space-between; font-size: var(--font-size-xxs); color: var(--text-muted);">
        <span>${min}</span>
        <span>${max}</span>
      </div>
    </div>
  `;
}

function selectControl(settingPath, label, options, value) {
  return html`
    <div class="c-form-group" style="margin-bottom: var(--space-5);">
      <label class="c-form-group__label">${esc(label)}</label>
      <select class="c-select" data-setting="${esc(settingPath)}" style="max-width: 300px;">
        ${html.raw(options.map((opt) => html`
          <option value="${esc(String(opt.value))}" ${String(opt.value) === String(value) ? 'selected' : ''}>
            ${esc(opt.label)}
          </option>
        `).join(''))}
      </select>
    </div>
  `;
}

function colorControl(settingPath, label, value) {
  return html`
    <div class="c-form-group c-form-group--horizontal" style="margin-bottom: var(--space-5);">
      <label class="c-form-group__label">${esc(label)}</label>
      <div style="display: flex; align-items: center; gap: var(--space-2);">
        <input type="color" class="c-color-picker" data-setting="${esc(settingPath)}"
               value="${esc(value)}"
               style="width: 36px; height: 36px; border: 1px solid var(--border); border-radius: var(--radius-md); background: none; cursor: pointer; padding: 2px;">
        <input type="text" class="c-input c-input--sm" data-setting-text="${esc(settingPath)}"
               value="${esc(value)}" style="width: 100px; font-family: var(--font-mono); font-size: var(--font-size-xs);">
      </div>
    </div>
  `;
}

function textControl(settingPath, label, value, placeholder) {
  return html`
    <div class="c-form-group" style="margin-bottom: var(--space-5);">
      <label class="c-form-group__label">${esc(label)}</label>
      <input type="text" class="c-input" data-setting="${esc(settingPath)}"
             value="${esc(value)}" placeholder="${esc(placeholder || '')}"
             style="max-width: 400px;">
    </div>
  `;
}

function numberControl(settingPath, label, value, min, max) {
  return html`
    <div class="c-form-group" style="margin-bottom: var(--space-5);">
      <label class="c-form-group__label">${esc(label)}</label>
      <input type="number" class="c-input" data-setting="${esc(settingPath)}"
             value="${value}" min="${min}" max="${max}"
             style="max-width: 160px; font-variant-numeric: tabular-nums;">
    </div>
  `;
}

/* ── Component Mounting ─────────────────────────────────────────────────── */

function mountComponents(container) {
  if (_state.destroyed) return;
  _state.container = container;

  // ── Search ──
  const searchInput = container.querySelector('#settings-search');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      _state.searchQuery = e.target.value;
      renderSettingsPage(container);
    });
    // Focus search on Ctrl+F or slash
    setTimeout(() => searchInput.focus(), 100);
  }

  // ── Navigation sections ──
  container.querySelectorAll('[data-action="nav-section"]').forEach((btn) => {
    btn.addEventListener('click', () => {
      _state.activeSection = btn.dataset.section;
      _state.rebindingKey = null;
      renderSettingsPage(container);
    });
  });

  // ── Form control changes ──
  bindFormControls(container);

  // ── Save section ──
  container.querySelector('[data-action="save-section"]')?.addEventListener('click', () => {
    saveSection(_state.activeSection);
  });

  // ── Reset section ──
  container.querySelector('[data-action="reset-section"]')?.addEventListener('click', () => {
    showResetDialog();
  });

  // ── Export ──
  container.querySelector('[data-action="export-settings"]')?.addEventListener('click', exportSettingsJSON);

  // ── Import ──
  container.querySelector('[data-action="import-settings"]')?.addEventListener('click', () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.addEventListener('change', (e) => {
      if (e.target.files[0]) importSettingsJSON(e.target.files[0]);
    });
    input.click();
  });

  // ── Keyboard shortcut rebinding ──
  container.querySelectorAll('[data-action="rebind-shortcut"]').forEach((el) => {
    el.addEventListener('click', () => {
      const id = el.dataset.shortcutId;
      if (!id) return;
      if (_state.rebindingKey === id) {
        _state.rebindingKey = null;
        renderSettingsPage(container);
        return;
      }
      _state.rebindingKey = id;
      renderSettingsPage(container);
      // Listen for keydown
      const handler = (e) => {
        e.preventDefault();
        if (e.key === 'Escape') {
          _state.rebindingKey = null;
          renderSettingsPage(container);
          document.removeEventListener('keydown', handler);
          return;
        }
        // Only record modifier + key combos
        if (e.key === 'Control' || e.key === 'Shift' || e.key === 'Alt' || e.key === 'Meta') return;
        if (!e.ctrlKey && !e.metaKey && !e.altKey) {
          // Single key is valid too for some shortcuts
        }
        const newShortcut = {
          key: e.key.toLowerCase(),
          ctrl: e.ctrlKey || false,
          shift: e.shiftKey || false,
          alt: e.altKey || false,
          meta: e.metaKey || false,
        };
        if (!_state.settings.keyboard.shortcuts[id]) {
          _state.settings.keyboard.shortcuts[id] = {};
        }
        _state.settings.keyboard.shortcuts[id] = newShortcut;
        _state.rebindingKey = null;
        markUnsaved();
        renderSettingsPage(container);
        document.removeEventListener('keydown', handler);
      };
      // Debounce to avoid capturing the click's keyup
      setTimeout(() => document.addEventListener('keydown', handler), 50);
    });
  });

  // ── Reset shortcut to default ──
  container.querySelectorAll('[data-action="reset-shortcut"]').forEach((el) => {
    el.addEventListener('click', () => {
      const id = el.dataset.shortcutId;
      if (!id) return;
      const def = DEFAULT_SETTINGS.keyboard.shortcuts[id];
      if (def) {
        if (!_state.settings.keyboard.shortcuts[id]) {
          _state.settings.keyboard.shortcuts[id] = {};
        }
        _state.settings.keyboard.shortcuts[id] = { ...def };
        markUnsaved();
        renderSettingsPage(container);
      }
    });
  });

  updateUnsavedIndicator();
}

function bindFormControls(container) {
  // Toggles
  container.querySelectorAll('[data-setting].c-toggle__input').forEach((el) => {
    el.addEventListener('change', (e) => {
      const path = e.target.dataset.setting;
      setSettingByPath(path, e.target.checked);
    });
  });

  // Sliders
  container.querySelectorAll('input[type="range"][data-setting]').forEach((el) => {
    const displayId = `slider-val-${el.dataset.setting.replace(/\./g, '-')}`;
    el.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value);
      const display = container.querySelector(`#${displayId}`);
      if (display) {
        display.textContent = parseFloat(e.target.step) < 1 ? val.toFixed(2) : val;
      }
      setSettingByPath(e.target.dataset.setting, val);
    });
  });

  // Selects
  container.querySelectorAll('select[data-setting]').forEach((el) => {
    el.addEventListener('change', (e) => {
      const val = e.target.value;
      // Try to preserve number type
      const num = parseFloat(val);
      setSettingByPath(e.target.dataset.setting, isNaN(num) ? val : num);
    });
  });

  // Color pickers
  container.querySelectorAll('input[type="color"][data-setting]').forEach((el) => {
    el.addEventListener('input', (e) => {
      const val = e.target.value;
      // Sync text input
      const textInput = container.querySelector(`[data-setting-text="${e.target.dataset.setting}"]`);
      if (textInput) textInput.value = val;
      setSettingByPath(e.target.dataset.setting, val);
    });
  });

  // Color text inputs
  container.querySelectorAll('[data-setting-text]').forEach((el) => {
    el.addEventListener('input', (e) => {
      const val = e.target.value;
      // Sync color picker
      const colorInput = container.querySelector(`[data-setting="${e.target.dataset.settingText}"]`);
      if (colorInput && /^#[0-9a-f]{6}$/i.test(val)) {
        colorInput.value = val;
      }
      if (/^#[0-9a-f]{6}$/i.test(val)) {
        setSettingByPath(e.target.dataset.settingText, val);
      }
    });
  });

  // Text inputs
  container.querySelectorAll('input[type="text"][data-setting]:not([data-setting-text])').forEach((el) => {
    el.addEventListener('change', (e) => {
      setSettingByPath(e.target.dataset.setting, e.target.value);
    });
    // Auto-save on blur
    el.addEventListener('blur', (e) => {
      setSettingByPath(e.target.dataset.setting, e.target.value);
    });
  });

  // Number inputs
  container.querySelectorAll('input[type="number"][data-setting]').forEach((el) => {
    el.addEventListener('change', (e) => {
      const val = parseFloat(e.target.value);
      if (!isNaN(val)) setSettingByPath(e.target.dataset.setting, val);
    });
    el.addEventListener('blur', (e) => {
      const val = parseFloat(e.target.value);
      if (!isNaN(val)) setSettingByPath(e.target.dataset.setting, val);
    });
  });

  // Textareas
  container.querySelectorAll('textarea[data-setting]').forEach((el) => {
    el.addEventListener('change', (e) => {
      setSettingByPath(e.target.dataset.setting, e.target.value);
    });
    el.addEventListener('blur', (e) => {
      setSettingByPath(e.target.dataset.setting, e.target.value);
    });
  });
}

/* ── Settings Mutation ──────────────────────────────────────────────────── */

function setSettingByPath(path, value) {
  if (!_state.settings) return;
  const parts = path.split('.');
  let obj = _state.settings;
  for (let i = 0; i < parts.length - 1; i++) {
    if (!obj[parts[i]]) obj[parts[i]] = {};
    obj = obj[parts[i]];
  }
  obj[parts[parts.length - 1]] = value;

  markUnsaved();
}

function markUnsaved() {
  // Track the current section as dirty
  if (_state.activeSection) {
    _state.dirtySections.add(_state.activeSection);
  }
  updateUnsavedIndicator();

  // Debounced auto-save (full settings)
  if (_state.saveTimer) clearTimeout(_state.saveTimer);
  _state.saveTimer = setTimeout(() => {
    saveSettings();
    markSaved();
    _state.dirtySections.clear();
    updateUnsavedIndicator();
  }, 800);
}

/* ── Reset Dialog ───────────────────────────────────────────────────────── */

function showResetDialog() {
  const modalContainer = document.getElementById('modal-container');
  if (!modalContainer) return;

  modalContainer.innerHTML = `
    <div class="c-modal-backdrop" id="settings-reset-backdrop">
      <div class="c-modal c-modal--sm">
        <div class="c-modal__header">
          <h3 class="c-modal__title">Reset Section</h3>
          <button class="c-modal__close" data-action="close-modal">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="c-modal__body">
          <p style="color: var(--text-secondary); font-size: var(--font-size-sm);">
            Reset <strong>${esc(SECTIONS.find(s => s.id === _state.activeSection)?.label || 'this section')}</strong> settings to their defaults?
          </p>
          <p style="color: var(--text-muted); font-size: var(--font-size-xs); margin-top: var(--space-2);">
            This action cannot be undone.
          </p>
        </div>
        <div class="c-modal__footer">
          <button class="c-btn" data-action="cancel-reset">Cancel</button>
          <button class="c-btn c-btn--danger" data-action="confirm-reset">Reset to Defaults</button>
        </div>
      </div>
    </div>
  `;

  modalContainer.style.display = 'flex';

  const close = () => {
    modalContainer.innerHTML = '';
    modalContainer.style.display = 'none';
  };

  modalContainer.querySelector('[data-action="close-modal"]')?.addEventListener('click', close);
  modalContainer.querySelector('[data-action="cancel-reset"]')?.addEventListener('click', close);
  modalContainer.querySelector('#settings-reset-backdrop')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) close();
  });
  modalContainer.querySelector('[data-action="confirm-reset"]')?.addEventListener('click', () => {
    if (_state.settings && _state.activeSection) {
      _state.settings[_state.activeSection] = deepClone(DEFAULT_SETTINGS[_state.activeSection]);
      // Save to backend and localStorage, then re-render
      saveSection(_state.activeSection).then(() => {
        if (_state.container) renderSettingsPage(_state.container);
        showToast('success', 'Section reset to defaults.');
      });
    }
    close();
  });
}

/* ── Data Loading ───────────────────────────────────────────────────────── */

async function loadSettings() {
  if (_state.destroyed) return;

  _state.settings = _loadLocalSettings();
  _state.originalSettings = deepClone(_state.settings);
  _state.loading = false;

  // Attempt to load from server (overrides local if successful)
  const api = getApi();
  if (api) {
    try {
      const result = await api.get('/api/v1/settings');
      if (result && typeof result === 'object') {
        const serverSettings = result.data || result;
        // Merge server settings on top of local
        _state.settings = migrateSettings({
          ..._state.settings,
          ...serverSettings,
        });
        _state.originalSettings = deepClone(_state.settings);
        saveSettings();
      }
    } catch (err) {
      // Server not available — try per-section loading
      console.log('[settings] Server settings unavailable, trying per-section…');
      await loadAllSectionsFromServer();
    }
  }

  if (!_state.destroyed && _state.container) {
    await renderSettingsPage(_state.container);
  }
}

/**
 * Attempt to load each section from the per-section API endpoints.
 * Merges successful responses on top of existing local settings.
 */
async function loadAllSectionsFromServer() {
  const api = getApi();
  if (!api) return;

  const sectionIds = SECTIONS.map(s => s.id);
  let anyLoaded = false;

  for (const sectionId of sectionIds) {
    try {
      const result = await api.get(`/api/v1/settings/${sectionId}`);
      if (result && typeof result === 'object') {
        const sectionData = result.data || result;
        if (sectionData && typeof sectionData === 'object' && Object.keys(sectionData).length > 0) {
          _state.settings[sectionId] = {
            ...deepClone(DEFAULT_SETTINGS[sectionId] || {}),
            ..._state.settings[sectionId],
            ...sectionData,
          };
          anyLoaded = true;
        }
      }
    } catch (err) {
      // Per-section endpoint not available — skip
    }
  }

  if (anyLoaded) {
    _state.originalSettings = deepClone(_state.settings);
    saveSettings();
  }
}

/* ── Lifecycle ──────────────────────────────────────────────────────────── */

export function render() {
  return '<div id="settings-root"></div>';
}

export async function mount(container) {
  _state.destroyed = false;
  _state.loading = true;
  _state.container = container;

  renderSkeletons(container);
  await loadSettings();
}

export function destroy() {
  _state.destroyed = true;
  if (_state.saveTimer) {
    clearTimeout(_state.saveTimer);
    _state.saveTimer = null;
  }
  _state.rebindingKey = null;
  _state.container = null;
  _state.settings = null;
  _state.originalSettings = null;
  _state.dirtySections.clear();
  _state.savingSection = null;

  // Remove preview styles
  if (_state.previewStyles) {
    _state.previewStyles.remove();
    _state.previewStyles = null;
  }
}

/* ── Router-compatible default export ───────────────────────────────────── */

export default function createPage(_routeInfo) {
  return {
    render,
    async mount(container) {
      const root = container.querySelector('#settings-root') || container;
      _state.destroyed = false;
      _state.loading = true;
      _state.container = root;

      renderSkeletons(root);
      await loadSettings();
    },
    destroy,
  };
}
