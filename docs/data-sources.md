# Data sources and provenance

FareSphere uses provider APIs rather than scraping consumer travel websites.

## OctoTrip Flights

**Use:** default real-time flight search displayed inside FareSphere.

FareSphere parses provider results into its own journey model and keeps provider provenance attached to each result.

## Transport for London Unified API

**Use:** London Journey Planner, quoted fares when supplied, stop resolution and network geometry.

**Runtime:** optional `TFL_APP_KEY`.

The project supports anonymous access at a lower quota and can use an app key when configured.

## traini.ac v1

**Use:** GB rail station lookup, live journeys, operators, headcodes, scheduled/expected times, platforms, delay status and departure boards.

**Runtime:** optional `TRAINIAC_BASE_URL`, defaulting to the public traini.ac API.

This source is used for operational journey data only. FareSphere does not treat it as a ticket-fare source.

## National Rail / Rail Data Marketplace

**Use:** optional direct live departure-board access when an RDM consumer key is configured.

**Runtime:** `NATIONAL_RAIL_API_KEY` and optionally `NATIONAL_RAIL_DEPARTURES_URL`.

Darwin running information is not treated as ticket pricing.

## Duffel

**Use:** optional commercial live airline offer search.

**Runtime:** `DUFFEL_ACCESS_TOKEN`.

## Skyscanner Flights Live Prices

**Use:** optional approved commercial flight pricing.

**Runtime:** `SKYSCANNER_API_KEY`.

## Trainline Partner Solutions

**Use:** future licensed rail commerce/fare search.

**Runtime:** `TRAINLINE_API_BASE_URL`, `TRAINLINE_API_TOKEN` after partnership approval.

No consumer-site scraping or guessed private endpoints are part of FareSphere.

## Rail-fare boundary

The default GB rail integration supplies live operations and journey information but not ticket prices. FareSphere therefore renders the route and explicitly shows **Fare unavailable**.

A future cross-modal cheapest-journey claim requires a licensed rail-fare source.