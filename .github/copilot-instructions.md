# Copilot Instructions for data-platform

## Scope
- Apply these instructions to all Python source and test files in this repository unless a more specific instruction overrides them.
- Treat these as default preferences unless the user explicitly requests a stricter or different approach.

## Architecture and Domain
- Preserve the package structure under `src/data_platform`:
  - `connectors`: data source adapters
  - `repositories`: CRUD interfaces for canonical ontology entities
  - `etl`: extract/transform/load pipelines
  - `knowledge_base`: markdown read/write and property cataloging
  - `quality`: checks and lineage helpers
- Favor small, composable units over cross-module coupling.

## Python and Style
- Target Python 3.11+ and keep full type hints on public functions and methods.
- Use `pathlib.Path` for filesystem paths.
- Keep line length within 100 where practical.
- Follow existing Ruff configuration from `pyproject.toml` (`E`, `F`, `I`, `UP`, `B`; `E501` ignored).
- Match existing docstring style (clear summary plus concise details where useful).

## Configuration and Compatibility
- Use `data_platform.config.get_config()` and `reset_config_cache()` patterns already used in code/tests.
- Keep compatibility for existing knowledge-base project folder keys (`projects_folder` and `projects_dir`).
- Default project directory naming should remain `Properties` unless explicitly changed by user config.
- If behavior or defaults in config models change, update tests and docs in the same PR.

## Logging and Safety
- Use `data_platform.log.get_logger(__name__)` for module loggers.
- Do not log secrets or credentials (log only safe identifiers such as backend type or URL scheme).
- Prefer actionable, structured log messages for ETL phase boundaries and recoverable errors.

## Testing Expectations
- Add or update pytest coverage for behavior changes under `tests/`.
- Prefer focused unit tests that validate defaults, compatibility paths, and error handling.
- For config changes, include cache behavior checks where relevant.

## Change Hygiene
- Keep edits minimal and localized to the requested change.
- Do not rename public APIs or configuration keys without explicit request.
- When modifying behavior surfaced in README examples or configuration samples, update `README.md` and `config.yaml.example` in the same change.
