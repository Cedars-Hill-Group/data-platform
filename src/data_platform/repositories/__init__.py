"""Repositories package – CRUD interfaces for canonical ontology objects."""

from data_platform.repositories.base import BaseRepository
from data_platform.repositories.companies import CompanyRepository
from data_platform.repositories.normalization import (
    normalize_company_name,
    normalize_person_name,
    normalize_website_domain,
)
from data_platform.repositories.people import PeopleRepository
from data_platform.repositories.projects import ProjectRepository

__all__ = [
    "BaseRepository",
    "CompanyRepository",
    "PeopleRepository",
    "ProjectRepository",
    "normalize_company_name",
    "normalize_person_name",
    "normalize_website_domain",
]
