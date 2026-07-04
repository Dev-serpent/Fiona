/* ==========================================================================
   Sidebar.js — Collapsible Navigation Sidebar
   ==========================================================================
   Collapsible sidebar with logo/brand area, grouped navigation sections
   (Favorites, Pages, Tools, System), nav items with icons, badges, and
   active-state highlighting.  Supports Cmd+B toggle and emits `navigate`
   events.

   Import:
     import { Sidebar } from './Sidebar.js';

     const sidebar = new Sidebar({
       container: '#sidebar',
       store,
       router,
       navSections: [
         {
           id: 'pages',
           label: 'Pages',
           items: [
             { id: 'dashboard', label: 'Dashboard', icon: 'dashboard', path: '/' },
           ],
         },
       ],
     });
     sidebar.attach();
   ========================================================================== */

import { BaseComponent, html, escapeSelector } from './BaseComponent.js';
import { ICONS } from './_icons.js';

/* ── CSS class name constants ──────────────────────────────────────────── */

const CSS = {
  sidebar: 'sidebar',
  header: 'sidebar__header',
  logo: 'sidebar__logo',
  logoIcon: 'sidebar__logo-icon',
  nav: 'sidebar__nav',
  navSection: 'sidebar__nav-section',
  sectionTitle: 'sidebar__nav-section-title',
  sectionContent: 'sidebar__nav-section-content',
  sectionCollapsed: 'sidebar__nav-section-content--collapsed',
  chevron: 'chevron',
  chevronCollapsed: 'chevron--collapsed',
  navItem: 'nav-item',
  navItemActive: 'nav-item--active',
  itemIcon: 'nav-item__icon',
  itemLabel: 'nav-item__label',
  itemBadge: 'nav-item__badge',
  footer: 'sidebar__footer',
  footerVersion: 'sidebar__footer-version',
  footerActions: 'sidebar__footer-actions',
  footerBtn: 'sidebar__footer-btn',
};

/**
 * Default navigation sections used when none are provided in props.
 * @type {Array<SectionDef>}
 */
const DEFAULT_SECTIONS = [
  {
    id: 'favorites',
    label: 'Favorites',
    collapsible: true,
    defaultCollapsed: false,
    items: [],
  },
  {
    id: 'pages',
    label: 'Pages',
    collapsible: true,
    defaultCollapsed: false,
    items: [
      { id: 'dashboard', label: 'Dashboard', icon: 'dashboard', path: '/' },
      { id: 'chat', label: 'AI Chat', icon: 'message', path: '/chat' },
      { id: 'agents', label: 'Agents', icon: 'bot', path: '/agents' },
      { id: 'actions', label: 'Actions', icon: 'bolt', path: '/actions' },
      { id: 'recall', label: 'RecallVault', icon: 'search', path: '/recall' },
      { id: 'bindings', label: 'Key Bindings', icon: 'keyboard', path: '/bindings' },
      { id: 'terminal', label: 'Terminal', icon: 'terminal', path: '/terminal' },
      { id: 'files', label: 'Files', icon: 'folder', path: '/files' },
      { id: 'browser', label: 'Browser', icon: 'globe', path: '/browser' },
    ],
  },
  {
    id: 'tools',
    label: 'Tools',
    collapsible: true,
    defaultCollapsed: true,
    items: [
      { id: 'apicatalog', label: 'API Catalog', icon: 'globe', path: '/apicatalog' },
      { id: 'macros', label: 'Macros', icon: 'play', path: '/macros' },
      { id: 'camcoms', label: 'CamComs', icon: 'wifi', path: '/camcoms' },
      { id: 'desktop', label: 'SeeOnDesk', icon: 'maximize', path: '/desktop' },
      { id: 'voice', label: 'Voice', icon: 'message', path: '/voice' },
      { id: 'phiconnect', label: 'PhiConnect', icon: 'lock', path: '/phiconnect' },
    ],
  },
  {
    id: 'system',
    label: 'System',
    collapsible: true,
    defaultCollapsed: true,
    items: [
      { id: 'tasks', label: 'Tasks', icon: 'check-circle', path: '/tasks' },
      { id: 'notifications', label: 'Notifications', icon: 'bell', path: '/notifications' },
      { id: 'plugins', label: 'Plugins', icon: 'puzzle', path: '/plugins' },
    ],
  },
];

