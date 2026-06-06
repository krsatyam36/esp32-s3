# Contributing to ESP32-S3 Edge Intelligence Platform

## Development Setup

1. Clone the repo
2. Run `make check` to verify dependencies
3. Install pre-commit hooks: `pre-commit install`
4. Create `src/config.py` from `src/config.example.py`

## Code Style

- Python: ruff (see `ruff.toml`)
- Firmware C++: Arduino style with 4-space indents
- Web: 2-space indents, Tailwind CSS classes

## Pull Request Process

1. Create a feature branch from `main`
2. Add tests for new functionality
3. Ensure `make check` passes
4. Open PR with descriptive title and body

## Commit Convention

`type(scope): description`

Types: feat, fix, refactor, test, docs, chore, ci, types
