/* ==========================================================================
   app.js — Main Application Bootstrap
   ==========================================================================
   Entry point for the Fiona web frontend.  Initializes the state store,
   router, API client, and all global UI subsystems (keyboard shortcuts,
   sidebar, status bar, command palette, notifications, modals).
   
   Loaded by index.html via <script type="module" src="js/app.js"></script>.
   ========================================================================== */

import { createStore } from './state.js';
import { createRouter } from './router.js';
import { createApi } from './api.js';

/* ── Initial State ──────────────────────────────────────────────────────── */

/**
 * Default application state with all required slices.
 * Each slice maps to a functional domain of the application.
 */
const initialState = {
  /** Application-level settings and metadata */
  app: {
    version: '0.1.0',
    theme: 'dark',
    sidebarCollapsed: false,
    rightPanelOpen: false,
    commandPaletteOpen: false,
    modalOpen: false,
    currentModal: null,
    isOnline: navigator.onLine,
    startTime: Date.now(),
  },

  /** Chat state for the AI agent */
  chat: {
    sessions: [],
    activeSessionId: null,
    messages: [],
    streamToken: null,
    isResponding: false,
    personalities: [],
    activePersonality: null,
  },

  /** Agent configuration and status */
  agents: {
    list: [],
    activeAgentId: null,
    agentStatus: {},
  },

  /** System metrics and health */
  system: {
    status: 'disconnected', // 'disconnected' | 'connecting' | 'connected' | 'error'
    metrics: {
      cpu: 0,
      memory: 0,
      disk: 0,
      uptime: 0,
    },
    serverInfo: null,
    capabilities: [],
    reconnectAttempts: 0,
  },

  /** User and application settings */
  settings: {
    general: {},
    security: {},
    voice: {},
    macros: {},
    shellSafety: {},
    about: {},
    isDirty: {},
  },

  /** Workspace / project state */
  workspace: {
    currentPath: null,
    recentFiles: [],
    openFiles: [],
    activeFileId: null,
  },

  /** Notification center */
  notifications: {
    items: [],
    unreadCount: 0,
    toasts: [],
  },

  /** Terminal sessions */
  terminal: {
    sessions: {},
    activeSessionId: null,
  },

  /** Browser / web views */
  browser: {
    tabs: [],
    activeTabId: null,
    history: [],
  },

  /** File system browser */
  files: {
    currentDir: null,
    items: [],
    selectedPath: null,
    clipboard: null,
  },

  /** Background tasks and progress */
  tasks: {
    queue: [],
    active: null,
    history: [],
  },

  /** Plugin registry state */
  plugins: {
    loaded: [],
    available: [],
    settings: {},
  },
};

/* ── Route Definitions ──────────────────────────────────────────────────── */

