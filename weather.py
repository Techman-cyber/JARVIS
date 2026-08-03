"""
Fetches a short, current weather line for the startup greeting - no API key
needed anywhere in this file.

Two free, keyless services chained together:
  1. ipapi.co - guesses your city/lat/lon from your public IP address.
  2. open-meteo.com - turns that lat/lon into an actual current-conditions reading.

Both are best-effort. If either fails (no internet, service down, VPN
confusing the IP lookup, etc.) this just returns "" - callers should treat
that as "skip the weather line", not as an error worth showing the user.
"""

import requests

_WEATHER_CODES = {
    0: "clear skies",
    1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzling", 55: "heavy drizzle",
    61: "light rain", 63: "raining", 65: "pouring rain",
    71: "light snow", 73: "snowing", 75: "heavy snow",
    80: "showery", 81: "showery", 82: "stormy",
    95: "thundery",
}


def _get_location():
    """Returns (lat, lon, city) guessed from the public IP, or (None, None, None)."""
    try:
        r = requests.get("https://ipapi.co/json/", timeout=4)
        r.raise_for_status()
        data = r.json()
        return data.get("latitude"), data.get("longitude"), data.get("city")
    except Exception:
        return None, None, None


def get_current_weather() -> str:
    """Returns something like 'it's about 29°C in Hyderabad and partly cloudy',
    or '' if it couldn't be determined for any reason."""
    lat, lon, city = _get_location()
    if lat is None or lon is None:
        return ""

    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current_weather": True,
                "temperature_unit": "celsius",
            },
            timeout=5,
        )
        r.raise_for_status()
        current = r.json().get("current_weather", {})
        temp = current.get("temperature")
        if temp is None:
            return ""

        desc = _WEATHER_CODES.get(current.get("weathercode"), "")
        place = f" in {city}" if city else ""
        line = f"it's about {temp:.0f}\u00b0C{place} right now"
        if desc:
            line += f" and {desc}"
        return line
    except Exception:
        return ""


if __name__ == "__main__":
    # Run directly to sanity-check this in isolation: python weather.py
    result = get_current_weather()
    print(result if result else "Couldn't determine current weather.")
