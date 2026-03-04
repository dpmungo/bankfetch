# Justfile — common development tasks
# Run `just` or `just --list` to see available recipes.

# Show available recipes
default:
    just --list --unsorted

# Authenticate with the bank (opens browser, stores session)
[group('app')]
auth:
    uv run bankfetch auth

# Fetch transactions to CSV  (e.g. `just fetch --from 2024-01-01`)
[group('app')]
fetch *args:
    uv run bankfetch fetch {{args}}

# Run all tests
[group('tests')]
test:
    uv run pytest

# Run a specific test file or test (e.g. `just test-one tests/test_export.py`)
[group('tests')]
test-one file:
    uv run pytest {{file}} -v

# Install dependencies (including dev)
[group('setup')]
install:
    uv sync --dev

# Build the package
[group('setup')]
build:
    uv build

# Run ruff linter
[group('code quality')]
lint:
    uv run ruff check . --fix

# Run ruff formatter
[group('code quality')]
fmt:
    uv run ruff format .

# Type-check with ty
[group('code quality')]
typecheck:
    uv run ty check
