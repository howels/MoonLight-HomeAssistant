"""Constants for the MoonLight integration."""

DOMAIN = "moonlight"
MANUFACTURER = "MoonModules"

# A board serves its UI and API on port 80, a host (MoonLight as a program on a computer) on 8080.
DEFAULT_PORT = 80

# The device's identity, health and modules, as MoonLight's UI reads them.
SYSTEM_PATH = "/api/system"
REQUEST_TIMEOUT = 10
