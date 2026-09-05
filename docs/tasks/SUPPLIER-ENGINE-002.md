# SUPPLIER-ENGINE-002 — public supplier search adapter

## Goal

Connect canonical M-016 Supplier Search to the Supplier Engine matching core introduced in SUPPLIER-ENGINE-001.

## Scope

- run the existing public internet supplier search for one procurement position;
- convert returned supplier search results into source-attributed `SupplierOfferCandidate` objects;
- preserve the public source URL and deterministic candidate identity;
- keep commercial fields unknown when the search source does not provide them;
- pass candidates through deterministic position-offer matching and return the ranking;
- propagate search failures without fabricating candidates.

## Non-goals

- scrape product pages for price or stock;
- infer VAT, MOQ, lead time, article, brand or manufacturer from unsupported text;
- write to the database;
- send RFQs or supplier messages;
- choose a commercial winner;
- add autonomous external execution.

## Acceptance

Offline regression tests prove that public supplier search results become `public_web` candidates with preserved source attribution, marketplaces remain filtered by the existing M-016 contour, missing commercial terms remain explicit, deterministic candidate IDs are stable, and search errors return no fabricated offers.
