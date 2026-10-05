# FareSphere architecture

## Runtime

```text
Browser
  |
  v
Static web client
  | same-origin REST
  v
FastAPI unified search
  |
  +-- London city / airport / terminal --> TfL Journey Planner
  +-- GB rail station pair -------------> traini.ac / optional RDM
  +-- Flight route ----------------------> OctoTrip
                                            optional Duffel / Skyscanner
```

## Frontend

The production browser client is dependency-free HTML/CSS/JavaScript with a custom canvas globe.

The main form accepts airport/city IATA codes and GB rail station names/CRS codes. Rail suggestions are loaded from the backend station-search endpoint.

## Backend

Provider adapters live under `backend/app/providers/`.

- `octotrip.py`: default real-time flight search and metropolitan-airport expansion.
- `duffel.py`: optional airline-offer provider.
- `skyscanner.py`: optional approved live-pricing provider.
- `tfl.py`: London network geometry.
- `tfl_journey.py`: London Journey Planner, quoted fares and London terminal resolution.
- `national_rail.py`: GB rail station lookup, live journeys and departure boards via traini.ac v1, with optional direct RDM support.
- `trainline.py`: partner-contract boundary.
- `status.py`: non-secret provider status.

`backend/app/services/live_search.py` is the route-classification layer.

## Routing rules

1. Reject identical origin/destination.
2. Known London city/airport pairs use TfL.
3. London city/airport + resolved London rail terminal uses TfL.
4. Two resolved GB rail endpoints use the rail journey provider.
5. Remaining three-letter routes are treated as flights.

This prevents `LON → PAD` from being sent to the flight provider.

## Accuracy boundary

Missing provider data stays missing.

- Rail fare not supplied -> `total_price = null`.
- UI -> **Fare unavailable**.
- No synthetic £0 or estimated rail price is inserted.

## Future work

1. Add a licensed UK rail-fare source.
2. Add provider-aware caching/rate-limit protection.
3. Add checked-baggage ancillary pricing.
4. Add booking-time flight-offer revalidation.
5. Add persistent users, saved trips and price alerts.