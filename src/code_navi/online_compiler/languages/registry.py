"""Read-only registration and exact runtime capability filtering."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from types import MappingProxyType

from .models import LanguagePackage, LanguageStatus, RuntimeIdentity

DEFAULT_LANGUAGE_ID = "python"


def normalize_language_name(value: str) -> str:
    """Normalize a stable language ID or declared product alias."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("language name must be a non-empty string")
    return value.strip().casefold()


class LanguageRegistry:
    """Resolve immutable language packages by stable ID or declared alias."""

    def __init__(
        self,
        packages: Iterable[LanguagePackage],
        *,
        default_language_id: str = DEFAULT_LANGUAGE_ID,
    ) -> None:
        entries = tuple(packages)
        if not entries:
            raise ValueError("packages must contain at least one LanguagePackage")
        if any(not isinstance(package, LanguagePackage) for package in entries):
            raise TypeError("packages must contain LanguagePackage values")

        names: dict[str, LanguagePackage] = {}
        by_id: dict[str, LanguagePackage] = {}
        for package in entries:
            if package.id in by_id:
                raise ValueError(f"duplicate language id or alias: {package.id}")
            by_id[package.id] = package
            for name in (package.id, *package.aliases):
                normalized = normalize_language_name(name)
                if normalized in names:
                    raise ValueError(f"duplicate language id or alias: {normalized}")
                names[normalized] = package

        normalized_default = normalize_language_name(default_language_id)
        default = by_id.get(normalized_default)
        if default is None:
            raise ValueError("default_language_id must be a registered stable ID")
        self._packages = entries
        self._by_id: Mapping[str, LanguagePackage] = MappingProxyType(by_id)
        self._by_name: Mapping[str, LanguagePackage] = MappingProxyType(names)
        self._default_language_id = default.id

    @property
    def packages(self) -> tuple[LanguagePackage, ...]:
        """Return packages in stable product order."""

        return self._packages

    @property
    def default(self) -> LanguagePackage:
        """Return the default language package."""

        return self._by_id[self._default_language_id]

    def get(self, name: str) -> LanguagePackage | None:
        """Return a package by stable ID or declared alias, if known."""

        try:
            normalized = normalize_language_name(name)
        except ValueError:
            return None
        return self._by_name.get(normalized)

    def require(self, name: str) -> LanguagePackage:
        """Return a known package or raise a stable lookup error."""

        package = self.get(name)
        if package is None:
            raise KeyError(f"unknown language: {name}")
        return package

    def with_runtime_capabilities(
        self, runtimes: Iterable[RuntimeIdentity]
    ) -> LanguageRegistry:
        """Downgrade enabled packages unless their exact runtime is present."""

        identities = tuple(runtimes)
        if any(not isinstance(runtime, RuntimeIdentity) for runtime in identities):
            raise TypeError("runtimes must contain RuntimeIdentity values")
        exact = {(runtime.runtime_id, runtime.version) for runtime in identities}
        packages = tuple(
            _with_runtime_status(package, exact) for package in self._packages
        )
        return LanguageRegistry(packages, default_language_id=self._default_language_id)


def _with_runtime_status(
    package: LanguagePackage, exact_runtimes: set[tuple[str, str]]
) -> LanguagePackage:
    if package.status is not LanguageStatus.ENABLED or package.runtime is None:
        return package
    identity = (package.runtime.runtime_id, package.runtime.version)
    if identity in exact_runtimes:
        return package
    return replace(package, status=LanguageStatus.UNAVAILABLE)
