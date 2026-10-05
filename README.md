# FareSphere

**Live-data-first travel search and 3D transport visualisation.**

Personal project by **Mohammed Mominur Rahman Miah**.

FareSphere is designed around a simple rule: **never present an invented fare as live travel data**. It combines provider-backed flight search, live UK rail information and London network geometry behind one interface, while keeping sample data isolated to an explicitly enabled development mode.

## What it does

- Interactive draggable globe with route arcs and transport-network overlays.
- Live flight-offer search through Duffel when `DUFFEL_ACCESS_TOKEN` is configured.
- Live TfL Tube / Overground / Elizabeth line / DLR route geometry on the globe when `TFL_APP_KEY` is configured.
- Live National Rail departure boards through the Rail Data Marketplace when its consumer key and endpoint are configured.
- Provider-health/status panel so the UI clearly shows which sources are actually connected.
- Provenance on journey results (`source`, live/sample mode, verified-price flag).
- Explicit failure when a live source is unavailable; live search does **not** fall back to demonstration prices.
- Development-only sample search for UI demonstrations, disabled by default.
- Custom dependency-free canvas globe with pointer rotation and zoom.
- Docker Compose deployment and automated backend/web tests.

## Data-integrity rules

FareSphere intentionally refuses to guess data that should come from a transport provider.

1. **No fake live prices.** If Duffel is not configured, `/api/v1/search` returns an unavailable-provider response.
2. **No guessed baggage charges.** Current live flight search supports included allowance only. Requests asking FareSphere to price additional checked baggage are rejected until ancillary pricing is integrated.
3. **No synthetic flexible-date pricing in live mode.** Adjacent-date sample prices exist only in the development sample endpoint.
4. **Rail departures are not rail fares.** Darwin departure-board data is used for live running information; it is never treated as a ticket price.
5. **Commercial rail fares require a licensed commerce source.** Trainline Partner Solutions is represented by a contract-gated adapter boundary; no scraping or undocumented endpoint guessing is used.
6. **Booking-time revalidation is required.** Airline offers can change or expire, so a production booking flow must re-fetch a selected offer before purchase.

## Current live integrations

| Source | Purpose | Repository status | Access needed |
| --- | --- | --- | --- |
| Duffel | Live flight offers and search-time prices | Implemented | Access token |
| Transport for London Unified API | London network/line geometry | Implemented | TfL app key |
| National Rail Darwin via Rail Data Marketplace | Live GB departures/platforms/cancellations | Implemented | RDM consumer key + subscribed endpoint |
| Trainline Partner Solutions | UK/European rail fares/retailing | Adapter boundary only | Commercial partner approval + official integration docs |

The project does not claim complete cross-modal fare optimisation until a licensed rail-fare provider is connected. That is deliberate: accurate savings require comparable, verified prices from every priced leg.

## Architecture

```text
Browser (HTML/CSS/JS + canvas globe)
              |
              v
         FastAPI API
          /   |   \
         /    |    \
    Duffel   TfL   National Rail
   flights  lines    Darwin
              |
       provider provenance
              |
       verified UI results
```

See [`docs/architecture.md`](docs/architecture.md) for more detail.

## Run the verified local application

### 1. Create configuration

```bash
cp .env.example .env
```

Add whichever live-provider credentials you have. Sample data remains disabled unless you explicitly set:

```env
ENABLE_SAMPLE_DATA=true
```

### 2. Docker

```bash
docker compose up --build
```

Open:

```text
http://localhost:5173
```

API documentation:

```text
http://localhost:8000/docs
```

### Backend-only development

The FastAPI process also serves the static web client when the repository is run directly:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --reload
```

Open `http://localhost:8000`.

## Tests

```bash
cd backend
PYTHONPATH=. pytest -q

cd ..
node --check web/app.js
node --test web/tests/*.test.mjs
python scripts/validate_static.py
```

The provider tests use recorded provider-shaped responses through `httpx.MockTransport`. They verify parsing, request headers, data provenance, no-live-provider failure behaviour and the custom globe geometry without pretending that a network-isolated CI runner is a live provider.

## Provider setup

### TfL

Create a TfL Unified API key and set:

```env
TFL_APP_KEY=...
```

FareSphere uses the official Line API to load current Tube, Overground, Elizabeth line and DLR route sequences.

### National Rail

Register with the Rail Data Marketplace and subscribe to the **Live Departure Board** data product. Set the consumer key and the exact endpoint shown in the subscription's Specification tab:

```env
NATIONAL_RAIL_API_KEY=...
NATIONAL_RAIL_DEPARTURES_URL=https://api1.raildata.org.uk/<your-product-path>/LDBWS/api/20220120/GetDepBoardWithDetails/{crs}
```

### Duffel

Set a server-side access token:

```env
DUFFEL_ACCESS_TOKEN=...
```

Never put a Duffel access token in browser JavaScript or a public repository.

### Trainline Partner Solutions

Trainline rail-commerce data is a partner product. If access is approved, keep the official base URL/token server-side:

```env
TRAINLINE_API_BASE_URL=...
TRAINLINE_API_TOKEN=...
```

The repository intentionally does not scrape Trainline or implement guessed private endpoints.

## Attribution and independence

FareSphere is an independent personal project and is not affiliated with or endorsed by any transport provider.

- **Powered by TfL Open Data** where TfL data is displayed. Contains OS data © Crown copyright and database rights; applicable TfL/OS attribution requirements should be checked against the current TfL data licence before public production deployment.
- National Rail live data, where configured, is sourced from Rail Delivery Group / Rail Data Marketplace and must be displayed in accordance with the subscribed product's licence and National Rail developer/brand guidelines.
- Duffel is identified as the source when Duffel flight offers are displayed.

See [`docs/data-sources.md`](docs/data-sources.md).

## Release status

The codebase is **not considered live-data release-ready until the intended production provider credentials have been configured and the release checklist has been run against those providers**. See [`docs/release-checklist.md`](docs/release-checklist.md).

## Licence

MIT. Third-party transport data remains subject to the applicable provider/data licences.
