# Changelog

## v1.0.0 - 2026-04-01

_Initial release._

### Added:

- _Split Panes_: create split tabbed panes and arrange documents side by side.
- _Toolbar Icons_: highlight the active tool in the toolbars (not just the
  toolbox docker).
- _Shared Tool_: keep the same tool when switching documents.
- _Toggle Docking_: instead of holding ctrl when dragging floating dockers can
  use a shortcut to enable or disable docking regions when needed.

## v1.0.1 - 2026-07-01

### Added:

- _Left Button Dragging_: can now drag to split with the left button
  [0b5a362](https://github.com/vurentjie/krita_ui_tweaks/pull/1/commits/3b76b1785f36295d290e9d73d0444af63e7ddf53)
  [#1](https://github.com/vurentjie/krita_ui_tweaks/pull/1)
- _Save and Load Layouts_:
  - Save and load layouts as JSON files - options in menu and configurable
    shortcuts.
  - Restore split panes layout when Krita restarts - disabled by default.
- _Tab Appearance_: can change the tab appearance
- _Hide floating messages_: ability to permanently hide the floating message
  that appears on the top left of the canvas
- _Changelog_: Add the changelog to keep track of things.
- _Versioning_: Add the current version details to the README and link to a
  release.

### Fixed:

- _Typo_: fixed a typo in configuration key `krita_ui_teaks` should be
  `krita_ui_tweaks`.

## v1.0.2 - 2026-08-01

### Fixed:

- _Restoring layouts_: fixed an issue when restoring layouts and some files are
  missing, it would cause the layout to break.
- _Perf_: made a change to make the splitting feel more instant

### Changed:

- _Text Edits_: changed "Load Layout" to "Open Layout"

### Added:

- _Shortcuts_: configurable shortcuts for the actions (Save/Open Layouts)
- _Hide the menu button_: added an option to hide the menu button (3 dots)

## v1.0.3 - 2026-09-01

### Added:

- _Layout locking_: adding ability to lock layouts

