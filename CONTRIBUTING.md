# Contributing to ESP32-S3 Edge Intelligence Platform

## Development Setup

1. Clone the repo:
   ```bash
   git clone https://github.com/krsatyam36/esp32-s3.git ~/Projects/xiao
   cd ~/Projects/xiao
   ```
2. Create a virtual environment:
   ```bash
   python3 -m venv ~/vir_esp32SENSEenv
   source ~/vir_esp32SENSEenv/bin/activate
   pip install -r requirements.txt -r requirements-dev.txt
   ```
3. Run `make check` to verify dependencies
4. Install pre-commit hooks: `pre-commit install`
5. Create `src/config.py` from `src/config.example.py`
6. Create `src/config.h` from `src/config.example.h`

## Code Style

- **Python**: ruff (see `ruff.toml`), line length 100, double quotes
- **Firmware C++**: Arduino style with 4-space indents, `#pragma once` guards
- **Web**: 2-space indents
- **YAML**: 2-space indents (see `.yamllint`)
- All files must pass `make lint` before committing

## Testing

- Run tests: `make pytest`
- Coverage: `make coverage-html`
- All new features should include tests in `tests/`
- Mock external dependencies (ESP32, Ollama) in tests

## Pull Request Process

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```
2. Make changes with descriptive individual commits
3. Add tests for new functionality
4. Ensure `make lint typecheck pytest` passes
5. Push branch and open PR with descriptive title and body
6. Reference related issues in the PR description

## Commit Convention

`type(scope): description`

Types: feat, fix, refactor, test, docs, chore, ci, types

Examples:
- `feat: add dark mode toggle to dashboard`
- `fix: handle camera init timeout gracefully`
- `test: add scene classifier confidence tests`

## Project Structure

```
include/          — C++ firmware headers
src/              — Python host apps + firmware source
src/ai/           — AI modules (YOLO, search, alerts)
src/core/         — Core modules (camera, stream, metrics)
tests/            — Python test files
```

## Code Review Checklist

- [ ] Tests pass
- [ ] Type hints present
- [ ] No hardcoded secrets (use env vars or config files)
- [ ] Linter clean (`make lint`)
- [ ] Type checker passes (`make typecheck`)
- [ ] Backward compatible (no breaking API changes)
