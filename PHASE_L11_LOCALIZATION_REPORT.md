# PHASE L11 — LOCALIZATION / INTERNATIONALIZATION REPORT

## 1. Executive Summary & Objective

Phase L11 implements a clean, lightweight, dependency-free **Localization & Internationalization (i18n) Infrastructure Layer** for Cyclone Twin — Critical Access Restoration Engine.

The objective is to enable seamless multi-language presentation for user-facing UI labels, headings, buttons, tooltips, modal dialogs, and citizen-facing ground report forms without altering domain logic, REST API contracts, machine-readable enum codes, decision mathematics, or simulation state.

### Architectural Invariant Preserved:

$$\text{FORECAST} \neq \text{OBSERVATION} \neq \text{STATE}$$

Localization functions purely as presentation-layer infrastructure. Machine-readable codes (`ROAD_FLOODED`, `CITIZEN`, `SUBMITTED`, `DRAIN_OVERFLOW`, JSON keys, API query parameters) remain 100% immutable across all locales.

---

## 2. Localization Infrastructure Architecture

Implemented in [`frontend/src/i18n/`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/frontend/src/i18n/):

- **`I18nProvider` & `useI18n()`**: [`frontend/src/i18n/i18nContext.jsx`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/frontend/src/i18n/i18nContext.jsx)
  - React Context Provider managing active `locale` state with persistent `localStorage` synchronization (`cyclone_twin_locale`).
  - Exports translation function `t(keyPath, params)` supporting dot-notation (`header.title`, `reportTypes.ROAD_FLOODED`) and parameter interpolation (`{var}`).
  - Automatic fallback chain: `Target Locale` $\rightarrow$ `English (en)` $\rightarrow$ `Key String`.
  - Locale-aware Intl formatters: `formatNumber()`, `formatPercent()`, `formatDate()`, `formatTime()`.
  - Machine code to human label helper getters: `getReportTypeLabel(code)`, `getStatusLabel(code)`.

- **Locale Dictionaries**:
  1. [`frontend/src/i18n/locales/en.js`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/frontend/src/i18n/locales/en.js) — Default English dictionary matching existing product copy.
  2. [`frontend/src/i18n/locales/ta.js`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/frontend/src/i18n/locales/ta.js) — Tamil dictionary tailored for Greater Chennai Corporation (GCC) emergency response operations.

---

## 3. Supported Locales & Locale Switching

| Locale Code | Label | Native Name | Default |
|---|---|---|---|
| `en` | English | English | **Yes** |
| `ta` | Tamil | தமிழ் | No |

### Locale Selector Component:
- Unobtrusive dropdown integrated into header action bar (`🌐 Language: [English | தமிழ்]`).
- Switching locale instantly updates UI text without page reload, state loss, or extra API requests.
- Leaflet map bounds, simulation step, forecast horizon, and citizen report form inputs are strictly preserved across locale transitions.

---

## 4. Machine-Readable Code vs. Presentation Separation

| Internal Code (API / State / DB) | English UI Label (`en`) | Tamil UI Label (`ta`) |
|---|---|---|
| `ROAD_FLOODED` | 🌊 Road Flooded (Water Inundation Observed) | 🌊 சாலையில் வெள்ளம் |
| `ROAD_BLOCKED` | 🚧 Road Blocked (Physical Impassable Blockage) | 🚧 சாலை அடைக்கப்பட்டுள்ளது |
| `ROAD_PASSABLE` | ✅ Road Passable (Road Open & Clear) | ✅ சாலை செல்லத்தக்கது |
| `DRAIN_OVERFLOW` | 💧 Drain Overflowing (Capacity Exceeded) | 💧 வடிகால் வழிகிறது |
| `HOSPITAL_ACCESS_BLOCKED` | 🏥 Hospital Access Blocked | 🏥 மருத்துவமனைப் பாதை அடைக்கப்பட்டுள்ளது |
| `SUBMITTED` | Submitted | சமர்ப்பிக்கப்பட்டது |
| `VALIDATED` | Validated | சரிபார்க்கப்பட்டது |
| `RECONCILED` | Reconciled | ஒருங்கிணைக்கப்பட்டது |
| `CITIZEN` | Citizen Report | பொதுமக்கள் அறிக்கை |

---

## 5. Non-Negotiables Audit

1. **Domain Semantics**: Zero changes to BPR marginal benefit formulas, Dijkstra pathfinding, HAND topography, flood depth grids, or Phase E reconciliation rules.
2. **API Contracts**: REST API field names, query parameters, JSON response schemas, and HTTP status codes remain 100% English machine keys regardless of `Accept-Language` headers.
3. **Data vs. Presentation**: `POST /observations/citizen` receives and stores exact machine codes (`report_type: "ROAD_FLOODED"`). The UI displays localized human labels via `getReportTypeLabel()`.
4. **Dates, Times & Numbers**: Formatted using `Intl.NumberFormat("ta-IN" / "en-US")` and `Intl.DateTimeFormat()` without modifying underlying numeric floating-point values or engineering units.
5. **Accessibility**: Form controls preserve `aria-label={t("header.language")}`, accessible field names, and keyboard focus states.

---

## 6. Verification & Test Suite

- **Phase L11 Tests**: 15 focused tests in [`tests/test_phase_l11_localization.py`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/tests/test_phase_l11_localization.py).
  - Dictionary file existence & key structure validation (`en.js`, `ta.js`, `i18nContext.jsx`)
  - Machine-readable enum immutability under localization (`ROAD_FLOODED`, `ROAD_PASSABLE`, `DRAIN_OVERFLOW`, `HOSPITAL_ACCESS_BLOCKED`)
  - API output neutrality under `Accept-Language: ta-IN` headers
  - Zero state mutation invariant (observation submission with localized headers leaves state version unchanged)
  - Coordinate & numeric float parsing neutrality
  - Architectural invariant assertion ($\text{FORECAST} \neq \text{OBSERVATION} \neq \text{STATE}$)
- **Full Pytest Suite**: 350/350 backend tests passing cleanly.
- **Frontend Build & Lint**: `npm run lint` (0 errors) & `npm run build` (PASS).

---

## 7. System Limitations

- **Number of Languages**: Phase L11 provides infrastructure for two primary locales (`en` and `ta`). The dictionary structure is fully modular so additional languages (e.g. `hi`, `te`) can be added by placing new locale dictionary files in `frontend/src/i18n/locales/`.
- **Backend Error Messages**: Internal exception tracebacks and system logs remain in technical English for developer debugging.
