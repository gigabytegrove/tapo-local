"""Runtime dependency management for TP-Link Local."""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.requirements import RequirementsNotFound, async_process_requirements

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

KASA_DISTRIBUTION = "python-kasa"
KASA_VERSION = "0.10.2"
KASA_REQUIREMENT = f"python-kasa[speedups]=={KASA_VERSION}"
DEPENDENCY_ISSUE_ID = "python_kasa_dependency"


class TPLinkLocalDependencyError(RuntimeError):
    """Raised when TP-Link Local cannot establish its required runtime."""


def installed_kasa_version() -> str | None:
    """Return the installed python-kasa version from the active HA environment."""
    try:
        return version(KASA_DISTRIBUTION)
    except PackageNotFoundError:
        return None


def _create_dependency_issue(hass: HomeAssistant, detail: str) -> None:
    """Create a clear Home Assistant Repairs issue for an unresolved dependency."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        DEPENDENCY_ISSUE_ID,
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key="python_kasa_dependency",
        translation_placeholders={
            "requirement": KASA_REQUIREMENT,
            "detail": detail,
        },
    )


async def async_ensure_kasa(hass: HomeAssistant) -> None:
    """Ensure python-kasa exists, is the required version, and imports cleanly.

    Home Assistant normally processes manifest requirements before loading an
    integration. This explicit preflight provides a second, integration-owned
    safety check and asks Home Assistant's own requirements manager to repair a
    missing or mismatched install before any device I/O begins.
    """
    before = installed_kasa_version()

    if before != KASA_VERSION:
        state = "missing" if before is None else f"version {before}"
        _LOGGER.warning(
            "TP-Link Local requires %s but found %s; asking Home Assistant to "
            "install the required dependency before device setup",
            KASA_REQUIREMENT,
            state,
        )

    try:
        await async_process_requirements(
            hass,
            DOMAIN,
            [KASA_REQUIREMENT],
            is_built_in=False,
        )
    except RequirementsNotFound as exc:
        detail = (
            "Home Assistant could not install the required python-kasa package. "
            "No TP-Link device commands were attempted. Check Home Assistant "
            "Internet/DNS access and available storage, then reload or restart."
        )
        _create_dependency_issue(hass, detail)
        raise TPLinkLocalDependencyError(detail) from exc

    installed = installed_kasa_version()
    if installed != KASA_VERSION:
        detail = (
            f"Home Assistant expected python-kasa {KASA_VERSION} but the active "
            f"runtime reports {installed or 'not installed'}. No TP-Link device "
            "commands were attempted. Reload or restart Home Assistant after "
            "correcting the Python dependency environment."
        )
        _create_dependency_issue(hass, detail)
        raise TPLinkLocalDependencyError(detail)

    try:
        import_module("kasa")
    except (ImportError, OSError) as exc:
        detail = (
            f"python-kasa {installed} is installed but cannot be imported: {exc}. "
            "No TP-Link device commands were attempted. Reload or restart Home "
            "Assistant after correcting the dependency environment."
        )
        _create_dependency_issue(hass, detail)
        raise TPLinkLocalDependencyError(detail) from exc

    ir.async_delete_issue(hass, DOMAIN, DEPENDENCY_ISSUE_ID)

    if before != installed:
        _LOGGER.info(
            "TP-Link Local dependency ready: python-kasa %s is installed and importable",
            installed,
        )
