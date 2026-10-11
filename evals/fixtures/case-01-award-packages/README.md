# Fixture: case-01-award-packages

Straightforward feature with a mostly complete mockup (BUILD_SPEC §16, required case 1).
A supplier-package list, two package detail pages (one open with an Award Package button,
one already awarded with the button disabled) and a placeholder Reports page.
`mockup.png` is a simple static image of the list layout for the image-capture path.
Every file is local; capture in fixture mode makes no network requests.

`sources/` holds fixture source pages (written for testing, hosted on the fake domain
`docs.fixture.example`, clearly marked as not real documentation). The URL map and recorded
search results are in `evals/cases/case-01-award-packages/sources.json`; one mapped URL is
`unavailable` to simulate an inaccessible source.
