"""Hosts used by Part B's weather sources."""

ANALYTICS_HOSTS: set[str] = {
    "archive-api.open-meteo.com",  # https://open-meteo.com/en/docs/historical-weather-api
    "api.open-meteo.com",  # https://open-meteo.com/en/docs (forecast and recent past days)
    "mapy.geoportal.gov.pl",  # https://mapy.geoportal.gov.pl/wss/service/PZGIK/EGIB/WFS/UslugaZbiorcza
}
