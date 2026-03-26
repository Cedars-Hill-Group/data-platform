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

All other sections (`database`, `warehouse`, `object_storage`, `logging`) are optional and have sensible defaults. See `config.yaml.example` for the full list of options.

Alternatively, set the `DATA_PLATFORM_CONFIG` environment variable to point at any YAML file:

```bash
export DATA_PLATFORM_CONFIG=/path/to/my-config.yaml
```

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

Each file uses YAML front-matter followed by free-form markdown content.

**Person file** (`people/alice-smith.md`):
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

**Company file** (`companies/acme-corp.md`):
```markdown
---
id: co-001
name: Acme Corp
industry: Technology
size: Large
website: https://acme.example.com
tags: [saas, b2b]
---

Acme Corp builds enterprise software solutions.
```

**Project file** (`projects/project-alpha.md`):
```markdown
---
id: proj-001
name: Project Alpha
status: active
owner: alice@example.com
members: [alice@example.com, bob@example.com]
tags: [data, platform]
---

Platform modernisation initiative for Q3.
```

The sub-folder names can be customised in `config.yaml`:

```yaml
knowledge_base:
  path: /path/to/kb
  people_folder: persons      # default: people
  companies_folder: orgs      # default: companies
  projects_folder: initiatives  # default: projects
```

---

## Configuration

`get_config()` loads and validates `config.yaml`, auto-configures logging, and caches the result for the process lifetime.

```python
from data_platform.config import get_config

cfg = get_config()                     # reads config.yaml / $DATA_PLATFORM_CONFIG
cfg = get_config("/path/to/cfg.yaml")  # explicit path

# Access sub-sections
cfg.knowledge_base.path        # Path to the KB root
cfg.output.path                # Path for generated artefacts
cfg.database.url               # SQLAlchemy connection string
cfg.warehouse.type             # bigquery | snowflake | redshift | none
cfg.object_storage.type        # s3 | gcs | azure | local | none
cfg.logging.level              # DEBUG | INFO | WARNING | ERROR | CRITICAL
```

To reset the cache (useful in tests):

```python
from data_platform.config import reset_config_cache
reset_config_cache()
```

---

## Logging

All platform modules share a single `data_platform` logger hierarchy. Call `configure_logging()` once at your entry point, or let `get_config()` do it automatically when a `logging:` section is present in `config.yaml`.

```python
from data_platform.log import configure_logging, get_logger

# One-time setup at the top of your script / application
configure_logging(
    level="DEBUG",        # DEBUG | INFO | WARNING | ERROR | CRITICAL (default: INFO)
    json_logs=False,      # True → emit each record as a single-line JSON object
    log_file="app.log",   # Optional: write to a file in addition to stdout
)

# Per-module usage (use __name__ so each module gets its own scoped logger)
logger = get_logger(__name__)
logger.info("Something happened")
logger.debug("Fine-grained detail: %s", some_value)
```

### JSON logging for log-aggregation pipelines

```python
configure_logging(level="INFO", json_logs=True)
# Each record is emitted as:
# {"timestamp": "2024-01-15T12:34:56+0000", "level": "INFO",
#  "logger": "data_platform.etl.base", "message": "Pipeline started"}
```

### Log levels used across the codebase

| Level | When it is used |
|---|---|
| `DEBUG` | Per-record transforms, individual file reads, SQL queries |
| `INFO` | Connector connect/disconnect, pipeline start/finish, KB reads |
| `WARNING` | Transform errors, data quality violations, recoverable problems |
| `ERROR` | Serious failures requiring human attention |
| `CRITICAL` | Fatal errors that prevent the platform from operating |

---

## Connectors

All connectors implement the `BaseConnector` interface and are context-manager aware.

### Database connector (SQLAlchemy)

Connects to any SQLAlchemy-compatible relational database (SQLite, PostgreSQL, MySQL, …).

```python
from data_platform.config import get_config
from data_platform.connectors.database import DatabaseConnector

cfg = get_config()

# Use as a context manager (auto connect / disconnect)
with DatabaseConnector(cfg.database) as db:
    rows = db.execute("SELECT * FROM people")          # → list[dict]
    rows = db.execute(
        "SELECT * FROM people WHERE org = :org",
        params={"org": "Acme Corp"},
    )

# Manual lifecycle
db = DatabaseConnector(cfg.database)
db.connect()
print(db.is_connected())   # True

# ORM / SQLAlchemy session
session = db.session()     # sqlalchemy.orm.Session
engine  = db.engine        # sqlalchemy.engine.Engine

db.disconnect()
```

