# Code Review
Review a diff for correctness, not style alone. Check every changed file against its contract, then against its tests.
Tools: read, test, contract-check
- Read the full diff, not just the summary.
- Check each changed file against its declared contract (files, APIs, schemas).
- Run the tests; a review that did not run tests is incomplete.
- List unknowns explicitly — what you could not verify — instead of guessing.
- Approve, request changes, or reject, with reasons tied to files and lines.