const routes = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('../pages/dashboard.js'),
    title: 'Dashboard',
    icon: 'dashboard',
  },
  {
    path: '/chat',
    name: 'chat',
    component: () => import('../pages/chat.js'),
    title: 'AI Chat',
    icon: 'message',
  },
  {
    path: '/agents',
    name: 'agents',
    component: () => import('../pages/agents.js'),
    title: 'Agents',
    icon: 'bot',
  },
  {
    path: '/agents/:id',
    name: 'agent-detail',
    component: () => import('../pages/agent-status.js'),
    title: 'Agent Detail',
    icon: 'bot',
  },
  {
    path: '/actions',
    name: 'actions',
    component: () => import('../pages/actions.js'),
    title: 'Actions',
    icon: 'bolt',
  },
  {
    path: '/bindings',
    name: 'bindings',
    component: () => import('../pages/bindings.js'),
    title: 'Key Bindings',
    icon: 'keyboard',
  },
  {
    path: '/phiconnect',
    name: 'phiconnect',
    component: () => import('../pages/phiconnect.js'),
    title: 'PhiConnect',
    icon: 'lock',
  },
  {
    path: '/macros',
    name: 'macros',
    component: () => import('../pages/macros.js'),
    title: 'Macros',
    icon: 'play',
  },
  {
    path: '/terminal',
    name: 'terminal',
    component: () => import('../pages/terminal.js'),
    title: 'Terminal',
    icon: 'terminal',
  },
  {
    path: '/notifications',
    name: 'notifications',
    component: () => import('../pages/notifications.js'),
    title: 'Notifications',
    icon: 'bell',
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../pages/settings.js'),
    title: 'Settings',
    icon: 'gear',
  },
  {
    path: '/performance',
    name: 'performance',
    component: () => import('../pages/performance.js'),
    title: 'Performance',
    icon: 'activity',
  },
  {
    path: '/files',
    name: 'files',
    component: () => import('../pages/file-explorer.js'),
    title: 'Files',
    icon: 'folder',
  },
  {
    path: '/browser',
    name: 'browser',
    component: () => import('../pages/browser.js'),
    title: 'Browser',
    icon: 'globe',
  },
  {
    path: '/tasks',
    name: 'tasks',
    component: () => import('../pages/tasks.js'),
    title: 'Tasks',
    icon: 'check-circle',
  },
  {
    path: '/plugins',
    name: 'plugins',
    component: () => import('../pages/plugins.js'),
    title: 'Plugins',
    icon: 'puzzle',
  },
  {
    path: '/logs',
    name: 'logs',
    component: () => import('../pages/logs.js'),
    title: 'Logs',
    icon: 'activity',
  },
  {
    path: '/config',
    name: 'config',
    component: () => import('../pages/config.js'),
    title: 'Configuration',
    icon: 'gear',
  },
  {
    path: '/diagnostics',
    name: 'diagnostics',
    component: () => import('../pages/diagnostics.js'),
    title: 'Diagnostics',
    icon: 'activity',
  },
  {
    path: '/devtools',
    name: 'devtools',
    component: () => import('../pages/devtools.js'),
    title: 'Developer Tools',
    icon: 'terminal',
  },
  {
    path: '/calendar',
    name: 'calendar',
    component: () => import('../pages/calendar.js'),
    title: 'Calendar',
    icon: 'calendar',
  },
  {
    path: '/workspace',
    name: 'workspace',
    component: () => import('../pages/workspace.js'),
    title: 'Workspace',
    icon: 'folder',
  },
  {
    path: '/camcoms',
    name: 'camcoms',
    component: () => import('../pages/camcoms.js'),
    title: 'CamComs',
    icon: 'wifi',
  },
  {
    path: '/recall',
    name: 'recall',
    component: () => import('../pages/recall.js'),
    title: 'RecallVault',
    icon: 'search',
  },
  {
    path: '/desktop',
    name: 'desktop',
    component: () => import('../pages/desktop.js'),
    title: 'SeeOnDesk',
    icon: 'maximize',
  },
  {
    path: '/voice',
    name: 'voice',
    component: () => import('../pages/voice.js'),
    title: 'Voice Commands',
    icon: 'message',
  },
];

/* ── Sidebar Navigation Sections ──────────────────────────────────────────── */



/* ── Global App Object ──────────────────────────────────────────────────── */

/**
 * @namespace FionaApp
 */
const app = {
  /** @type {import('./state.js').Store} */
  store: null,
  /** @type {import('./router.js').Router} */
  router: null,
  /** @type {import('./api.js').ApiClient} */
  api: null,

  /** @type {Object} Store references to initialized subsystems */
  subsystems: {},

  /** @type {boolean} Whether the app has been booted */
  initialized: false,
};

/* ── Initialization ─────────────────────────────────────────────────────── */

/**
 * Bootstrap the application.
 * Called once when the module loads.
 */
