## Summary

Describe the user problem and the implemented change.

## Scope

- Related issue:
- User-visible behavior:
- Deliberately out of scope:

## Grounding, privacy, and data impact

- Does this change retrieval scope, prompts, citations, upload handling, storage, or deletion?
- Does it add configuration, a migration, a network call, or exposure of sensitive data?

## Verification

- [ ] `make test`
- [ ] `make lint`
- [ ] `make build`
- [ ] `cd apps/web && npm run e2e`, when a cross-boundary workflow changed
- [ ] `make docker-verify`, when packaging, proxying, uploads, or runtime configuration changed
- [ ] Migrations tested from a clean database, when applicable
- [ ] Documentation and configuration examples updated
- [ ] No private documents, credentials, or generated dependency artifacts committed

List exact results, warnings, skipped checks, and additional manual verification. Do not describe an
unexecuted check as passing.

## Compatibility and release impact

- Database migration required: yes / no
- Existing documents require reprocessing: yes / no
- Configuration or environment changes: yes / no
- Changelog entry required: yes / no

## Visual changes

Attach before/after images for interface changes. Use the synthetic sample PDF, state how the image
was captured, and remove private document content.
