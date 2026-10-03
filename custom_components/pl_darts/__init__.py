"""Premier League Darts voor Home Assistant."""
from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import DartsConfigEntry, DartsCoordinator

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: DartsConfigEntry) -> bool:
    """Zet de integratie op."""
    coordinator = DartsCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DartsConfigEntry) -> bool:
    """Verwijder de integratie."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
