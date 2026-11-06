"""Products module — use cases for the Category aggregate."""
from __future__ import annotations

from uuid import UUID

from app.modules.products.application.dtos import CategoryDTO
from app.modules.products.domain.entities import Category
from app.modules.products.domain.exceptions import CategoryInUseError, CategoryNotFoundError
from app.modules.products.domain.repositories import CategoryRepository


class CreateCategory:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    def execute(
        self,
        company_id: UUID,
        *,
        name: str,
        description: str = "",
        parent_id: UUID | None = None,
    ) -> CategoryDTO:
        category = Category(
            company_id=company_id,
            name=name,
            description=description,
            parent_id=parent_id,
        )
        return CategoryDTO.from_entity(self._categories.add(category))


class GetCategory:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    def execute(self, company_id: UUID, category_id: UUID) -> CategoryDTO:
        category = self._categories.get_by_id(category_id)
        if category is None or category.company_id != company_id:
            raise CategoryNotFoundError(category_id)
        return CategoryDTO.from_entity(category)


class ListCategories:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    def execute(self, company_id: UUID) -> list[CategoryDTO]:
        return [
            CategoryDTO.from_entity(c)
            for c in self._categories.list_by_company(company_id)
        ]


class UpdateCategory:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    def execute(
        self,
        company_id: UUID,
        category_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> CategoryDTO:
        category = self._categories.get_by_id(category_id)
        if category is None or category.company_id != company_id:
            raise CategoryNotFoundError(category_id)
        if name is not None:
            category.name = name
        if description is not None:
            category.description = description
        return CategoryDTO.from_entity(self._categories.update(category))


class DeleteCategory:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    def execute(self, company_id: UUID, category_id: UUID) -> bool:
        category = self._categories.get_by_id(category_id)
        if category is None or category.company_id != company_id:
            raise CategoryNotFoundError(category_id)
        # Only empty categories go: subcategories or products (paused ones too) would
        # be left pointing at a category that no longer exists.
        subcategories = self._categories.count_subcategories(category_id)
        products = self._categories.count_products(category_id)
        if subcategories or products:
            raise CategoryInUseError(category_id, subcategories, products)
        if not self._categories.delete(category_id):
            raise CategoryNotFoundError(category_id)
        return True
