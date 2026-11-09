# Quartz package contributor guidance

Read the [README](README.md) and relevant package source before editing.
Keep package build inputs and image references reproducible. Preserve evaluator
report contracts and mandatory scan evidence; timeout or missing reports must
not become a successful scan.

Use the relevant `scripts/test-*.py` checks for package changes and existing
image build checks. Report which validations require Docker, registries or
live services; do not claim those ran from static tests alone.