`config.yaml` options for `database:`:

```yaml
database:
  url: sqlite:///data_platform.db          # any SQLAlchemy URL
  echo: false                              # log all SQL statements
  pool_size: 5
  max_overflow: 10
```

### Warehouse connector (BigQuery / Snowflake / Redshift)

```python
from data_platform.connectors.warehouse import WarehouseConnector

with WarehouseConnector(cfg.warehouse) as wh:
    rows = wh.execute("SELECT * FROM my_dataset.my_table")
```

`config.yaml` options for `warehouse:`:

```yaml
# BigQuery
warehouse:
  type: bigquery
  project: my-gcp-project
  dataset: my_dataset

# Snowflake
warehouse:
  type: snowflake
  account: myorg-myaccount
  user: username
  password: password
  warehouse: COMPUTE_WH
  database: MY_DB
  schema: PUBLIC

# Redshift
warehouse:
  type: redshift
  user: username
  password: password
  account: my-cluster.abc123.us-east-1.redshift.amazonaws.com
  database: my_db
```

Each backend requires the matching SQLAlchemy dialect to be installed separately (e.g. `pip install sqlalchemy-bigquery`).

### Object storage connector (S3 / GCS / Azure / local)

```python
from pathlib import Path
from data_platform.connectors.object_storage import ObjectStorageConnector

with ObjectStorageConnector(cfg.object_storage) as store:
    # Upload a local file
    store.upload(Path("output/report.json"), remote_key="reports/report.json")

    # Download an object
    store.download("reports/report.json", local_path=Path("/tmp/report.json"))

    # List objects under an optional prefix
    keys = store.list_objects(prefix="reports/")   # → list[str]
```

`config.yaml` options for `object_storage:`:

```yaml
# Amazon S3 (requires boto3)
object_storage:
  type: s3
  bucket: my-bucket
  prefix: data/
  region: us-east-1

# Google Cloud Storage (requires google-cloud-storage)
object_storage:
  type: gcs
  bucket: my-bucket
  prefix: data/

# Azure Blob Storage (requires azure-storage-blob)
object_storage:
  type: azure
  bucket: my-container

# Local filesystem (no extra dependencies)
object_storage:
  type: local
  root_path: /path/to/local/storage
  prefix: data/
```

---

## Repositories

Repositories provide a CRUD interface over canonical ontology objects. The default implementations are in-memory stores (suitable for tests and small datasets). For production, subclass and back onto a database.

### PeopleRepository

```python
from data_platform.repositories.people import PeopleRepository
from data_platform.ontology_adapter import Person

repo = PeopleRepository()

# Save (insert or update)
person = Person(name="Alice Smith", email="alice@example.com", role="Engineer",
                organization="Acme Corp", tags=["python", "data"])
repo.save(person)

# Retrieve by ID
alice = repo.get(person.id)       # → Person | None

# List all
all_people = repo.list()          # → list[Person]

# Filter by any field
engineers = repo.list(role="Engineer")
acme_staff = repo.list(organization="Acme Corp")

# Count
print(repo.count())               # → int

# Delete
repo.delete(person.id)            # → True if existed, False otherwise

# Domain helpers
alice     = repo.find_by_email("alice@example.com")  # → Person | None
acme_team = repo.find_by_organization("Acme Corp")   # → list[Person]
```

### CompanyRepository

```python
from data_platform.repositories.companies import CompanyRepository
from data_platform.ontology_adapter import Company

repo = CompanyRepository()

company = Company(name="Acme Corp", industry="Technology", size="Large",
                  website="https://acme.example.com")
repo.save(company)

repo.get(company.id)                         # → Company | None
repo.list()                                  # → list[Company]
repo.list(industry="Technology")             # filter by field
repo.count()                                 # → int
repo.delete(company.id)                      # → bool

# Domain helpers
repo.find_by_name("Acme Corp")               # → Company | None (case-insensitive)
repo.find_by_industry("Technology")          # → list[Company]
```

### ProjectRepository

