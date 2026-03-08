# data-platform

The data platform layer of the CHG Operating System provides data access, normalization, and storage abstractions. It interacts with the other 3 layers: `ontology-core`, `domain-services`, and the `integration-hub`.

## Overview

| Layer | Role |
|---|---|
| **Connectors** | Adapters to relational databases, cloud data warehouses, and object storage |
| **Repositories** | CRUD interfaces for canonical ontology objects (People, Companies, Projects) |
| **ETL / ELT** | Pipelines that read raw sources (markdown KB, APIs) → canonical objects |
| **Data Quality** | Composable checks and lineage metadata tracking |
| **Knowledge Base** | Markdown file reader / writer backed by `ontology-core` templates |

---

## Quick Start

### 1. Install the package

```bash
pip install -e ".[dev]"
```

`ontology-core` is installed as a direct dependency from GitHub via `pyproject.toml`.

### 2. Configure

Copy the example configuration and fill in your paths / credentials:

```bash
cp config.yaml.example config.yaml   # config.yaml is .gitignored
```

Minimum required fields:

```yaml
knowledge_base:
  path: /absolute/path/to/your/knowledge-base

output:
    path: /absolute/or/relative/output
```

Alternatively, set the `DATA_PLATFORM_CONFIG` environment variable to point at any YAML file.

### 3. Knowledge Base layout

The KB root directory must contain sub-folders for each object type:

```
<knowledge_base.path>/
    people/
        alice-smith.md
        bob-jones.md
    companies/
        acme-corp.md
    projects/
        project-alpha.md
```

Each file uses YAML front-matter followed by markdown content:

```markdown
---
id: abc-123
name: Alice Smith
email: alice@example.com
role: Engineer
organization: Acme Corp
tags: [python, data]
---

Alice is a senior engineer at Acme Corp.
```

---

## Usage Examples

### Run the full ETL pipeline

```python
from pathlib import Path

from data_platform.config import get_config
from data_platform.knowledge_base.reader import KnowledgeBaseReader
from data_platform.etl.markdown_loader import MarkdownETLPipeline
from data_platform.etl.loaders import RepositoryLoader
from data_platform.repositories.people import PeopleRepository
from data_platform.repositories.companies import CompanyRepository
from data_platform.repositories.projects import ProjectRepository

cfg = get_config()  # reads config.yaml

pipeline = MarkdownETLPipeline(
    reader=KnowledgeBaseReader(cfg.knowledge_base.path),
    loader=RepositoryLoader(
        people_repo=PeopleRepository(),
        companies_repo=CompanyRepository(),
        projects_repo=ProjectRepository(),
    ),
)
result = pipeline.run()
print(result)
# MarkdownETLPipeline: extracted=12, transformed=12, loaded=12, errors=0
```

### Generate `properties.json` from the Knowledge Base

```python
from data_platform.config import get_config
from data_platform.knowledge_base import collect_property_catalog

cfg = get_config()
kb = cfg.knowledge_base

catalog, saved = collect_property_catalog(
    kb.path,
    output_path=cfg.output.path / "properties.json",
)

print(saved)
print(len(catalog.firm_type), len(catalog.focus))
```

### Create a new KB file from a template

```python
from data_platform.knowledge_base.writer import KnowledgeBaseWriter
from data_platform.ontology_adapter import TemplateLibrary

writer = KnowledgeBaseWriter(cfg.knowledge_base.path, TemplateLibrary())
path = writer.create("person", name="Carol White", email="carol@example.com", role="Analyst")
print(path)  # .../people/carol-white.md
```

### Run data quality checks

```python
from data_platform.quality.checks import RequiredFieldsCheck, UniqueIdCheck, run_checks

people = people_repo.list()
report = run_checks(
    people,
    checks=[RequiredFieldsCheck(["name", "email"]), UniqueIdCheck()],
)
print(report.summary())
```

### Track lineage

```python
from data_platform.quality.lineage import LineageTracker

tracker = LineageTracker()
tracker.record_etl_result(objects, source="kb/people", pipeline="MarkdownETLPipeline")
print(tracker.summary())
```

---

## Project Structure

```
src/data_platform/
├── __init__.py
├── config.py                   # YAML configuration loader
├── ontology_adapter.py         # Import shim for ontology-core (with stub fallback)
├── _stubs/
│   └── ontology_stubs.py       # Stub Person, Company, Project, TemplateLibrary
├── connectors/
│   ├── base.py                 # Abstract BaseConnector
│   ├── database.py             # SQLAlchemy relational DB connector
│   ├── warehouse.py            # BigQuery / Snowflake / Redshift connector
│   └── object_storage.py       # S3 / GCS / Azure / local connector
├── repositories/
│   ├── base.py                 # Generic BaseRepository[T]
│   ├── people.py               # PeopleRepository
│   ├── companies.py            # CompanyRepository
│   └── projects.py             # ProjectRepository
├── etl/
│   ├── base.py                 # ETLPipeline + ETLResult
│   ├── markdown_loader.py      # MarkdownETLPipeline (KB → repositories)
│   ├── transformers.py         # Person/Company/ProjectTransformer
│   └── loaders.py              # RepositoryLoader
├── quality/
│   ├── checks.py               # DataQualityCheck, built-in checks, run_checks()
│   └── lineage.py              # LineageRecord, LineageTracker
└── knowledge_base/
    ├── reader.py               # KnowledgeBaseReader (markdown parser)
    └── writer.py               # KnowledgeBaseWriter (template-based file creator)

tests/
├── conftest.py                 # Shared fixtures (KB root, config file)
├── test_config.py
├── test_connectors.py
├── test_repositories.py
├── test_etl.py
├── test_knowledge_base.py
└── test_quality.py
```

---

## Running Tests

```bash
pytest                          # all tests
pytest tests/test_etl.py -v    # single module
pytest --cov=data_platform      # with coverage
```

## Linting

```bash
ruff check src/ tests/
ruff format src/ tests/
```