async function init() {
  if (app.initialized) return;

  console.log('[fiona] Initializing Fiona frontend v0.1.0');

  try {
    // ── 1. Create Store ──
    console.log('[fiona] Initializing state store');
    app.store = createStore(initialState, { logger: true });

    // Persist UI state and settings to localStorage
    app.store.persist('app');
    app.store.persist('settings');

    // Start with the sidebar expanded on every boot.
    // This intentionally overrides any previous persisted collapse state.
    app.store.set('app.sidebarCollapsed', false);

    // ── 2. Create API Client ──
    console.log('[fiona] Initializing API client');
    app.api = createApi({
      baseURL: 'http://localhost:8765',
      timeout: 30000,
      onError: (error) => {
        console.error('[fiona] API error:', error);
        app.store.set('system.status', 'error');
        _addToast({
          type: 'error',
          message: error.message || 'A network error occurred.',
        });
      },
    });

    // ── 3. Set up API request interceptor for auth/headers ──
    app.api.onRequest((config) => {
      // Could attach tokens or additional headers here
      return config;
    });

    // ── 4. Set up API response interceptor for connection tracking ──
    app.api.onResponse((response) => {
      if (response.ok) {
        app.store.set('system.status', 'connected', { silent: true });
      }
      return response;
    });

    // ── 5. Create Router ──
    console.log('[fiona] Initializing router');
    const container = document.getElementById('page-content');
    app.router = createRouter({
      routes,
      container: container || '#page-content',
      scrollToTop: true,
      beforeEach: (to, from) => {
        // Global navigation guard — can redirect or cancel
        return true;
      },
      onError: (error, route) => {
        console.error(`[fiona] Route error on ${route?.path}:`, error);
        _addToast({
          type: 'error',
          message: `Failed to load ${route?.title || 'page'}: ${error.message}`,
          duration: 5000,
        });
      },
    });

    // ── 6. Initialize Global UI Systems ──
    console.log('[fiona] Initializing UI systems');
    _initGlobalShortcuts();
    _initSidebar();
    _initStatusBar();
    _initCommandPalette();
    _initNotificationSystem();
    _initModalSystem();
    _initResizeHandler();
    _initBeforeUnload();
    _initClock();
    _initConnectionIndicator();
    _initHeaderActions();

    // ── 7. Register service worker (placeholder) ──
    _registerServiceWorker();

    // ── 8. Start the router ──
    app.router.init();

    // ── 9. Connect to backend WebSocket ──
    _connectWebSocket();

    // ── 10. Expose app globally for debugging ──
    window.__fiona = app;
    window.fiona = app;

    app.initialized = true;
    console.log('[fiona] Fiona frontend initialized successfully');
  } catch (err) {
    console.error('[fiona] Failed to initialize:', err);
    _showFatalError(err);
  }
}

/* ── Keyboard Shortcuts ─────────────────────────────────────────────────── */

/**
 * Register global keyboard shortcuts.
 * @private
 */
function _initGlobalShortcuts() {
  document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + K — Command palette
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      _toggleCommandPalette();
      return;
    }

    // Ctrl/Cmd + B — Toggle sidebar
    if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
      e.preventDefault();
      _toggleSidebar();
      return;
    }

    // Escape — Close modals, command palette, panels
    if (e.key === 'Escape') {
      const appState = app.store.get('app');
      if (appState.commandPaletteOpen) {
        _toggleCommandPalette();
        return;
      }
      if (appState.modalOpen) {
        _closeModal();
        return;
      }
      if (appState.rightPanelOpen) {
        _toggleRightPanel();
        return;
      }
    }

    // Ctrl/Cmd + , — Open settings
    if ((e.ctrlKey || e.metaKey) && e.key === ',') {
      e.preventDefault();
      app.router.navigate('/settings');
      return;
    }

    // Alt + N — Notifications
    if (e.altKey && e.key === 'n') {
      e.preventDefault();
      app.router.navigate('/notifications');
      return;
    }

    // Ctrl/Cmd + Shift + Z — Redo
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'z') {
      e.preventDefault();
      app.store.redo();
      return;
    }

    // Ctrl/Cmd + Z — Undo (when not in input)
    if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !_isInInput(e.target)) {
      e.preventDefault();
      app.store.undo();
      return;
    }
  });
}

