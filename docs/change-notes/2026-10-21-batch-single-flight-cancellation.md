# Batch cancellation single-flight UX — 2026-10-21

## Confirmed problems
- The Cancel Batch button remained enabled in the cancelling state.
- Repeated calls reset the two-minute terminal deadline; users could inadvertently extend it indefinitely.
- A late cancellation bridge error could revert an already completed run to generating.
- The cancel button could be pressed before start_batch returned its operation ID.

## Implementation
- Guard cancellation by active operation ID and a single-flight ref.
- Expose canCancelBatch to the footer UI; show Starting / Cancelling states with disabled controls.
- Maintain one cancellation deadline per run; reject duplicate clicks without re-arming.
- Ignore bridge failures that arrive after a terminal result.
- Add regression tests for duplicate calls, terminal race, and disabled state.

## Scope
This is frontend reliability work only. It does not change renderer process termination semantics or claim to fix native Windows UI hangs.

## Local verification required
- [ ] cd frontend && npm ci && npm run typecheck && npm test && npm run build
- [ ] Test running/starting/cancelling states on packaged Windows WebView.
- [ ] Verify that lost terminal events still time out and recover.
