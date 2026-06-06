# Krita UI Tweaks

Various tweaks for Krita's interface:
  - _Split panes_: create multiple split tabbed panes and arrange documents side by side 
  - _Shared tool_: keep the same tool while switching documents
  - _Toolbar highlighter_: highlight the active tool in the toolbars (not just the toolbox docker)   
  - _Toggle Docking_: enable or disable docking when dragging floating dockers to dockable regions
  - _Tab Options_: Configure the tab appearance (colors, height, max chars, style, etc)
  - _Save and Restore Layouts_: Menu options and shortcuts to save and restore
      split pane layouts as JSON files. Config option to restart Krita with your
      previously opened splits panes.

Krita is a free and open source digital painting program. More info here:
[https://krita.org](https://krita.org)

There's a thread related to this plugin on [krita-artists.org](https://krita-artists.org/t/krita-split-panes-and-other-tweaks/157491)

<table>
  <tr>
    <td>
      <img width="1918" height="1050" alt="screenshot-1" src="https://github.com/user-attachments/assets/3461dc55-aa95-469f-9c9e-5e2a3a6df6f6" />
    </td>
    <td>
      <img width="1918" height="1050" alt="screenshot-2" src="https://github.com/user-attachments/assets/41f66a21-9172-4276-9f6a-1a1112b56ff7" />
    </td>
    <td>
      <img width="1918" height="1050" alt="screenshot-4" src="https://github.com/user-attachments/assets/da3e3038-40c6-400a-b73c-462cf512b7bb" />
    <td>
      <img width="1918" height="1050" alt="screenshot-5" src="https://github.com/user-attachments/assets/804b5098-8076-491a-911d-279291840254" />
    </td>
  </tr>
</table>

### Basic interactions:

- Drag tab with left mouse requires a slight vertical movement to enter drag-and-drop mode.
- Drag tab with middle mouse will immediately enter drag-and-drop mode.
- Right clicking the tab bar shows a context menu.

- Drag to edge regions to create a new split pane.
- Drag over the tab bar to transfer to a particular split pane.

<table>
  <tr>
    <td>
      <img width="1916" height="1051" alt="transfer-tab" src="https://github.com/user-attachments/assets/14941458-218b-42c4-89df-1246342556fa" />
    </td>
    <td>
      <img width="1916" height="1055" alt="make-split" src="https://github.com/user-attachments/assets/b2e19df0-4a74-498f-ba83-dd4ec268fe09" />
    </td>
  </tr>
  <tr>
    <td>
      <img width="1915" height="1052" alt="menu-1" src="https://github.com/user-attachments/assets/fed302b9-6825-4d1c-b89f-1e33a5d81cc9" />
    </td>
    <td>
      <img width="1916" height="1050" alt="menu-2" src="https://github.com/user-attachments/assets/23427a6f-0aec-490b-a57c-2648b5701e62" />
    </td>
  </tr>
</table>

- Lock the layout to avoid closing splits panes when moving tabs around:
  
  https://github.com/user-attachments/assets/223fcc58-179a-40a9-9f4d-1741705ec701
  
## Downloads

Latest version: [v1.1.6.zip](https://github.com/vurentjie/krita_ui_tweaks/archive/refs/tags/v1.1.6.zip)

Development version: [main.zip](https://github.com/vurentjie/krita_ui_tweaks/archive/refs/heads/main.zip)

### Shortcuts:

The following actions can be assigned shortcut keys:

<img width="840" height="368" alt="shortcuts" src="https://github.com/user-attachments/assets/89f4f1c2-427f-4586-8be6-f4c01ca17191" />
  
- **Goto next tab**: `krita_ui_tweaks_next_tab`, **Goto previous tab**: `krita_ui_tweaks_prev_tab`
  
  Cycle through tabs in for the active pane.
  
  When the last tab is reached jumps to the first tab.
  
  When the first tab is reached jumps to the last tab.

- **Reset layout**: `krita_ui_tweaks_reset_layout`
  
  Moves all documents into a single tabbed pane and closes the other split panes 
  
- **Equalize layout**: `krita_ui_tweaks_equalize_layout` 
  
  Resizes the layout so that each split pane's size is equally allocated.
  
  
- **Toggle Layout Locked**: `krita_ui_tweaks_toggle_layout_lock` 
  
  Lock or unlock the layout
  
  When the split layout is locked:
    - new split panes cannot be created
    - existing panes will remain open even when empty
    - tabs can be moved between existing split panes
  
- **Toggle Docking**: `krita_ui_tweaks_toggle_dockers`
  
  Instead of holding ctrl while dragging dockers, you can set a shortcut to toggle docking.

- Layout save/load:
  
  - **Save Layout As…** `krita_ui_tweaks_save_layout_as`
      
      Save the current layout to a JSON file
      
  - **Load Layout** `krita_ui_tweaks_load_layout`
      
      Restore a layout from a saved JSON file
      
  - **Save Current Layout** `krita_ui_tweaks_save_layout`
      
      Save the currently loaded layout.
      
### Configuration:

<table>
  <tr>
    <td>
      <img width="456" height="836" alt="options-1-options" src="https://github.com/user-attachments/assets/a16c41f2-1d07-4c25-a0f0-afd9f197d57f" />
    </td>
    <td>
      <img width="456" height="836" alt="options-2-tabs" src="https://github.com/user-attachments/assets/cdf13fcf-888f-45b8-8248-4c78f63cc1f2" />
    </td>
  </tr>
  <tr>
    <td>
      <img width="456" height="836" alt="options-3-colors" src="https://github.com/user-attachments/assets/4ecc85d1-b14b-4d29-adb3-9f2b37e302dc" />
    </td>
    <td>
      <img width="456" height="836" alt="options-4-translate" src="https://github.com/user-attachments/assets/f7dd1e3b-af7e-4c7a-940b-502f4aeda786" />
    </td>
  </tr>
</table>























