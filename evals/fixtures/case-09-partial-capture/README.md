# Fixture: case-09-partial-capture

Partial capture (BUILD_SPEC §16, required case 9). `request-2.html` and `new-request.html`
are linked but deliberately missing (HTTP 404 in fixture mode), and the page references
external CSS/JS and a cloud-metadata image, all of which fixture mode blocks and records.
The capture must be labelled partial and the inventory must not be described as complete.
