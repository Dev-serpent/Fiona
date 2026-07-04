# FionaLocalPages Implementation Task — Complete Remaining Modules

## Objective

FionaLocalPages currently contains several pages and systems that are either placeholders, partially implemented, or only display sample/demo data.

Your task is to **fully implement these modules using the existing Fiona architecture** while preserving compatibility with the rest of the project.

This is primarily an **implementation and integration task**, **not** a redesign task.

Before implementing any feature:

* Review the existing Fiona codebase.
* Locate any existing implementations.
* Reuse existing services whenever possible.
* Avoid duplicating logic.
* Follow existing architectural patterns (Dependency Injection, ToolRuntime, Agent architecture, REST handlers, Terminal commands, etc.).

Unless absolutely necessary, **extend existing systems rather than replacing them.**

---

# General Requirements

For every module listed below:

* Review the existing CLI implementation.
* Review existing backend services.
* Review existing APIs.
* Review documentation.
* Review GUI implementations already present elsewhere in Fiona.
* Integrate those capabilities into FionaLocalPages.

Do **not** implement simplified versions if a complete implementation already exists elsewhere.

The goal is feature parity.

---

# 1. Files Tab

Implement the Files tab as a complete project explorer.

Requirements:

* Display the complete project tree starting from Fiona's root directory.
* Lazy-load directories where appropriate.
* File icons based on type.
* Search/filter files.
* Refresh support.
* Open files in existing editor/viewer.
* Support file metadata.
* Context menu actions where appropriate.
* Integrate with Workspace and Diagnostics where applicable.

Do not hardcode directory structures.

---

# 2. Actions System

Replace the placeholder implementation with a complete Action Management System.

## Architecture

Create a new root directory:

```text
actions/
```

containing:

```text
actions/
├── actions.json
├── *.py
```

Each Python file represents an executable action.

The JSON file stores metadata.

Example metadata:

* name
* filename
* description
* tag
* enabled
* created
* modified

---

## Actions Tab Layout

Implement three primary sections.

### Action History

Display:

* executed actions
* timestamps
* status
* execution duration
* result

Allow filtering and searching.

---

### Actions Library

Display every action contained inside:

```text
actions/
```

Each action should show:

* Name
* Description
* Tag
* File
* Status

Allow:

* execute
* enable/disable
* delete
* duplicate

---

### Action Editor

Implement a complete editor.

Fields:

* Existing File / New File selector
* Code editor (only visible when creating/editing code)
* Description
* Tag

Capabilities:

* Create new actions
* Edit metadata
* Edit code
* Save
* Delete
* Validate before saving

The editor should automatically maintain the JSON metadata.

---

# 3. Macro System

Design and implement a general-purpose Macro System.

The architecture should support:

* recording
* editing
* saving
* loading
* execution
* import/export
* keyboard shortcut assignment
* chaining multiple actions
* future automation integration

Macros should be reusable by:

* Terminal
* Agent
* Actions
* Future ToolRuntime

Design this as a reusable subsystem rather than a page-specific feature.

---

# 4. CamComs Tab

Review:

* CLI implementation
* Existing backend
* Documentation

Implement every existing CamComs capability inside FionaLocalPages using the existing GUI architecture.

Do not create a simplified interface.

Feature parity with the CLI is also expected.

---

# 5. SeeOnDesk

Current implementation is incomplete.

Implement full desktop integration including:

* Running applications
* Installed applications
* Process usage
* CPU usage
* Memory usage
* GPU usage (where supported)
* Application information
* Refresh
* Search
* Filtering

Reuse existing backend components where available.

---

# 6. Key Bindings

QuickTieper currently exists outside FionaLocalPages.

Review the existing QuickTieper implementation.

Move its functionality into the FionaLocalPages Key Bindings page using the existing GUI architecture.

Support:

* Create bindings
* Edit bindings
* Delete bindings
* Enable/Disable
* Categories
* Search
* Import/Export
* Live status
* Conflict detection

The existing architecture should remain reusable.

Do not duplicate logic.

---

# 7. PhiConnect

PhiConnect currently has only minimal implementation.

Review the complete PhiConnect GUI implementation.

Integrate every existing feature into FionaLocalPages.

The only exception is the Agents page, which already exists.

Everything else should reach feature parity.

---

# 8. VSee

Remove the VSee page entirely.

Requirements:

* Remove UI components.
* Remove navigation entries.
* Remove unused routes.
* Remove dead code.
* Remove unused assets.

Do not affect unrelated systems.

---

# 9. Task Tab

Replace placeholder content with a complete task management interface.

Suggested capabilities:

* Task list
* Progress
* Status
* Priority
* Due dates
* Categories
* Search
* Filtering
* Sorting
* Integration with Agent
* Integration with Actions
* Integration with Workspace

---

# 10. Notifications

Replace sample data.

Implement:

* Notification history
* Categories
* Severity
* Search
* Read/Unread
* Clear
* Filtering
* Real-time updates
* System notifications
* Agent notifications

---

# 11. Workspace

Replace placeholders.

Implement a complete Workspace Manager.

Support:

* Workspace creation
* Workspace switching
* Workspace configuration
* Project metadata
* Recent projects
* Workspace persistence
* Session restoration

Integrate with:

* Files
* Terminal
* Agent
* Diagnostics

---

# 12. Diagnostics

Replace sample data.

Implement:

* System diagnostics
* Fiona diagnostics
* Service health
* API status
* ToolRuntime status
* SciRetrieval status
* Cache status
* Error logs
* Dependency checks
* Environment validation

Provide actionable diagnostics rather than raw logs.

---

# 13. Performance

This page currently requires the most work.

Implement a comprehensive performance dashboard.

Include:

* CPU usage
* RAM usage
* GPU usage
* Disk usage
* Network usage
* Active processes
* Running Fiona services
* Cache usage
* ToolRuntime metrics
* Agent metrics
* SciRetrieval metrics
* Response times
* API timings
* Live graphs where appropriate
* Historical statistics where available

Reuse any existing monitoring services.

---

# 14. Plugins

Replace placeholder content.

Implement a Plugin Manager.

Capabilities:

* Installed plugins
* Enable/Disable
* Install
* Remove
* Update
* Plugin metadata
* Dependency information
* Version information
* Plugin status
* Search

Design around Fiona's plugin architecture.

---

# 15. Settings

Replace placeholders with the complete Fiona configuration system.

Expose existing configurable options including:

* Appearance
* Themes
* Terminal
* Agent
* ToolRuntime
* SciRetrieval
* Plugins
* Workspace
* Notifications
* Performance
* Logging
* Key Bindings
* PhiConnect
* CamComs

Settings should edit the actual configuration rather than temporary UI state.

---

# Integration Requirements

All implemented pages should integrate naturally with:

* ToolRuntime
* Agent
* Terminal
* Workspace
* Files
* Actions
* Diagnostics
* Notifications
* Plugin system
* Existing REST APIs
* Existing backend services

Avoid duplicate implementations.

---

# Constraints

* Do **not** redesign FionaLocalPages.
* Do **not** redesign existing backend systems.
* Preserve the existing architecture.
* Reuse existing services wherever possible.
* Extend instead of replacing.
* Maintain backward compatibility.
* Remove placeholder/demo implementations.
* Reach feature parity with existing Fiona components.
* Ensure every implemented feature follows the existing UI/UX patterns of FionaLocalPages.

## Expected Outcome

After completion, FionaLocalPages should function as the **primary graphical interface** for Fiona, exposing the full capabilities of the existing platform rather than placeholder or sample implementations, while remaining modular, maintainable, and fully integrated with the project's architecture.
