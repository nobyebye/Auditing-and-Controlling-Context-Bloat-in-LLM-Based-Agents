# External Validation Dataset v1

This immutable research view contains 12 calibration tasks and 60 held-out test
tasks: 24 each for retrieval QA, memory, and multi-step tool use. It stores
derived task records selected with seed 20260727 and points back to pinned
HotpotQA, LongMemEval, and BFCL source versions.

Potential credentials, email addresses, and phone numbers in upstream text are
redacted before persistence. Raw third-party source files remain under the
ignored `data/sources/` directory and are not redistributed by this package.
See `dataset_manifest.json` for record IDs, versions, source hashes, and the
derived `tasks.json` hash.
