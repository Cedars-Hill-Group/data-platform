from __future__ import annotations

from data_platform import ontology_adapter


def test_get_attributes_catalog_converts_registry_dict(monkeypatch):
    registry_catalog = {
        "$ontology_id": "attributes",
        "$schema_version": "1.0.0",
        "firm_type": [
            {
                "value": "private_equity",
                "description": "Private equity firm.",
            }
        ],
        "focus": [
            {
                "value": "technology",
                "description": "Technology companies.",
            }
        ],
    }

    monkeypatch.setattr(ontology_adapter, "ontology_get_catalog", lambda name: registry_catalog)
    ontology_adapter.get_attributes_catalog.cache_clear()

    catalog = ontology_adapter.get_attributes_catalog()

    assert [prop.field for prop in catalog.properties] == ["firm_type", "focus"]
    assert catalog.get_property("focus") is not None
    assert catalog.get_property("focus").accept_multiple_values is True
    assert catalog.get_property("firm_type").values[0].value == "private_equity"


def test_get_naics_catalog_converts_registry_dict(monkeypatch):
    registry_catalog = {
        "$ontology_id": "naics",
        "$schema_version": "1.0.0",
        "naics_sectors": [
            {
                "code": "51",
                "title": "Information",
                "description": "Information sector.",
            }
        ],
    }

    monkeypatch.setattr(ontology_adapter, "ontology_get_catalog", lambda name: registry_catalog)
    ontology_adapter.get_naics_catalog.cache_clear()

    catalog = ontology_adapter.get_naics_catalog()

    assert len(catalog.sectors) == 1
    assert catalog.sectors[0].code == "51"
    assert catalog.sectors[0].title == "Information"