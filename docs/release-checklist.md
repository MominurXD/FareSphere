# Live-data release checklist

## Automated

- [ ] `PYTHONPATH=. pytest -q` passes in `backend/`.
- [ ] `node --check web/app.js` passes.
- [ ] `node --test web/tests/*.test.mjs` passes.
- [ ] `python scripts/validate_static.py` passes.
- [ ] `docker build -t faresphere-ci .` passes.
- [ ] CI is green on the exact release commit.

## Unified-search smoke tests

- [ ] `LON → LHR` routes through TfL.
- [ ] `LON → PAD` routes through TfL and never becomes a flight search.
- [ ] `LON → BCN` routes to the flight provider.
- [ ] A current-day GB rail route such as `EUS → MAN` routes to the rail provider.
- [ ] Rail station suggestions work.
- [ ] `/api/v1/rail/departures/KGX` returns a live board.
- [ ] `/api/v1/network/london` returns TfL geometry.

## Integrity checks

- [ ] Flight results show provider provenance and a live price.
- [ ] TfL shows a fare only when TfL returned one.
- [ ] GB rail without ticket pricing displays **Fare unavailable**, not £0.
- [ ] Sample data is visibly labelled when enabled.
- [ ] No provider credentials are committed.

## Optional commercial providers

- [ ] Verify Duffel against the provider response if enabled.
- [ ] Verify Skyscanner against approved partner access if enabled.
- [ ] Verify direct RDM access if enabled.
- [ ] Enable Trainline only with approved partner access.

## Claims

- [ ] Do not claim complete cheapest cross-modal comparison until licensed rail fares are integrated.
- [ ] Do not claim future-date GB rail fare comparison from the current operational rail source.

## Production

- [ ] Render health check is healthy.
- [ ] Public homepage loads.
- [ ] Provider status exposes no secrets.
- [ ] Provider outages show errors rather than fabricated/sample live data.