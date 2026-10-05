# Data sources and provenance

FareSphere uses provider APIs rather than scraping consumer websites.

## Transport for London

**Use:** line/route geometry for Tube, London Overground, Elizabeth line and DLR.

**Runtime environment:** `TFL_APP_KEY`.

**UI attribution:** `Powered by TfL Open Data` plus any additional current attribution required by the TfL Transport Data Service licence for the fields displayed.

FareSphere is independent and must not display TfL branding in a way that suggests endorsement.

## National Rail / Rail Delivery Group

**Use:** live scheduled/expected departures, platforms and cancellations from Darwin through the Rail Data Marketplace.

**Runtime environment:** `NATIONAL_RAIL_API_KEY`, `NATIONAL_RAIL_DEPARTURES_URL`.

**Important:** Darwin running information is not treated as a fare source. Any future rail-fare comparison must use a separately licensed fare/journey-planning source.

## Duffel

**Use:** live airline offer searches.

**Runtime environment:** `DUFFEL_ACCESS_TOKEN`.

FareSphere displays operating-carrier names from the offer data and records Duffel as result provenance. Search-time prices can expire/change; selected offers must be re-fetched before a booking workflow.

## Trainline Partner Solutions

**Use:** intended future rail commerce / fare search.

**Runtime environment:** `TRAINLINE_API_BASE_URL`, `TRAINLINE_API_TOKEN` after partnership approval.

No consumer-site scraping, DOM extraction or guessed private endpoints are part of FareSphere.
