"""Runtime dependency management for TP-Link Local."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.importlib import async_import_module
from homeassistant.requirements import RequirementsNotFound, async_process_requirements

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

KASA_DISTRIBUTION = "python-kasa"
KASA_VERSION = "0.10.2"
KASA_REQUIREMENT = f"python-kasa[speedups]=={KASA_VERSION}"
CRYPTO_REQUIREMENT = "cryptography>=1.9"
REQUIRED_REQUIREMENTS = [KASA_REQUIREMENT, CRYPTO_REQUIREMENT]
DEPENDENCY_ISSUE_ID = "python_kasa_dependency"


class TPLinkLocalDependencyError(RuntimeError):
    """Raised when TP-Link Local cannot establish its required runtime."""


def installed_kasa_version() -> str | None:
    """Return installed python-kasa version.

    importlib.metadata performs filesystem I/O, so callers from Home Assistant's
    event loop must run this function in the executor.
    """
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
            "requirement": ", ".join(REQUIRED_REQUIREMENTS),
            "detail": detail,
        },
    )


async def _async_verify_imports(hass: HomeAssistant) -> None:
    """Import runtime modules using Home Assistant's import executor."""
    await async_import_module(hass, "kasa")
    await async_import_module(hass, "cryptography")


async def async_ensure_kasa(hass: HomeAssistant) -> None:
    """Ensure the local-control runtime is installed and importable.

    Home Assistant normally processes manifest requirements before loading an
    integration. This preflight verifies the active runtime and only invokes
    Home Assistant's requirements manager when repair is actually necessary.
    All package metadata I/O and imports are kept off the event loop.
    """
    before = await hass.async_add_executor_job(installed_kasa_version)

    needs_repair = before != KASA_VERSION
    if not needs_repair:
        try:
            await _async_verify_imports(hass)
        except (ImportError, OSError):
            needs_repair = True

    if needs_repair:
        state = "missing" if before is None else f"version {before}"
        _LOGGER.warning(
            "TP-Link Local requires %s but found %s or an unusable runtime; "
            "asking Home Assistant to repair the dependency before device setup",
            KASA_REQUIREMENT,
            state,
        )

        try:
            await async_process_requirements(
                hass,
                DOMAIN,
                REQUIRED_REQUIREMENTS,
                is_built_in=False,
            )
        except RequirementsNotFound as exc:
            detail = (
                "Home Assistant could not install the required local-control Python "
                "packages. No TP-Link device commands were attempted. Check Home "
                "Assistant Internet/DNS access and available storage, then reload or "
                "restart."
            )
            _create_dependency_issue(hass, detail)
            raise TPLinkLocalDependencyError(detail) from exc

    installed = await hass.async_add_executor_job(installed_kasa_version)
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
        await _async_verify_imports(hass)
    except (ImportError, OSError) as exc:
        detail = (
            f"The required local-control runtime is installed but cannot be "
            f"imported: {exc}. No TP-Link device commands were attempted. Reload "
            "or restart Home Assistant after correcting the dependency environment."
        )
        _create_dependency_issue(hass, detail)
        raise TPLinkLocalDependencyError(detail) from exc

    ir.async_delete_issue(hass, DOMAIN, DEPENDENCY_ISSUE_ID)

    if needs_repair:
        _LOGGER.info(
            "TP-Link Local runtime ready: python-kasa %s and cryptography are importable",
            installed,
        )
