import { html } from '../js/components/BaseComponent.js';
import { createPlaceholderPage } from './_placeholderPage.js';

/* ── Placeholder page: links to Flask-rendered Calendar ── */

const page = createPlaceholderPage({
  title: 'Calendar',
  subtitle: 'Event Management',
  icon: 'calendar',
  description: `Manage events, reminders, and schedules using natural language time input.
    The Calendar page requires the full Jinja2-rendered version for its interactive features.
    Please use the Flask-served page for complete functionality.`,
  actions: [
    { label: 'Open Calendar', action: 'open-calendar', icon: 'calendar' },
    { label: 'Back to Dashboard', action: 'open-dashboard', icon: 'dashboard' },
  ],
});

/* Override mount to add the calendar link action */
const originalMount = page.mount;
page.mount = function (container) {
  originalMount.call(this, container);
  if (!container) return;

  container.querySelectorAll('[data-action="open-calendar"]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      window.location.href = '/calendar';
    });
  });
};

export default page;