/**
 * Check if the event target is a text input element.
 * @param {Element} target
 * @returns {boolean}
 */
function _isInInput(target) {
  const tag = target?.tagName?.toLowerCase();
  return tag === 'input' || tag === 'textarea' || target?.isContentEditable;
}

/* ── Sidebar ────────────────────────────────────────────────────────────── */

/**
 * Set up sidebar navigation, section collapse, collapse-state sync,
 * and active-highlighting on route change.
 * @private
 */
function _initSidebar() {
  const sidebarEl = document.getElementById('sidebar');
  if (!sidebarEl) return;

  // ── Logo click → Dashboard ──
  const logo = sidebarEl.querySelector('.sidebar__logo');
  if (logo) {
    logo.style.cursor = 'pointer';
    logo.addEventListener('click', (e) => {
      e.stopPropagation();
      if (app.router) app.router.navigate('/');
    });
  }

  // ── Section collapse toggle only (nav <a> links work natively) ──
  sidebarEl.addEventListener('click', (e) => {
    const sectionTitle = e.target.closest('[data-action="toggle-section"]');
    if (!sectionTitle) return;
    e.preventDefault();
    const section = sectionTitle.closest('.sidebar__nav-section');
    if (!section) return;
    const content = section.querySelector('.sidebar__nav-section-content');
    const chevron = sectionTitle.querySelector('.chevron');
    if (content) {
      const isCollapsed = content.classList.toggle('sidebar__nav-section-content--collapsed');
      if (chevron) chevron.classList.toggle('chevron--collapsed', isCollapsed);
      sectionTitle.setAttribute('aria-expanded', !isCollapsed);
    }
  });

  // ── Route changes → update active nav highlight ─────────────────
  if (app.router) {
    app.router.onChange((route) => {
      if (!route) return;
      const path = route.path || '/';
      document.querySelectorAll('#sidebar .nav-item').forEach((el) => {
        const itemPath = el.getAttribute('data-nav-path');
        if (!itemPath) return;
        const isActive = path === itemPath || (itemPath !== '/' && path.startsWith(itemPath));
        el.classList.toggle('nav-item--active', isActive);
      });
    });
  }
}

/**
 * Toggle the right panel.
 * @private
 */
function _toggleRightPanel() {
  const current = app.store.get('app.rightPanelOpen');
  app.store.set('app.rightPanelOpen', !current);
  const panel = document.getElementById('right-panel');
  if (panel) {
    panel.classList.toggle('right-panel--hidden', current);
  }
}

/* ── Status Bar ─────────────────────────────────────────────────────────── */

/**
 * Set up status bar updates (clock, connection status, notifications).
 * @private
 */
function _initStatusBar() {
  // Update status message on store changes
  app.store.subscribe('system.status', (status) => {
    const statusMsg = document.getElementById('status-message');
    if (statusMsg) {
      const messages = {
        disconnected: 'Disconnected',
        connecting: 'Connecting…',
        connected: 'Connected',
        error: 'Connection Error',
      };
      statusMsg.textContent = messages[status] || status;
    }
  });
}

/* ── Clock ──────────────────────────────────────────────────────────────── */

/**
 * Update the clock in the status bar every minute.
 * @private
 */
function _initClock() {
  const clockEl = document.getElementById('status-clock');
  if (!clockEl) return;

  function updateClock() {
    const now = new Date();
    const hours = now.getHours();
    const minutes = now.getMinutes().toString().padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours % 12 || 12;
    clockEl.textContent = `${displayHours}:${minutes} ${ampm}`;
  }

  updateClock();
  setInterval(updateClock, 30000); // Update every 30 seconds
}

/* ── Connection Indicator ───────────────────────────────────────────────── */

/**
 * Set up the connection indicator in the header and status bar.
 * @private
 */
