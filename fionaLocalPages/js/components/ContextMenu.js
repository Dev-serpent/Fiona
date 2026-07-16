/* ==========================================================================
   ContextMenu.js — Right-Click Context Menu
   ==========================================================================
   Singleton right-click context menu with nested submenu support,
   keyboard navigation, disabled items, danger styling, and click-outside
   dismissal.

   Usage:
     import { contextMenu } from './ContextMenu.js';

     element.addEventListener('contextmenu', (e) => {
       e.preventDefault();
       contextMenu.showContextMenu(e.clientX, e.clientY, [
         { label: 'Rename', icon: 'edit', handler: () => console.log('rename') },
         { label: 'Delete', icon: 'trash', danger: true, handler: () => console.log('delete') },
         { divider: true },
         {
           label: 'Share', icon: 'externalLink',
           children: [
             { label: 'Copy Link', handler: () => {} },
             { label: 'Email', handler: () => {} },
           ],
         },
       ]);
     });
   ========================================================================== */

import { html } from './BaseComponent.js';
import { ICONS } from './_icons.js';

/* ── CSS class constants ───────────────────────────────────────────────── */

const CSS = {
  menu: 'c-context-menu',
  item: 'c-context-menu__item',
  itemDanger: 'c-context-menu__item--danger',
  itemDisabled: 'c-context-menu__item--disabled',
  itemIcon: 'c-context-menu__item-icon',
  itemLabel: 'c-context-menu__item-label',
  itemShortcut: 'c-context-menu__item-shortcut',
  separator: 'c-context-menu__separator',
};

/**
 * @typedef {Object} ContextMenuItem
 * @property {string} [label] - Display label
 * @property {string} [icon] - Icon key from ICONS
 * @property {string} [shortcut] - Keyboard shortcut hint
 * @property {boolean} [disabled=false] - Disable the item
 * @property {boolean} [divider=false] - Render as separator
 * @property {boolean} [danger=false] - Danger styling (red)
 * @property {ContextMenuItem[]} [children] - Nested submenu items
 * @property {Function} [handler] - Click handler
 */

/**
 * Create a context menu system.
 * @returns {ContextMenuSystem}
 */
