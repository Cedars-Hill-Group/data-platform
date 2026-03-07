"""Repositories package – CRUD interfaces for canonical ontology objects."""

from data_platform.repositories.base import BaseRepository
from data_platform.repositories.companies import CompanyRepository
from data_platform.repositories.people import PeopleRepository
from data_platform.repositories.projects import ProjectRepository

__all__ = [
    "BaseRepository",
    "CompanyRepository",
    "PeopleRepository",
    "ProjectRepository",
]