function _initConnectionIndicator() {
  const indicator = document.getElementById('connection-indicator');
  const statusLabel = document.getElementById('status-connection');

  app.store.subscribe('system.status', (status) => {
    // Update header indicator
    if (indicator) {
      indicator.className = `connection-indicator connection-indicator--${status}`;
      const label = indicator.querySelector('.connection-indicator__label');
      if (label) {
        const labels = {
          disconnected: 'Disconnected',
          connecting: 'Connecting…',
          connected: 'Connected',
          error: 'Error',
        };
        label.textContent = labels[status] || status;
      }
    }

    // Update status bar
    if (statusLabel) {
      const labels = {
        disconnected: 'Disconnected',
        connecting: 'Connecting…',
        connected: 'Connected',
        error: 'Error',
      };
      statusLabel.textContent = labels[status] || status;
    }
  });
}

/* ── Command Palette ────────────────────────────────────────────────────── */

/**
 * Initialize the command palette subsystem.
 * @private
 */
function _initCommandPalette() {
  const paletteContainer = document.getElementById('command-palette-container');

  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      _toggleCommandPalette();
    }
  });

  // Close on backdrop click
  if (paletteContainer) {
    paletteContainer.addEventListener('click', (e) => {
      if (e.target === paletteContainer) {
        _toggleCommandPalette();
      }
    });

    // Close on Escape (handled by global shortcuts, but also here)
    paletteContainer.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        _toggleCommandPalette();
      }
    });
  }

  // Sync with store
  app.store.subscribe('app.commandPaletteOpen', (isOpen) => {
    if (paletteContainer) {
      paletteContainer.classList.toggle('command-palette--open', isOpen);
      paletteContainer.style.display = isOpen ? 'flex' : 'none';
    }
  });
}

/**
 * Toggle the command palette open/closed.
 * @private
 */
function _toggleCommandPalette() {
  const current = app.store.get('app.commandPaletteOpen');
  app.store.set('app.commandPaletteOpen', !current);
}

/* ── Notification System ────────────────────────────────────────────────── */

/**
 * Initialize the notification / toast display system.
 * @private
 */
function _initNotificationSystem() {
  const toastContainer = document.getElementById('toast-container');
  if (!toastContainer) return;

  // Listen for new toasts
  app.store.subscribe('notifications.toasts', (toasts) => {
    // Render active toasts
    const toastHtml = toasts.map((t) => `
      <div class="c-toast c-toast--${t.type || 'info'}" data-toast-id="${t.id}">
        <div class="c-toast__icon">${_getToastIcon(t.type)}</div>
        <div class="c-toast__content">
          <div class="c-toast__message">${_escapeHtml(t.message)}</div>
          ${t.details ? `<div class="c-toast__details">${_escapeHtml(t.details)}</div>` : ''}
        </div>
        <button class="c-toast__dismiss" data-toast-dismiss="${t.id}" aria-label="Dismiss">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    `).join('');

    toastContainer.innerHTML = toastHtml;

    // Set up dismiss handlers
    toastContainer.querySelectorAll('[data-toast-dismiss]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.dataset.toastDismiss;
        _removeToast(id);
      });
    });
  });

  // Update notification badge
  app.store.subscribe('notifications.unreadCount', (count) => {
    const badge = document.getElementById('status-notification-count');
    if (badge) {
      badge.textContent = String(count);
    }
  });
}

/**
 * Add a toast notification.
 * @param {Object} toast
 * @param {string} toast.type - 'info' | 'success' | 'warning' | 'error'
 * @param {string} toast.message
 * @param {string} [toast.details]
 * @param {number} [toast.duration=4000]
 * @private
 */
function _addToast(toast) {
  const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  const newToast = { ...toast, id };
  const toasts = app.store.get('notifications.toasts');
  app.store.set('notifications.toasts', [...toasts, newToast]);

  // Auto-dismiss after duration
  const duration = toast.duration || 4000;
  setTimeout(() => _removeToast(id), duration);
}

