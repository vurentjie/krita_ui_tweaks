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

### Fixed:

- _Toolbar click_: clicking toolbar should make it's split pane active AND
  activate its current tab (if any).
- _Syntax error_: there was error occuring when saving layout when at least one
  open document is new and not associated with a file on disk.

## v1.0.4 - 2026-10-01

### Added:

- _Custom colors_: ability to adjust the ui colors

## v1.0.5 - 2026-13-01

### Changed:

- _Refactored_ canvas alignment, zooming during resize and splitting operations.
  This adds a big performance improvement over previous versions.

### Fixed:

- _Dropzone_ edge case when splitting, a valid drop zone was not showing up.

### Added:

- _Resize hint:_ new option to scale images to viewport size if they are already
  contained in the viewport during resize.
- _Ctrl-drag resizing:_ hold ctrl while resizing and it will scale up or down.

## v1.0.6 - 2026-14-01

### Fixed:

- _Canvas alignment:_ fix an issue introduced with aligning canvas
- _Ctrl-drag resizing:_ fix an issue ctrl-drag resizing
- _Resize hint:_ fix edge case on upsizing
- _Splitting:_ ensure split sizes are correct when make a new split (edge case)

## v1.0.7 - 2026-25-01

### Added:

- _Config option:_ Split handle size
- _Drag and drop:_ Ctrl-drag to move all tabs
- _Scaling modes:_ Apply scaling modes when resizing splits
- _Action:_ Center canvas
- _Fit to View:_
  - Fit to view actions are now all toggles
  - Fit to View Height now works correctly
- _Restore defaults:_ Add buttons to restore default options

### Fixed:

- Fixed issues with rotated views
- Fixed issue where canvas floating messages disappear
- Correctly restore layout sizes. Layout needs to be re-saved for this fix.
- Fix issue when toggling "Show Rulers" it should propagate to all windows

### Removed:

- Removed ctrl-drag resizing (replaced by scaling modes).

## v1.0.8 - 2026-31-01

### Fixed:

- Fixed issue with window flashing when splitting from the menu options
- Fixed issue when "Restore layout" option is enabled, closing a tab does not
  always remove the tab on next restart.

## v1.0.9 - 2026-02-02

### Fixed:

- On startup when recovering an autosave and recovering previous layout, don't
  show warning about modified documents
- CSS tweaks:
  - The tab separator was short by 1px
  - Take into account saturation and lightness for any default colors
- Fully refresh all widgets when switching themes so you don't have to restart
  Krita.

## v1.1.0 - 2026-03-02

### Added:

- Tabs can now render in the default Krita style (this is also the default
  option)
- Added a drop shadow to the drag 'n drop placeholder
- Added config option `Use Krita's default style for tabs` (disable this to
  revert to the original flat tab styles)

### Fixed:

- Fix the issue where the tab bar is unfilled on startup
- Fix issue with section separator in the options dialog
