# config/config.py

import os

# Choose environment: "local" or "host"
# You can change this manually, or override with an environment variable
ENVIRONMENT = os.getenv("APP_ENV", "local")

# Spreadsheet configuration (same for both)
SPREADSHEET_ID = "1KMpaAiTMAlWsGxLZaqrWJfIXL8ynUt5i0nfsja7mXWs"

SHEET_GIDS = {
    'security': "1337649065",
    'driver': "2019928657",
    'status': "1969607654",
    'logistic': "1027892338"
}

REFRESH_INTERVAL_SECONDS = 30

# Timezone auto-switch
if ENVIRONMENT == "local":
    LOCAL_TZ = "Asia/Phnom_Penh"
    DEBUG_MODE = True
else:
    LOCAL_TZ = "Asia/Phnom_Penh"  # still show local time even if host is UTC
    DEBUG_MODE = False
    