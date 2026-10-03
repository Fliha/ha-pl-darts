"""Gedeelde basis voor alle entiteiten."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DartsCoordinator


class DartsEntity(CoordinatorEntity[DartsCoordinator]):
    """Basis-entiteit, allemaal onder één apparaat."""

    _attr_has_entity_name = True
    _attr_attribution = "Data: SofaScore (onofficieel) of Wikipedia (CC BY-SA), schema van de PDC"

    def __init__(
        self, coordinator: DartsCoordinator, key: str, platform: str, device: str = "pl"
    ) -> None:
        super().__init__(coordinator)
        # Vaste entity-id's, zodat de voorbeeldkaart in elke taal werkt.
        self.entity_id = f"{platform}.pl_darts_{key}"
        self._attr_unique_id = f"{DOMAIN}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DEVICES[device]


DEVICES = {
    "pl": DeviceInfo(
        identifiers={(DOMAIN, "premier_league")},
        name="Premier League Darts",
        manufacturer="PDC",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://www.pdc.tv/tournaments/premier-league",
    ),
    "wk": DeviceInfo(
        identifiers={(DOMAIN, "world_championship")},
        name="WK Darts",
        manufacturer="PDC",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://www.pdc.tv/tournaments/world-darts-championship",
    ),
}