```python
from data_platform.repositories.projects import ProjectRepository
from data_platform.ontology_adapter import Project

repo = ProjectRepository()

project = Project(name="Project Alpha", status="active",
                  owner="alice@example.com",
                  members=["alice@example.com", "bob@example.com"])
repo.save(project)

repo.get(project.id)                         # → Project | None
repo.list()                                  # → list[Project]
repo.list(status="active")                   # filter by field
repo.count()                                 # → int
repo.delete(project.id)                      # → bool

# Domain helpers
repo.find_by_owner("alice@example.com")      # → list[Project]
repo.find_by_status("active")               # → list[Project]
repo.find_by_member("bob@example.com")       # → list[Project]
```

---

## ETL / ELT Pipelines

### Run the full ETL pipeline (KB → repositories)

`MarkdownETLPipeline` reads all markdown files from the Knowledge Base, transforms them into canonical objects, and loads them into repositories.

```python
from data_platform.config import get_config
from data_platform.knowledge_base.reader import KnowledgeBaseReader
from data_platform.etl.markdown_loader import MarkdownETLPipeline
from data_platform.etl.loaders import RepositoryLoader
from data_platform.repositories.people import PeopleRepository
from data_platform.repositories.companies import CompanyRepository
from data_platform.repositories.projects import ProjectRepository

cfg = get_config()

people_repo   = PeopleRepository()
companies_repo = CompanyRepository()
projects_repo  = ProjectRepository()

pipeline = MarkdownETLPipeline(
    reader=KnowledgeBaseReader(cfg.knowledge_base.path),
    loader=RepositoryLoader(
        people_repo=people_repo,
        companies_repo=companies_repo,
        projects_repo=projects_repo,
    ),
)
result = pipeline.run()
print(result)
# MarkdownETLPipeline: extracted=12, transformed=12, loaded=12, errors=0
```

### Run a partial pipeline (single object type)

```python
pipeline = MarkdownETLPipeline(
    reader=KnowledgeBaseReader(cfg.knowledge_base.path),
    loader=RepositoryLoader(people_repo=PeopleRepository()),
    object_type="person",   # "person" | "company" | "project"
)
result = pipeline.run()
```

### Inspect the ETLResult

```python
result.pipeline_name          # "MarkdownETLPipeline"
result.records_extracted      # total files read
result.records_transformed    # successfully converted to canonical objects
result.records_loaded         # written to repositories
result.errors                 # list of (source_path, error_message) tuples
result.success_rate           # float 0.0–1.0
result.has_errors             # bool
result.metadata["elapsed_seconds"]  # wall-clock time

if result.has_errors:
    for source, msg in result.errors:
        print(f"  {source}: {msg}")
```

### Use repositories after the pipeline

```python
# Repositories are populated in-place by the pipeline
all_people = people_repo.list()
alice = people_repo.find_by_email("alice@example.com")
```

### Use transformers directly

```python
from data_platform.etl.transformers import PersonTransformer, RawDocument

transformer = PersonTransformer()

raw = RawDocument(
    data={"name": "Bob Jones", "email": "bob@example.com", "role": "Designer"},
    source="manual",
    object_type="person",
)
person = transformer.transform(raw)          # → Person

# Batch transform (errors collected, not raised)
people, errors = transformer.transform_many([raw1, raw2, raw3])
```

The same pattern works for `CompanyTransformer` and `ProjectTransformer`.

### Use RepositoryLoader directly

```python
from data_platform.etl.loaders import RepositoryLoader

loader = RepositoryLoader(
    people_repo=people_repo,
    companies_repo=companies_repo,
    projects_repo=projects_repo,
)

# Load a mixed list of canonical objects
saved_count = loader.load([person1, company1, project1])

# Or load by type
loader.load_people([person1, person2])
loader.load_companies([company1])
loader.load_projects([project1])
```

---

## Knowledge Base

### Reading markdown files

```python
from data_platform.knowledge_base.reader import KnowledgeBaseReader

reader = KnowledgeBaseReader(cfg.knowledge_base.path)

# Read all documents (all types)
docs = reader.read_all()                   # → list[ParsedDocument]

# Read a single object type
people_docs = reader.read_all(object_type="person")   # "person" | "company" | "project"

# Read a single file
doc = reader.read_file(Path("kb/people/alice-smith.md"))

# List file paths without parsing
paths = reader.list_files()                # → list[Path]
paths = reader.list_files(object_type="company")

# Access parsed document fields
doc.path          # pathlib.Path to the source file
doc.object_type   # "person" | "company" | "project"
doc.metadata      # dict parsed from YAML front-matter
doc.content       # markdown body text (after the --- block)
```