/**
 * @typedef {Object} NavItem
 * @property {string} id - Unique identifier
 * @property {string} label - Display label
 * @property {string} icon - Icon name (key into ICONS map)
 * @property {string} [path] - Route path for navigation
 * @property {number} [badge] - Optional badge count
 * @property {Function} [onClick] - Custom click handler
 */

/**
 * @typedef {Object} SectionDef
 * @property {string} id - Section identifier
 * @property {string} label - Section header label
 * @property {boolean} [collapsible=true] - Whether section can be collapsed
 * @property {boolean} [defaultCollapsed=false] - Initial collapsed state
 * @property {NavItem[]} items - Navigation items in this section
 */

export class Sidebar extends BaseComponent {
  /**
   * @param {Object} options
   * @param {string|Element} options.container - Mount container
   * @param {Object} options.store - Global state store
   * @param {Object} options.router - Router instance for isActive()
   * @param {Object} [options.props]
   * @param {SectionDef[]} [options.props.navSections] - Custom nav sections
   * @param {string} [options.props.brandLabel='Fiona'] - Brand text
   * @param {string} [options.props.version='0.1.0'] - Version string
   * @param {NavItem[]} [options.props.bottomItems] - Footer nav items
   */
  constructor(options = {}) {
    super(options);
    this._router = options.router || null;

    // Initialise collapsed sections state
    const sections = this._props.navSections || DEFAULT_SECTIONS;
    const sectionCollapse = {};
    for (const sec of sections) {
      if (sec.collapsible) {
        sectionCollapse[sec.id] = sec.defaultCollapsed === true;
      }
    }

    this._state = {
      sections: sectionCollapse,
      activePath: this._router ? this._router.getCurrentRoute()?.path || '/' : '/',
    };

    // Bottom items default
    this._bottomItems = this._props.bottomItems || [
      { id: 'settings', label: 'Settings', icon: 'gear', path: '/settings' },
      { id: 'help', label: 'Help', icon: 'help', onClick: () => this.emit('help') },
    ];
  }

  /**
   * Bind store subscription and keyboard shortcut on mount.
   */
  mount() {
    // Listen for route changes to update active state
    if (this._router) {
      this._unsubRoute = this._router.onChange((route) => {
        this.setState({ activePath: route?.path || '/' });
      });
    }

    // Keyboard shortcut: Cmd+B / Ctrl+B is handled by app.js
    // _initGlobalShortcuts() — we don't bind a second listener here.

    this.on('click', '[data-action="toggle-section"]', (e, el) => {
      const sectionId = el.dataset.sectionId;
      if (sectionId) {
        this._toggleSection(sectionId);
      }
    });

    this.on('click', '[data-nav-path]', (e, el) => {
      e.preventDefault();
      const path = el.dataset.navPath;
      const itemId = el.dataset.navId;
      if (path && this._router) {
        this._router.navigate(path);
        this.emit('navigate', { path, id: itemId });
      } else if (itemId) {
        // Custom handlers via emit
        this.emit('navigate', { id: itemId });
      }
    });

    // Footer item clicks
    this.on('click', '[data-footer-action]', (e, el) => {
      const action = el.dataset.footerAction;
      if (action === 'settings' && this._router) {
        this._router.navigate('/settings');
      } else if (action === 'help') {
        this.emit('help');
      }
    });
  }

  /**
   * Toggle a navigation section's collapsed state.
   * @param {string} sectionId
   * @private
   */
  _toggleSection(sectionId) {
    const sections = { ...this._state.sections };
    sections[sectionId] = !sections[sectionId];
    this.setState({ sections });
  }

