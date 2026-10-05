# FareSphere

**Live-data-first multimodal journey search and 3D transport visualisation.**

Personal project by **Mohammed Mominur Rahman Miah**.

**Live demo:** https://faresphere-mominur.onrender.com

FareSphere combines flights, London ground transport and live GB rail information in one search interface. Its core rule is simple: **never present invented data as a live fare.**

## What it does

- Unified search for flights, TfL journeys and GB rail journeys.
- Automatic routing based on the origin/destination entered.
- Live TfL journey planning with quoted fares when TfL supplies them.
- Live GB rail routes, operators, headcodes, expected times, platforms, delays and connections.
- Live GB rail departure board.
- Live flight prices displayed directly inside FareSphere.
- London metro-airport expansion for codes such as `LON`.
- London terminal routing, so searches such as `LON → PAD` are treated as ground journeys rather than invalid flights.
- GB rail station suggestions using station names or CRS codes.
- Interactive draggable globe with journey arcs and TfL network overlays.
- Explicit provider provenance and live/sample separation.
- Docker deployment and automated CI.

## Example searches

| Search | Routed to |
| --- | --- |
| `LON → BCN` | Live flight provider |
| `LON → LHR` | TfL Journey Planner + quoted fare |
| `LON → PAD` | TfL Journey Planner via London Paddington stop resolution |
| `EUS → MAN` | Live GB rail journey data |
| `KGX` in the rail board | Live GB departures |

## Data-integrity rules

FareSphere deliberately fails closed when a provider does not supply a field.

1. **No fake live prices.** Missing prices remain unavailable.
2. **No £0 rail fares.** Operational rail data is not treated as ticket pricing.
3. **No guessed baggage charges.**
4. **No synthetic flexible-date savings in live mode.**
5. **Provider provenance stays attached to results.**
6. **Flight prices should be revalidated before booking.**
7. **Licensed rail fares are still required for true cross-modal price comparison.**

## Current integrations

| Source | Purpose | Availability |
| --- | --- | --- |
| OctoTrip Flights | Real-time flight search/prices inside FareSphere | Keyless default flight provider |
| Transport for London Unified API | Journey planning, quoted fares, stop resolution and network geometry | Anonymous access; app key optional |
| traini.ac v1 | Live GB rail journeys, station lookup, platforms, delays and departure boards | Keyless public API |
| Rail Data Marketplace / National Rail Darwin | Optional direct live departure-board source | Consumer key optional |
| Duffel | Optional commercial flight offers | Access token optional |
| Skyscanner Flights Live Prices | Optional commercial flight pricing | Approved API key optional |
| Trainline Partner Solutions | Future licensed rail commerce/fares | Commercial partner access required |

## How routing works

FareSphere's FastAPI backend classifies each request before calling a provider:

1. London city/airport pairs use TfL Journey Planner.
2. London city/airport + a resolved London rail terminal also uses TfL.
3. Two resolved GB rail endpoints use the live GB rail provider.
4. Remaining three-letter routes are treated as flights.

This prevents cases such as `LON → PAD` from being expanded into nonsense flight searches like `LHR → PAD`.

## Current rail-fare limitation

The keyless GB rail source provides live operational journey information but **not ticket fares**. FareSphere therefore displays **Fare unavailable** instead of inventing a price.

Currently supported for GB rail:

- live station lookup;
- same-day journey routing;
- operators and train headcodes;
- scheduled/expected times;
- platforms and delays;
- connection information;
- live departure boards.

A licensed National Rail/rail-commerce fare source is still required for ticket prices and complete future-date rail fare comparison.

## Run locally

Copy the example environment file:

```bash
cp .env.example .env
```

Then run with Docker:

```bash
docker compose up --build
```

Open `http://localhost:5173`.

The FastAPI documentation is available at `http://localhost:8000/docs`.

## Optional provider credentials

```env
TFL_APP_KEY=
NATIONAL_RAIL_API_KEY=
NATIONAL_RAIL_DEPARTURES_URL=
DUFFEL_ACCESS_TOKEN=
SKYSCANNER_API_KEY=
TRAINLINE_API_BASE_URL=
TRAINLINE_API_TOKEN=
```

Credentials are server-side only and must never be committed.

## Tests

```bash
cd backend
PYTHONPATH=. pytest -q

cd ..
node --check web/app.js
node --test web/tests/*.test.mjs
python scripts/validate_static.py
docker build -t faresphere-ci .
```

CI validates the backend, frontend JavaScript, globe geometry, static UI and production Docker image. Regression tests cover London airport transfers, `LON → PAD`, metropolitan flight expansion and GB rail parsing.

## Deployment

Public deployment:

https://faresphere-mominur.onrender.com

Health endpoint:

`/api/v1/health`

## Attribution and independence

FareSphere is an independent personal project and is not affiliated with or endorsed by its data providers. Third-party transport data and booking links remain subject to the relevant provider terms and licences.

## Licence

MIT. Third-party transport data remains subject to the applicable provider/data licences.
