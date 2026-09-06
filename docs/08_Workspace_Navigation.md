# Workspace navigation

The shared application shell replaces the large hero and horizontal tabs with a left sidebar and a compact, sticky page-title toolbar. Existing page keys, APIs, and model workflows are unchanged. Trained Models and Model Registry remain distinct destinations.

| Group | Pages |
| --- | --- |
| Predict & simulate | Prediction, Optimization |
| Data & training | Dataset Management, Model Training, Trained Models |
| History & administration | Prediction History, Model Registry, Queue, API Tokens |

Desktop navigation is 256 px wide, or 76 px when collapsed. The toolbar toggle switches between labeled links and icons with tooltips. The preference is stored under `edgeml.sidebar.collapsed` in localStorage; blocked storage does not prevent navigation. The language switch has a fixed-width area at the right of the toolbar, and changing language does not change the selected page. Main content uses the remaining width, capped at 1800 px.

At viewport widths of 900 px or less, navigation becomes an overlay drawer. Open it from the toolbar; selecting a page, pressing Escape, clicking the backdrop, or using its close button closes it. Keyboard focus is contained in the open drawer and returns to the toggle on close. Background content is inert while the drawer is open; hidden navigation is inert as well. A skip-to-content link, accessible icon labels, visible focus indicators, and current-page semantics support keyboard navigation. Page changes scroll the document to the top. Sidebar scrolling supports shorter screens.

## Verification

Run `npm run build` in `frontend` to type-check and build the application. For visual acceptance, inspect both languages at desktop and mobile widths: visit all nine pages, collapse and reload, open/close the mobile drawer with keyboard and pointer, and verify wide tables remain within their existing page scroll containers. This shell does not change backend behavior or persist page form data beyond existing page behavior.
