"""Coordinator for the elmax-cloud integration."""

from __future__ import annotations

from asyncio import timeout
from datetime import timedelta
from logging import Logger

from elmax_api.exceptions import (
    ElmaxApiError,
    ElmaxBadLoginError,
    ElmaxBadPinError,
    ElmaxNetworkError,
    ElmaxPanelBusyError,
)
from elmax_api.http import Elmax, GenericElmax
from elmax_api.model.actuator import Actuator
from elmax_api.model.area import Area
from elmax_api.model.cover import Cover
from elmax_api.model.panel import PanelEntry, PanelStatus
from httpx import ConnectError, ConnectTimeout

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_TIMEOUT


class ElmaxCoordinator(DataUpdateCoordinator[PanelStatus]):
    """Coordinator helper to handle Elmax API polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: Logger,
        elmax_api_client: GenericElmax,
        panel: PanelEntry,
        name: str,
        update_interval: timedelta,
    ) -> None:
        """Instantiate the object."""
        self._client = elmax_api_client
        self._panel_entry = panel
        self._state_by_endpoint = None
        super().__init__(
            hass=hass, logger=logger, name=name, update_interval=update_interval
        )

    @property
    def panel_entry(self) -> PanelEntry:
        """Return the panel entry."""
        return self._panel_entry

    def get_actuator_state(self, actuator_id: str) -> Actuator:
        """Return state of a specific actuator."""
        if self._state_by_endpoint is not None:
            return self._state_by_endpoint[actuator_id]
        raise HomeAssistantError("Unknown actuator")

    def get_zone_state(self, zone_id: str) -> Actuator:
        """Return state of a specific zone."""
        if self._state_by_endpoint is not None:
            return self._state_by_endpoint[zone_id]
        raise HomeAssistantError("Unknown zone")

    def get_area_state(self, area_id: str) -> Area:
        """Return state of a specific area."""
        if self._state_by_endpoint is not None and area_id:
            return self._state_by_endpoint[area_id]
        raise HomeAssistantError("Unknown area")

    def get_cover_state(self, cover_id: str) -> Cover:
        """Return state of a specific cover."""
        if self._state_by_endpoint is not None:
            return self._state_by_endpoint[cover_id]
        raise HomeAssistantError("Unknown cover")

    @property
    def http_client(self):
        """Return the current http client being used by this instance."""
        return self._client

    @http_client.setter
    def http_client(self, client: GenericElmax):
        """Set the client library instance for Elmax API."""
        self._client = client

    async def _async_update_data(self):
        try:
            async with timeout(DEFAULT_TIMEOUT):
                # The following command might fail in case of the panel is offline.
                # We handle this case in the following exception blocks.
                status = await self._client.get_current_panel_status()

                # Store a dictionary for fast endpoint state access
                self._state_by_endpoint = {
                    k.endpoint_id: k for k in status.all_endpoints
                }
                return status

        except ElmaxBadPinError as err:
            raise ConfigEntryAuthFailed("Control panel pin was refused") from err
        except ElmaxBadLoginError as err:
            raise ConfigEntryAuthFailed("Refused username/password/pin") from err
        except ElmaxApiError as err:
            raise UpdateFailed(f"Error communicating with ELMAX API: {err}") from err
        except ElmaxPanelBusyError as err:
            raise UpdateFailed(
                "Communication with the panel failed, as it is currently busy"
            ) from err
        except (ConnectError, ConnectTimeout, ElmaxNetworkError) as err:
            if isinstance(self._client, Elmax):
                raise UpdateFailed(
                    "A communication error has occurred. "
                    "Make sure HA can reach the internet and that "
                    "your firewall allows communication with the Meross Cloud."
                ) from err

            raise UpdateFailed(
                "A communication error has occurred. "
                "Make sure the panel is online and that  "
                "your firewall allows communication with it."
            ) from err
