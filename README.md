# Krita UI Tweaks

## Downloads

If the latest version has any issues, you can download an older version.

- [v1.0.7.zip](https://github.com/vurentjie/krita_ui_tweaks/archive/refs/tags/v1.0.7.zip)
  - [update]: Patched the release to fix toggling "Show Rulers" it should propagate to all windows
  - [update]: Patched the release to add a "scaling per view" config option.
  - [update]: Patched the release to fix an issue with layout restoring.
  - New features:
    - Split handle size can be set in options.
    - Press ctrl when drag and dropping tabs to move all tabs
    - Scaling modes: Apply scaling modes when resizing splits
    - Toolbar action to center canvas
    - Fit to View actions are now all toggles
    - Fit to View Height now works correctly
    - Added reset buttons to restore default options
  - Bug Fixes:
    - Fixed issues with rotated views
    - Fixed issue where canvas floating messages disappear
    - Correctly restore layout sizes. Layout needs to be re-saved for this fix
  - Removed:
    - Ctrl-drag resizing is replaced by scaling modes
- [v1.0.6.zip](https://github.com/vurentjie/krita_ui_tweaks/archive/refs/tags/v1.0.6.zip)
  - Bug fixes:
    - Canvas alignment
    - Ctrl-drag resizing
    - Fix upsizing when "Resize hint" option is enabled
- [v1.0.5.zip](https://github.com/vurentjie/krita_ui_tweaks/archive/refs/tags/v1.0.5.zip)
  - Added ctrl-drag resizing as an alternative (will scale canvas zoom up or
    down during resize)
  - Added new "Resize hint" option (disabled by default). See discussion
    [here](krita-artists.org/t/krita-split-panes-and-other-tweaks/157491)
  - Refactored to improve performance over previous versions
- [v1.0.4.zip](https://github.com/vurentjie/krita_ui_tweaks/archive/refs/tags/v1.0.4.zip)
- [v1.0.3.zip](https://github.com/vurentjie/krita_ui_tweaks/archive/refs/tags/v1.0.3.zip)
- [v1.0.2.zip](https://github.com/vurentjie/krita_ui_tweaks/archive/refs/tags/v1.0.2.zip)
- [v1.0.1.zip](https://github.com/vurentjie/krita_ui_tweaks/archive/refs/tags/v1.0.1.zip)
- [v1.0.0.zip](https://github.com/vurentjie/krita_ui_tweaks/archive/refs/tags/v1.0.0.zip)
  (original release)

You can also download the development version from this link:
[main.zip](https://github.com/vurentjie/krita_ui_tweaks/archive/refs/heads/main.zip)

---

## Description

Various tweaks for Krita's interface.

Krita is a free and open source digital painting program. More info here:
[https://krita.org](https://krita.org)

Plugin features:

- _Split Panes_: create split tabbed panes and arrange documents side by side
- _Toolbar Icons_: highlight the active tool in the toolbars (not just the
  toolbox docker)
- _Shared Tool_: keep the same tool when switching documents
- _Toggle Docking_: enable or disable docking when dragging floating dockers to
  dockable regions
- _Save and Restore Layouts_: Menu options and shortcuts to save and restore
  split pane layouts as JSON files. Config option to restart Krita with your
  previously opened splits panes.
- _Tab Options_: Configure the tab appearance (height, max chars, etc) and tab
  dragging behaviour in the options menu.
- _Layout locking_: You can now lock a layout (see preview below). This is
  helpful when you want to move images around but keep the same layout.
  - When layout's are locked you cannot add or remove split panes.
  - You can drag tabs from one split to another.
  - Closing tabs does not close the split pane.
  - Closing the very last document will take you back to the home screen.
  - There is a menu option and a shortcut to toggle locking.
  - Some other menu options will become disabled when locked.

- _Custom colors_: You can set your own custom background colors

- _Scaling modes_ (See video below for a demo):
  - When resizing split panes you can set a scaling mode that will scale
    the canvas as the view shrinks or expands.
  - Scaling mode is global but there is an option to make it per-view.
  - Scaling mode can be set via toolbar buttons, keyboard shortcuts, or a
    default scaling mode can be set for when Krita starts.
  - Krita's "Fit-to-View" actions will override the scaling mode when resizing.
  - There are three types of scaling modes to choose from:
    - Scaling Mode Anchored
    - Scaling Mode Contained
    - Scaling Mode Expanded

---

### Split Panes:

Screenshot of split panes:

<img width="1760" height="1121" alt="Screenshot" src="https://github.com/user-attachments/assets/0bb37b33-3cf1-4b5f-b90b-92502b6a3da4" />



[Screencast.webm](https://github.com/user-attachments/assets/27f8b16b-b0a3-4d52-9b48-8a5ee166c891)

---

### Docking:

Instead of holding ctrl while dragging dockers, you can set a shortcut to toggle
docking:

[docking.webm](https://github.com/user-attachments/assets/b25dc0c1-afd8-432b-a3e2-71e7053c2989)

---

You can now use the left mouse button to drag tabs. Thanks to
[@10zindraws](https://github.com/10zindraws)

![left-mouse-drag](https://github.com/user-attachments/assets/aa44bcb2-92fb-4e3b-b690-64f76212a29f)

---

### Instructional video:

https://github.com/user-attachments/assets/8da930e0-4f5b-4da1-9fe9-e7bb2000bb1a

---

### Layouts:

You can now lock layouts to avoid closing splits when moving tabs around:

https://github.com/user-attachments/assets/223fcc58-179a-40a9-9f4d-1741705ec701

---

### Scaling modes:

To understand scaling modes add these buttons to a toolbar, and try out different scenarios.

Scaling mode applies to all views being resized, whereas fit-to-view is set per view and has a higher priority.

Note that fit-to-view actions are now also toggles, which differs from the default Krita behaviour.

You can configure a default scaling mode to use in the options dialog.

[update] There is now a config option to make scaling mode per-view instead of global.

<img width="692" height="183" alt="scaling-modes" src="https://github.com/user-attachments/assets/5c8ae7ef-ffbc-438d-a48c-c87f140dd306" />
<img width="314" height="277" alt="scaling-mode-tools" src="https://github.com/user-attachments/assets/38fcccfc-032a-43f2-8f2c-f8d9b69d9985" />

https://github.com/user-attachments/assets/8e54acf1-2aae-4602-bbc6-4744d1be5cf0


---

### Options


<img width="603" height="836" alt="options" src="https://github.com/user-attachments/assets/73f2c058-d47d-49d2-82bf-56883c62c2a0" />
<img width="560" height="839" alt="resizing" src="https://github.com/user-attachments/assets/df286fd3-9d14-4c43-9c05-187402a0d6d1" />
<img width="603" height="836" alt="tabs" src="https://github.com/user-attachments/assets/b086140f-93b3-44a0-ab23-8934e63b4c05" />
<img width="603" height="836" alt="colors" src="https://github.com/user-attachments/assets/88d1cc10-f3d3-4dd7-9938-7a00b654cf00" />
<img width="603" height="836" alt="translations" src="https://github.com/user-attachments/assets/f320ee28-9cc5-4fe5-b251-65f4ec1a6c95" />


