"""Support for Aidot lights."""

import asyncio
import logging
from typing import Any

from aidot.client import AidotClient
from aidot.device_client import DeviceClient
from aidot.exceptions import AidotNotLogin

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGBW_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Light."""
    data = hass.data[DOMAIN][entry.entry_id]
    client: AidotClient = data["client"]
    devices: list[dict[str, Any]] = data["devices"]

    async_add_entities(
        AidotLight(client, device_info)
        for device_info in devices
        if device_info.get("type") == "light"
        and "aesKey" in device_info
        and device_info["aesKey"][0] is not None
    )


class AidotLight(LightEntity):
    """Representation of a Aidot Wi-Fi Light."""

    _attr_has_entity_name = True

    def __init__(self, client: AidotClient, device: dict[str, Any]) -> None:
        """Initialize the light."""
        super().__init__()
        self.device_client: DeviceClient = client.get_device_client(device)
        self._attr_unique_id = self.device_client.info.dev_id
        self._attr_name = None

        manufacturer = self.device_client.info.model_id.split(".")[0]
        model = self.device_client.info.model_id[len(manufacturer) + 1 :]
        mac = format_mac(self.device_client.info.mac)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            connections={(CONNECTION_NETWORK_MAC, mac)},
            manufacturer=manufacturer,
            model=model,
            name=self.device_client.info.name,
            hw_version=self.device_client.info.hw_version,
        )

        supported_color_modes = set()
        if self.device_client.info.enable_rgbw:
            supported_color_modes.add(ColorMode.RGBW)

        if self.device_client.info.enable_cct:
            supported_color_modes.add(ColorMode.COLOR_TEMP)

        if not supported_color_modes:
            supported_color_modes.add(ColorMode.ONOFF)
            if self.device_client.info.enable_dimming:
                supported_color_modes.add(ColorMode.BRIGHTNESS)

        self._attr_supported_color_modes = supported_color_modes

        if ColorMode.RGBW in supported_color_modes:
            self._attr_color_mode = ColorMode.RGBW
        elif ColorMode.COLOR_TEMP in supported_color_modes:
            self._attr_color_mode = ColorMode.COLOR_TEMP
        elif ColorMode.BRIGHTNESS in supported_color_modes:
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_color_mode = ColorMode.ONOFF

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        await self.device_client.async_login()
        self.update_task = self.hass.loop.create_task(self._async_update_loop())

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        if hasattr(self, "update_task"):
            self.update_task.cancel()
        await super().async_will_remove_from_hass()

    async def _async_update_loop(self):
        """Loop to update status."""
        while True:
            try:
                await self.device_client.read_status()
                self.async_write_ha_state()
            except AidotNotLogin:
                await self.device_client.async_login()
            except Exception as e:
                _LOGGER.error(f"Error in update loop: {e}")
                await asyncio.sleep(5)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.device_client.status.online

    @property
    def is_on(self) -> bool:
        """Return True if the light is on."""
        return self.device_client.status.on

    @property
    def brightness(self) -> int:
        """Return the brightness of this light between 0..255."""
        return self.device_client.status.dimming

    @property
    def min_color_temp_kelvin(self) -> int:
        """Return the warmest color_temp_kelvin that this light supports."""
        return self.device_client.info.cct_min

    @property
    def max_color_temp_kelvin(self) -> int:
        """Return the coldest color_temp_kelvin that this light supports."""
        return self.device_client.info.cct_max

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the CT color value in Kelvin."""
        return self.device_client.status.cct

    @property
    def rgbw_color(self) -> tuple[int, int, int, int] | None:
        """Return the rgbw color value [int, int, int, int]."""
        return self.device_client.status.rgbw

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        if not self.is_on:
            await self.device_client.async_turn_on()

        if ATTR_BRIGHTNESS in kwargs:
            await self.device_client.async_set_brightness(kwargs[ATTR_BRIGHTNESS])
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            await self.device_client.async_set_cct(kwargs[ATTR_COLOR_TEMP_KELVIN])
        if ATTR_RGBW_COLOR in kwargs:
            await self.device_client.async_set_rgbw(kwargs[ATTR_RGBW_COLOR])

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self.device_client.async_turn_off()