/**
 * Remove a toast by id.
 * @param {string} id
 * @private
 */
function _removeToast(id) {
  const toasts = app.store.get('notifications.toasts');
  app.store.set('notifications.toasts', toasts.filter((t) => t.id !== id));
}

/**
 * Add a notification item to the store's notification list.
 * Deduplicates by id (replaces existing if same id).
 * @param {Object} params - Notification data
 * @private
 */
function _addNotificationToStore(params) {
  if (!params || !params.title) return;

  const items = app.store.get('notifications.items');
  const existingIdx = params.id ? items.findIndex((n) => n.id === params.id) : -1;

  let newItems;
  if (existingIdx >= 0) {
    // Replace existing
    newItems = [...items];
    newItems[existingIdx] = { ...newItems[existingIdx], ...params };
  } else {
    // Prepend new notification
    newItems = [params, ...items];
  }

  app.store.set('notifications.items', newItems);
  app.store.set('notifications.unreadCount', app.store.get('notifications.unreadCount') + 1);
}

/**
 * Update an existing notification in the store (e.g. mark as read).
 * @param {Object} params - Partial update with id
 * @private
 */
function _updateNotificationInStore(params) {
  if (!params || !params.id) return;

  const items = app.store.get('notifications.items');
  const idx = items.findIndex((n) => n.id === params.id);
  if (idx === -1) return;

  const updated = [...items];
  updated[idx] = { ...updated[idx], ...params };
  app.store.set('notifications.items', updated);
}

/**
 * Get an SVG icon for a toast type.
 * @param {string} type
 * @returns {string}
 * @private
 */
function _getToastIcon(type) {
  const icons = {
    info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    warning: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    error: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
  };
  return icons[type] || icons.info;
}

/* ── Modal System ───────────────────────────────────────────────────────── */

/**
 * Initialize the modal display system.
 * @private
 */
function _initModalSystem() {
  const modalContainer = document.getElementById('modal-container');
  if (!modalContainer) return;

  // Close modal on backdrop click
  modalContainer.addEventListener('click', (e) => {
    if (e.target === modalContainer) {
      _closeModal();
    }
  });

  app.store.subscribe('app.modalOpen', (isOpen) => {
    if (modalContainer) {
      modalContainer.classList.toggle('modal--open', isOpen);
      modalContainer.style.display = isOpen ? 'flex' : 'none';
    }

    // Prevent body scroll when modal is open
    document.body.style.overflow = isOpen ? 'hidden' : '';
  });
}

/**
 * Open a modal with content.
 * @param {Object} modalConfig
 * @param {string} modalConfig.title
 * @param {string} modalConfig.body - HTML for the modal body
 * @param {string} [modalConfig.size] - 'sm' | 'md' | 'lg' | 'xl'
 * @param {Array<Object>} [modalConfig.actions] - Footer action buttons
 * @private
 */
function _openModal(modalConfig) {
  const modalContainer = document.getElementById('modal-container');
  if (!modalContainer) return;

  const actionsHtml = (modalConfig.actions || [])
    .map((action) => `
      <button class="c-btn c-btn--${action.variant || 'primary'}"
              data-modal-action="${action.id || ''}">
        ${action.label}
      </button>
    `).join('');

  modalContainer.innerHTML = `
    <div class="c-modal c-modal--${modalConfig.size || 'md'}">
      <div class="c-modal__header">
        <h3 class="c-modal__title">${_escapeHtml(modalConfig.title)}</h3>
        <button class="c-modal__close" data-action="close-modal" aria-label="Close">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
      <div class="c-modal__body">${modalConfig.body}</div>
      ${actionsHtml ? `<div class="c-modal__footer">${actionsHtml}</div>` : ''}
    </div>
  `;

  // Set up close handlers
  modalContainer.querySelector('[data-action="close-modal"]')?.addEventListener('click', _closeModal);

  // Set up action handlers
  modalContainer.querySelectorAll('[data-modal-action]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const actionId = btn.dataset.modalAction;
      if (modalConfig.onAction) modalConfig.onAction(actionId);
    });
  });

  app.store.set('app.modalOpen', true);
  app.store.set('app.currentModal', modalConfig);
}

