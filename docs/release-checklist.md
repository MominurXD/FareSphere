# Live-data release checklist

Do not describe a deployment as fully live-data verified until every required item below passes in the target environment.

## Automated

- [ ] `PYTHONPATH=. pytest -q` passes in `backend/`.
- [ ] `node --check web/app.js` passes.
- [ ] `node --test web/tests/*.test.mjs` passes.
- [ ] `python scripts/validate_static.py` passes.
- [ ] CI is green on the exact commit to be released.

## Credentials and provider verification

- [ ] TfL key is configured and `/api/v1/network/london` returns non-empty live paths.
- [ ] National Rail RDM subscription is active and `/api/v1/rail/departures/KGX` returns a current board.
- [ ] Duffel token is configured in the intended mode and `/api/v1/search` returns current offers for a known route/date.
- [ ] Returned Duffel prices are compared against the Duffel dashboard/API response for at least three searches.
- [ ] Returned National Rail times/platforms are spot-checked against an authoritative National Rail surface for at least three stations.
- [ ] TfL line names/stops are spot-checked against TfL for at least three lines.

## Fare-comparison completeness

- [ ] Do not enable a "cheapest cross-modal journey" marketing claim until a licensed rail-fare provider is integrated.
- [ ] Do not include additional baggage in a live total until the selected offer's ancillary service has been priced.
- [ ] Do not show flexible-date savings in live mode until adjacent dates have been queried from a live provider.

## Legal / attribution

- [ ] Review current TfL Transport Data Service licence and required attribution.
- [ ] Review the current Rail Data Marketplace product licence and National Rail developer/brand guidance.
- [ ] Review current Duffel display/booking requirements for the enabled markets.
- [ ] Confirm no provider credentials or personal data are committed.

## UX

- [ ] Provider status accurately reflects configured sources.
- [ ] Provider outages show an error rather than cached/sample data presented as live.
- [ ] Sample mode, if enabled on a development deployment, is visibly labelled on every sample result.
