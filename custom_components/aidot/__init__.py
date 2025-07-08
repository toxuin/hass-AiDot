"""The aidot integration."""

from __future__ import annotations

import logging

from .helpers import PatchedAidotClient as AidotClient
from aidot.exceptions import AidotAuthFailed

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_LOGIN_INFO,
    CONF_DEVICE_LIST,
    CONF_PRODUCT_LIST,
    CONF_MANUAL_IPS,
    DOMAIN,
    CONF_SELECTED_HOUSE,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up aidot from a config entry."""

    hass.data.setdefault(DOMAIN, {})[CONF_DEVICE_LIST] = entry.data[CONF_DEVICE_LIST]
    hass.data.setdefault(DOMAIN, {})[CONF_LOGIN_INFO] = entry.data[CONF_LOGIN_INFO]
    hass.data.setdefault(DOMAIN, {})[CONF_PRODUCT_LIST] = entry.data[CONF_PRODUCT_LIST]

    devices = entry.data[CONF_DEVICE_LIST]
    products = entry.data.get(CONF_PRODUCT_LIST, [])

    _LOGGER.debug(f"Devices: {devices}")
    _LOGGER.debug(f"Products: {products}")

    for product in products:
        for device in devices:
            if device["productId"] == product["id"]:
                device["product"] = product

    session = async_get_clientsession(hass)
    client = AidotClient(session, token=entry.data[CONF_LOGIN_INFO])

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "devices": devices,
    }

    manual_ips = entry.data.get(CONF_MANUAL_IPS)
    if manual_ips:
        _LOGGER.debug(f"Applying manual IPs: {manual_ips}")
        for device in devices:
            dev_id = device.get("id")
            if dev_id in manual_ips:
                ip_address = manual_ips[dev_id]
                if ip_address:
                    _LOGGER.debug(f"Applying manual IP {ip_address} to device {dev_id}")
                    device_client = client.get_device_client(device)
                    device_client.update_ip_address(ip_address, manual=True)

    client.start_discover()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        client: AidotClient = data["client"]
        client.cleanup()
        hass.data[DOMAIN].pop(CONF_DEVICE_LIST, None)
        hass.data[DOMAIN].pop(CONF_LOGIN_INFO, None)
        hass.data[DOMAIN].pop(CONF_PRODUCT_LIST, None)

    return unload_ok