export function createContextMenu() {
  /** @type {Element|null} The currently visible menu element */
  let _menuEl = null;

  /** @type {Function|null} Click-outside listener cleanup */
  let _outsideCleanup = null;

  /** @type {Function|null} Keydown listener cleanup */
  let _keyCleanup = null;

  /** @type {Function|null} Resize listener cleanup */
  let _resizeCleanup = null;

  /** @type {boolean} Whether a submenu is open */
  let _submenuOpen = false;

  /** @type {Object|null} Touch tap tracking for mobile */
  let _touchTapItem = null;

  /* ── Render ──────────────────────────────────────────────────────────── */

  /**
   * Render the context menu at the given position.
   *
   * @param {number} x - Client X coordinate
   * @param {number} y - Client Y coordinate
   * @param {Array<ContextMenuItem>} items
   * @param {boolean} [isSubmenu=false]
   * @private
   */
  function _render(x, y, items, isSubmenu = false) {
    _removeMenu();

    const el = document.createElement('div');
    el.className = CSS.menu;

    el.innerHTML = items.map((item) => {
      if (item.divider) {
        return html`<div class="${CSS.separator}"></div>`;
      }

      const hasChildren = item.children && item.children.length > 0;
      const classes = [
        CSS.item,
        item.danger ? CSS.itemDanger : '',
        item.disabled ? CSS.itemDisabled : '',
      ].filter(Boolean).join(' ');

      return html`
        <div class="${classes}"
             tabindex="${item.disabled ? '-1' : '0'}"
             role="menuitem"
             data-action="${hasChildren ? 'submenu' : 'action'}"
             ${hasChildren ? `data-has-children="true"` : ''}
             ${!item.disabled && !hasChildren ? `data-handler-id="${_indexOf(items, item)}"` : ''}>
          ${item.icon ? html`<span class="${CSS.itemIcon}">${ICONS[item.icon] || ''}</span>` : ''}
          <span class="${CSS.itemLabel}">${item.label || ''}</span>
          ${item.shortcut ? html`<span class="${CSS.itemShortcut}">${item.shortcut}</span>` : ''}
          ${hasChildren ? html`<span class="${CSS.itemIcon}" style="margin-left: auto;">${ICONS.chevronRight}</span>` : ''}
        </div>
      `;
    }).join('');

    document.body.appendChild(el);

    // Position with boundary detection
    _positionMenu(el, x, y, isSubmenu);

    // Set up interactivity
    _setupInteractions(el, items);

    // Click-outside dismiss
    _outsideCleanup = _onClickOutside(el);

    // Keyboard navigation
    _keyCleanup = _setupKeyboardNav(el, items);

    // Reposition on window resize
    const resizeHandler = () => _positionMenu(el, x, y, isSubmenu);
    window.addEventListener('resize', resizeHandler);
    _resizeCleanup = () => window.removeEventListener('resize', resizeHandler);

    _menuEl = el;
  }

  /**
   * Position a menu element, keeping it within the viewport.
   * @param {Element} el
   * @param {number} x
   * @param {number} y
   * @param {boolean} isSubmenu
   * @private
   */
  function _positionMenu(el, x, y, isSubmenu) {
    el.style.position = 'fixed';
    el.style.left = '-9999px';
    el.style.top = '-9999px';

    // Force layout
    el.style.display = 'block';
    const rect = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let left = x;
    let top = y;

    // Flip horizontally if overflowing
    if (left + rect.width > vw - 8) {
      left = isSubmenu ? x - rect.width - 8 : vw - rect.width - 8;
    }
    if (left < 8) left = 8;

    // Flip vertically if overflowing
    if (top + rect.height > vh - 8) {
      top = vh - rect.height - 8;
    }
    if (top < 8) top = 8;

    el.style.left = `${left}px`;
    el.style.top = `${top}px`;
  }

  /**
   * Set up interaction handlers for menu items.
   * @param {Element} el
   * @param {ContextMenuItem[]} items
   * @private
   */
  function _setupInteractions(el, items) {
    const itemEls = el.querySelectorAll(`.${CSS.item}`);

    itemEls.forEach((itemEl, index) => {
      const item = items[index];
      if (!item || item.divider) return;

      // Hover: show submenu
      itemEl.addEventListener('mouseenter', () => {
        // Highlight item
        itemEls.forEach((ie) => ie.classList.remove('c-context-menu__item--selected'));
        itemEl.classList.add('c-context-menu__item--selected');

        // Show submenu if children exist
        if (item.children && item.children.length > 0) {
          _submenuOpen = true;
          const rect = itemEl.getBoundingClientRect();
          _render(rect.right, rect.top, item.children, true);
        }
      });

      // Click handler (mouse)
      itemEl.addEventListener('mousedown', (e) => {
        e.preventDefault();
        e.stopPropagation();
      });

      itemEl.addEventListener('mouseup', (e) => {
        e.stopPropagation();
        if (item.disabled) return;
        if (item.children && item.children.length > 0) return;
        _removeMenu();
        if (item.handler) {
          item.handler();
        }
      });

      // Click handler (touch)
      itemEl.addEventListener('touchstart', (e) => {
        if (item.disabled) return;
        if (item.children && item.children.length > 0) return;
        // Delay slightly to allow scroll vs tap discrimination
        _touchTapItem = item;
      }, { passive: true });

      itemEl.addEventListener('touchend', (e) => {
        if (_touchTapItem !== item) return;
        _touchTapItem = null;
        if (item.disabled) return;
        if (item.children && item.children.length > 0) return;
        e.preventDefault();
        _removeMenu();
        if (item.handler) {
          item.handler();
        }
      });
    });
  }

  /**
   * Listen for clicks outside the menu to dismiss.
   * @param {Element} el
   * @returns {Function}
   * @private
   */
  function _onClickOutside(el) {
    const mouseHandler = (e) => {
      if (!el.contains(e.target)) {
        _removeMenu();
      }
    };
    const touchHandler = (e) => {
      if (!el.contains(e.target)) {
        _removeMenu();
      }
    };
    // Use mousedown to catch before mouseup on items
    document.addEventListener('mousedown', mouseHandler);
    document.addEventListener('touchstart', touchHandler, { passive: true });
    return () => {
      document.removeEventListener('mousedown', mouseHandler);
      document.removeEventListener('touchstart', touchHandler);
    };
  }

  /**
   * Set up keyboard navigation within the menu.
   * @param {Element} el
   * @param {ContextMenuItem[]} items
   * @returns {Function}
   * @private
   */
  function _setupKeyboardNav(el, items) {
    const handler = (e) => {
      const focusable = Array.from(el.querySelectorAll(`.${CSS.item}:not(.${CSS.itemDisabled})`));
      if (focusable.length === 0) return;

      const currentIdx = focusable.indexOf(document.activeElement);

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          {
            const next = (currentIdx + 1) % focusable.length;
            focusable[next].focus();
          }
          break;

        case 'ArrowUp':
          e.preventDefault();
          {
            const prev = (currentIdx - 1 + focusable.length) % focusable.length;
            focusable[prev].focus();
          }
          break;

        case 'ArrowRight':
          e.preventDefault();
          {
            // If focused item has submenu, show it
            const focused = focusable[currentIdx];
            if (focused && focused.dataset.hasChildren === 'true') {
              const idx = Array.from(el.children).indexOf(focused);
              const item = items[idx];
              if (item && item.children) {
                _submenuOpen = true;
                const rect = focused.getBoundingClientRect();
                _render(rect.right, rect.top, item.children, true);
              }
            }
          }
          break;

        case 'ArrowLeft':
          e.preventDefault();
          // If this is a submenu, close it (handled by clicking outside)
          _removeMenu();
          break;

        case 'Enter':
        case ' ':
          e.preventDefault();
          {
            const focused = focusable[currentIdx];
            if (focused) {
              const idx = Array.from(el.children).indexOf(focused);
              const item = items[idx];
              if (item && !item.disabled && item.handler && !item.children) {
                _removeMenu();
                item.handler();
              }
            }
          }
          break;

        case 'Escape':
          e.preventDefault();
          _removeMenu();
          break;
      }
    };

    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }

  /**
   * Remove the current menu from the DOM.
   * @private
   */
  function _removeMenu() {
    if (_menuEl) {
      _menuEl.remove();
      _menuEl = null;
    }
    if (_outsideCleanup) { _outsideCleanup(); _outsideCleanup = null; }
    if (_keyCleanup) { _keyCleanup(); _keyCleanup = null; }
    if (_resizeCleanup) { _resizeCleanup(); _resizeCleanup = null; }
    _submenuOpen = false;
  }

  /**
   * Get the index of an item in an array (for data attribute mapping).
   * @param {Array} arr
   * @param {*} item
   * @returns {number}
   * @private
   */
  function _indexOf(arr, item) {
    return arr.indexOf(item);
  }

  /* ── Public API ──────────────────────────────────────────────────────── */

  /**
   * Show a context menu at the given coordinates.
   *
   * @param {number} x - Client X position
   * @param {number} y - Client Y position
   * @param {ContextMenuItem[]} items - Menu items
   */
  function showContextMenu(x, y, items) {
    // Ensure any existing menu is removed first
    _removeMenu();
    _render(x, y, items);
  }

  /**
   * Hide the context menu.
   */
  function hideContextMenu() {
    _removeMenu();
  }

  return {
    showContextMenu,
    hideContextMenu,
  };
}

/**
 * @typedef {Object} ContextMenuSystem
 * @property {(x: number, y: number, items: ContextMenuItem[]) => void} showContextMenu
 * @property {() => void} hideContextMenu
 */

/**
 * Singleton context menu instance.
 *
 * Import and use directly:
 *   import { contextMenu } from './ContextMenu.js';
 *   contextMenu.showContextMenu(e.clientX, e.clientY, [...]);
 *
 * @type {ContextMenuSystem}
 */
export const contextMenu = createContextMenu();

export default contextMenu;