To use non-default sub-directory names, pass the `folder_map` from your config:

```python
reader = KnowledgeBaseReader(
    cfg.knowledge_base.path,
    folder_map=cfg.knowledge_base.folder_map,
)
```

### Writing markdown files from templates

```python
from data_platform.knowledge_base.writer import KnowledgeBaseWriter
from data_platform.ontology_adapter import TemplateLibrary

writer = KnowledgeBaseWriter(cfg.knowledge_base.path, TemplateLibrary())

# Create a new file (filename defaults to a slug of the name field)
path = writer.create("person", name="Carol White", email="carol@example.com", role="Analyst")
# → <kb_root>/people/carol-white.md

path = writer.create("company", name="Beta Ltd", industry="Finance", website="https://beta.example.com")
# → <kb_root>/companies/beta-ltd.md

path = writer.create("project", name="Project Beta", status="planning", owner="carol@example.com")
# → <kb_root>/projects/project-beta.md

# Specify an explicit filename
path = writer.create("person", filename="cw-2024", name="Carol White", email="carol@example.com")

# Overwrite an existing file
path = writer.create("person", name="Carol White", overwrite=True)

# Update an existing file (merges new fields with existing front-matter)
writer.update(path, role="Senior Analyst", organization="Beta Ltd")
```

### Generating the property catalog (`properties.json`)

The property catalog collects all unique `firm_type` and `focus` values found across markdown files in the KB and saves them as a structured JSON file for downstream consumers.

```python
from data_platform.knowledge_base import collect_property_catalog

catalog, saved = collect_property_catalog(
    knowledge_base_path=cfg.knowledge_base.path,
    output_path=cfg.output.path / "properties.json",
)

print(saved)                   # Path to the written file
print(catalog.firm_type)       # list[PropertyValue]
print(catalog.focus)           # list[PropertyValue]

for pv in catalog.firm_type:
    print(pv.value, pv.description)
```

To also control the sub-directory names used during the walk:

```python
from data_platform.knowledge_base.properties_catalog import emit_properties_json

catalog, saved = emit_properties_json(
    knowledge_base_path=cfg.knowledge_base.path,
    output_dir=cfg.output.path,
    companies_dir=cfg.knowledge_base.companies_dir,
    people_dir=cfg.knowledge_base.people_dir,
    projects_dir=cfg.knowledge_base.projects_dir,
)
```

When `ontology-core` is installed, `collect_property_catalog` delegates to its `PropertyCollector`; otherwise a built-in fallback collector is used automatically.

---

## Data Quality

### Running checks

```python
from data_platform.quality.checks import (
    RequiredFieldsCheck,
    UniqueIdCheck,
    NoNullNamesCheck,
    TagsFormatCheck,
    run_checks,
)

people = people_repo.list()

report = run_checks(
    records=people,
    checks=[
        RequiredFieldsCheck(["name", "email"]),  # all listed fields must be non-empty
        UniqueIdCheck(),                          # every record must have a unique id
        NoNullNamesCheck(),                       # no record may have a null/blank name
        TagsFormatCheck(),                        # tags must be a list (not None)
    ],
)

print(report.summary())
# Data Quality Report – PASS
#   Checks run: 4
#   Total violations: 0
#   [PASS] RequiredFields(name, email): 0 violation(s)
#   ...

# Programmatic access
report.passed             # bool – True when all checks passed
report.total_violations   # int – total violations across all checks
report.failed_checks()    # list[QualityCheckResult] – only the failing checks

for result in report.results:
    print(result.check_name, result.passed, result.violations)
```

### Built-in checks reference

| Check class | Constructor args | What it verifies |
|---|---|---|
| `RequiredFieldsCheck` | `required_fields: list[str]` | All listed fields are non-null and non-empty |
| `UniqueIdCheck` | *(none)* | Every record has a unique `id` field |
| `NoNullNamesCheck` | *(none)* | No record has a null or blank `name` |
| `TagsFormatCheck` | *(none)* | `tags` field is a list (not `None`) |

### Writing a custom check

```python
from data_platform.quality.checks import DataQualityCheck, QualityCheckResult

class EmailDomainCheck(DataQualityCheck):
    def __init__(self, allowed_domain: str) -> None:
        self._domain = allowed_domain

    @property
    def name(self) -> str:
        return f"EmailDomain(@{self._domain})"

    def run(self, records):
        violations = []
        for record in records:
            email = getattr(record, "email", None) or ""
            if email and not email.endswith(f"@{self._domain}"):
                violations.append(f"Record '{record.id}' has non-company email: {email}")
        return QualityCheckResult(
            check_name=self.name,
            passed=len(violations) == 0,
            violations=violations,
        )

report = run_checks(people, checks=[EmailDomainCheck("acme.example.com")])
```

