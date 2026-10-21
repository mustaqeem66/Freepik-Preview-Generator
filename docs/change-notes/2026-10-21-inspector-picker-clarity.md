# Inspector focus and source picker UX (2026-10-21)

Screenshot diagnosis: the large blue rectangular outline around a clicked Font scale slider came from the explicit `.precision-slider-track:focus-within` CSS rule. Clicking the range gave the entire track keyboard-style focus framing.

Fix: remove the broad rectangle for mouse/touch activation. Keep the native HTML range semantics, keyboard control and a smaller visible `:focus-visible` halo on the circular thumb, including a forced-colors fallback. Do not remove keyboard focus visibility entirely.

The native `FOLDER_DIALOG` intentionally selects **directories**, so the OS file picker may hide file listings. `OPEN_DIALOG` with multi-selection can show image, vector, 3D and CAD files. Expose **Browse Files…** next to **Choose Folder** and explain this clearly, while keeping the existing Add Files button in the Assets section for familiarity. Both entry points invoke the same grant-restricted native selection and respect the app's picker lock. No arbitrary path is authorized.

Local QA: `cd frontend && npm ci && npm run typecheck && npm test && npm run build`; manually verify mouse-clicked slider does not show full-track blue rectangle, Tab-visible dial focus remains, and the two native dialogs differ appropriately on Win32/Cocoa/GTK. No native test passes are claimed.