  /**
   * Render the sidebar HTML.
   * @returns {string}
   */
  render() {
    const sections = this._props.navSections || DEFAULT_SECTIONS;
    const activePath = this._state.activePath;

    return html`
      <aside class="${CSS.sidebar}" data-component="sidebar">
        <!-- Header / Logo -->
        <div class="${CSS.header}">
          <div class="${CSS.logo}">
            <span class="${CSS.logoIcon}">F</span>
            <span>${this._props.brandLabel || 'Fiona'}</span>
          </div>
        </div>

        <!-- Navigation -->
        <nav class="${CSS.nav}">
          ${sections.map((sec) => this._renderSection(sec, activePath))}
        </nav>

        <!-- Footer -->
        <div class="${CSS.footer}">
          <span class="${CSS.footerVersion}">v${this._props.version || '0.1.0'}</span>
          <div class="${CSS.footerActions}">
            ${this._bottomItems.map((item) => html`
              <button class="${CSS.footerBtn}"
                      data-footer-action="${item.id}"
                      title="${item.label}"
                      aria-label="${item.label}">
                ${ICONS[item.icon] || ICONS.help}
              </button>
            `)}
          </div>
        </div>
      </aside>
    `;
  }

  /**
   * Render a navigation section.
   * @param {SectionDef} section
   * @param {string} activePath
   * @returns {string}
   * @private
   */
  _renderSection(section, activePath) {
    const isCollapsed = this._state.sections[section.id] === true;

    const content = section.items.map((item) => this._renderNavItem(item, activePath));

    if (!section.collapsible) {
      return html`
        <div class="${CSS.navSection}">
          ${content}
        </div>
      `;
    }

    return html`
      <div class="${CSS.navSection}">
        <div class="${CSS.sectionTitle}"
             data-action="toggle-section"
             data-section-id="${section.id}"
             role="button"
             tabindex="0"
             aria-expanded="${!isCollapsed}">
          <span>${section.label}</span>
          <span class="${CSS.chevron} ${isCollapsed ? CSS.chevronCollapsed : ''}">
            ${ICONS.chevronDown}
          </span>
        </div>
        <div class="${CSS.sectionContent} ${isCollapsed ? CSS.sectionCollapsed : ''}">
          ${content}
        </div>
      </div>
    `;
  }

  /**
   * Render a single navigation item.
   * @param {NavItem} item
   * @param {string} activePath
   * @returns {string}
   * @private
   */
  _renderNavItem(item, activePath) {
    const isActive = this._isActive(item, activePath);
    const iconSvg = ICONS[item.icon] || ICONS.dashboard;

    return html`
      <a class="${this.classNames(CSS.navItem, { [CSS.navItemActive]: isActive })}"
         href="${item.path ? '#' + item.path : '#'}"
         data-nav-path="${item.path || ''}"
         data-nav-id="${item.id}"
         title="${item.label}">
        <span class="${CSS.itemIcon}">${iconSvg}</span>
        <span class="${CSS.itemLabel}">${item.label}</span>
        ${item.badge != null ? html`<span class="${CSS.itemBadge}">${item.badge}</span>` : ''}
      </a>
    `;
  }

  /**
   * Determine if a nav item is active.
   * @param {NavItem} item
   * @param {string} activePath
   * @returns {boolean}
   * @private
   */
  _isActive(item, activePath) {
    if (!item.path) return false;
    if (this._router && typeof this._router.isActive === 'function') {
      return this._router.isActive(item.path);
    }
    // Fallback: exact or prefix match
    if (activePath === item.path) return true;
    if (item.path !== '/' && activePath.startsWith(item.path)) return true;
    return false;
  }

  /**
   * Clean up on destroy.
   */
  destroy() {
    if (this._unsubCollapse) {
      this._unsubCollapse();
    }
    if (this._unsubRoute) {
      this._unsubRoute();
    }
    super.destroy();
  }
}

export default Sidebar;