/**
 * Close the currently open modal.
 * @private
 */
function _closeModal() {
  app.store.set('app.modalOpen', false);
  app.store.set('app.currentModal', null);
  const modalContainer = document.getElementById('modal-container');
  if (modalContainer) {
    modalContainer.innerHTML = '';
  }
  document.body.style.overflow = '';
}

/* ── Header Actions ─────────────────────────────────────────────────────── */

/**
 * Bind clicks on header action buttons.
 * @private
 */
function _initHeaderActions() {
  // Settings button
  const settingsBtn = document.getElementById('header-settings-btn');
  settingsBtn?.addEventListener('click', () => {
    app.router.navigate('/settings');
  });

  // Notifications button
  const notifBtn = document.getElementById('header-notifications-btn');
  notifBtn?.addEventListener('click', () => {
    app.router.navigate('/notifications');
  });

  // Search / command palette trigger
  const searchTrigger = document.getElementById('search-trigger');
  searchTrigger?.addEventListener('click', _toggleCommandPalette);

  // Global data-action dispatcher
  document.addEventListener('click', (e) => {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;
    const action = actionEl.dataset.action;
    switch (action) {
      case 'open-settings':
        app.router.navigate('/settings');
        break;
      case 'open-notifications':
        app.router.navigate('/notifications');
        break;
      case 'open-command-palette':
        _toggleCommandPalette();
        break;
      case 'close-panel':
        _toggleRightPanel();
        break;
      case 'open-help':
        // TODO: Implement help system
        _addToast({ type: 'info', message: 'Help system coming soon' });
        break;
      case 'navigate-home':
        app.router.navigate('/');
        break;
      case 'close-modal':
        _closeModal();
        break;
      default:
        // Allow custom actions to be handled elsewhere
        break;
    }
  });
}

/* ── Resize Handler ─────────────────────────────────────────────────────── */

/**
 * Handle window resize events for responsive layout adjustments.
 * @private
 */
function _initResizeHandler() {
  let resizeTimeout;

  window.addEventListener('resize', () => {
    // Debounce resize handler
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
      const width = window.innerWidth;
      const height = window.innerHeight;

      // Dispatch a custom event for components to listen to
      window.dispatchEvent(new CustomEvent('fiona:resize', {
        detail: { width, height },
      }));
    }, 150);
  });
}

/* ── Before Unload ──────────────────────────────────────────────────────── */

/**
 * Warn the user before closing if there are unsaved changes.
 * @private
 */
function _initBeforeUnload() {
  window.addEventListener('beforeunload', (e) => {
    const isDirty = app.store.get('settings.isDirty');
    const hasDirty = Object.values(isDirty).some((v) => v === true);
    if (hasDirty) {
      e.preventDefault();
      e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
    }
  });
}

/* ── WebSocket Connection ───────────────────────────────────────────────── */

/**
 * Connect to the backend WebSocket for real-time updates.
 * @private
 */