---

## Lineage Tracking

```python
from data_platform.quality.lineage import LineageTracker, LineageRecord

tracker = LineageTracker()

# Record a single event
rec = tracker.record(
    object_id="abc-123",
    object_type="person",
    source="people/alice-smith.md",
    pipeline="MarkdownETLPipeline",
    operation="load",          # extract | transform | load | create | update
    row_count=1,               # arbitrary extra kwargs stored as metadata
)

# Batch-record lineage for a list of canonical objects
records = tracker.record_etl_result(
    objects=people_repo.list(),
    source="kb/people",
    pipeline="MarkdownETLPipeline",
    operation="load",
)

# Query
history  = tracker.get_history("abc-123")                    # → list[LineageRecord]
all_recs = tracker.get_all()                                 # → list[LineageRecord]
pipeline_recs = tracker.get_by_pipeline("MarkdownETLPipeline")  # → list[LineageRecord]
source_recs   = tracker.get_by_source("kb/people")          # → list[LineageRecord]

# Summary
print(tracker.summary())
# {
#   "total_records": 12,
#   "by_object_type": {"person": 5, "company": 4, "project": 3},
#   "by_pipeline": {"MarkdownETLPipeline": 12}
# }

# Serialise a single record
rec.to_dict()
# {"object_id": "abc-123", "object_type": "person",
#  "source": "people/alice-smith.md", "pipeline": "MarkdownETLPipeline",
#  "operation": "load", "timestamp": "2024-01-15T12:34:56+00:00",
#  "metadata": {"row_count": 1}}
```

---

## Canonical Data Models

The three canonical objects are defined in `data_platform.ontology_adapter` (backed by `ontology-core` when installed, or by local stubs when not).

```python
from data_platform.ontology_adapter import Person, Company, Project

person = Person(
    name="Alice Smith",           # required
    email="alice@example.com",
    role="Engineer",
    organization="Acme Corp",
    bio="Senior engineer at Acme.",
    tags=["python", "data"],
    metadata={"custom_field": "value"},
)
person.id             # auto-generated UUID (or supply your own)
person.created_at     # UTC datetime
person.source_file    # path of the originating markdown file (set by the ETL)

company = Company(
    name="Acme Corp",
    industry="Technology",
    size="Large",
    website="https://acme.example.com",
    description="Enterprise software provider.",
    tags=["saas"],
)

project = Project(
    name="Project Alpha",
    description="Platform modernisation.",
    status="active",
    owner="alice@example.com",
    members=["alice@example.com", "bob@example.com"],
    tags=["data", "platform"],
)
```

All three models accept extra fields (stored in `metadata`) and are fully Pydantic v2 compatible.

---

## `ontology-core` Integration

`data_platform.ontology_adapter` is a thin shim that imports canonical models and tooling from `ontology-core` when available, falling back to local stubs otherwise. This means the library works in any environment without requiring the internal package.

```python
from data_platform.ontology_adapter import ONTOLOGY_CORE_AVAILABLE

if ONTOLOGY_CORE_AVAILABLE:
    print("Using ontology-core models")
else:
    print("Using local stubs")
```

> **Note:** `ontology-core` is an internal CHG OS package. Do not add it to public PyPI dependencies. The fallback stubs are fully functional for development, testing, and standalone deployments.

---

## Project Structure

```
src/data_platform/
├── __init__.py
├── config.py                   # YAML configuration loader
├── log.py                      # Central logging (configure_logging / get_logger)
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
│   ├── transformers.py         # Person/Company/ProjectTransformer + RawDocument
│   └── loaders.py              # RepositoryLoader
├── quality/
│   ├── checks.py               # DataQualityCheck, built-in checks, run_checks()
│   └── lineage.py              # LineageRecord, LineageTracker
└── knowledge_base/
    ├── __init__.py             # Re-exports collect_property_catalog
    ├── reader.py               # KnowledgeBaseReader (markdown parser)
    ├── writer.py               # KnowledgeBaseWriter (template-based file creator)
    └── properties_catalog.py   # collect_property_catalog / emit_properties_json

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