function _connectWebSocket() {
  const baseURL = app.api._getBaseURL();
  const wsURL = baseURL.replace(/^http/, 'ws') + '/ws';

  app.store.set('system.status', 'connecting');

  try {
    const conn = app.api.connect(wsURL, {
      autoReconnect: true,
    });

    conn.on('open', () => {
      console.log('[fiona] WebSocket connected');
      app.store.set('system.status', 'connected');
      app.store.set('system.reconnectAttempts', 0);

      // Send handshake
      app.api.send('handshake', {
        client_name: 'fiona-localpages',
        client_version: '0.1.0',
        protocol_version: '1.0',
        capabilities: ['full_state', 'incremental_updates'],
      }, 1);
    });

    conn.on('close', () => {
      console.log('[fiona] WebSocket disconnected');
      app.store.set('system.status', 'disconnected');
    });

    conn.on('reconnecting', ({ attempt, delay }) => {
      console.log(`[fiona] WebSocket reconnecting (attempt ${attempt}) in ${delay}ms`);
      app.store.set('system.status', 'connecting');
      app.store.set('system.reconnectAttempts', attempt);
    });

    conn.on('error', (err) => {
      console.error('[fiona] WebSocket error:', err);
      app.store.set('system.status', 'error');
    });

    // Listen for JSON-RPC notifications
    app.api.on('connection.ready', (params) => {
      console.log('[fiona] Server ready:', params);
      app.store.set('system.serverInfo', params);
      app.store.set('system.status', 'connected');
    });

    app.api.on('system.notification', (params) => {
      // Add to notification center (JSON-RPC method format)
      _addNotificationToStore(params);
    });

    // Listen for event-format messages from the server's WebSocketManager.notify()
    conn.on('message', (msg) => {
      if (!msg || !msg.event || !msg.params) return;

      switch (msg.event) {
        case 'notification':
          // New notification from ws_manager.notify("notification", ...)
          _addNotificationToStore(msg.params);
          break;

        case 'notification.update':
          // Update an existing notification in the store
          _updateNotificationInStore(msg.params);
          break;

        case 'agent.notification':
          // Agent-related notification with agent identity
          _addNotificationToStore({
            ...msg.params,
            category: msg.params.category || 'Agent',
            agent_id: msg.params.agent_id || msg.params.agentId || null,
          });
          break;

        default:
          break;
      }
    });

  } catch (err) {
    console.error('[fiona] Failed to connect WebSocket:', err);
    app.store.set('system.status', 'error');
  }
}

/* ── Service Worker ─────────────────────────────────────────────────────── */

/**
 * Register the service worker for offline support (placeholder).
 * @private
 */
async function _registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    try {
      // Registration is commented out until sw.js is implemented
      // const registration = await navigator.serviceWorker.register('/sw.js');
      // console.log('[fiona] ServiceWorker registered:', registration.scope);
      console.log('[fiona] ServiceWorker registration ready (not yet active)');
    } catch (err) {
      console.warn('[fiona] ServiceWorker registration failed:', err);
    }
  }
}

/* ── Fatal Error ────────────────────────────────────────────────────────── */

/**
 * Display a fatal initialization error in the UI.
 * @param {Error} err
 * @private
 */
function _showFatalError(err) {
  const container = document.getElementById('page-content');
  if (container) {
    container.innerHTML = `
      <div class="empty-state" style="margin-top: 20vh;">
        <div class="empty-state__icon" style="color: var(--danger);">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="1.5" stroke-linecap="round"
               stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </div>
        <div class="empty-state__title">Failed to Start</div>
        <div class="empty-state__description" style="color: var(--danger);">
          ${_escapeHtml(err.message || 'An unexpected error occurred during initialization.')}
        </div>
        <pre style="margin-top: var(--space-4); max-width: 600px; text-align: left; font-size: var(--font-size-xs);">${_escapeHtml(err.stack || '')}</pre>
        <button class="c-btn c-btn--primary" style="margin-top: var(--space-6);" onclick="location.reload()">
          Reload
        </button>
      </div>
    `;
  }
}

/* ── Utility: Escape HTML ───────────────────────────────────────────────── */

/**
 * Escape HTML special characters.
 * @param {string} str
 * @returns {string}
 * @private
 */
function _escapeHtml(str) {
  if (!str) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return String(str).replace(/[&<>"']/g, (ch) => map[ch]);
}

/* ── Boot ───────────────────────────────────────────────────────────────── */

// Self-executing initialization when the DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

/* ── Export ─────────────────────────────────────────────────────────────── */

export { app };
export default app;
