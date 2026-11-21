import requests


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def get_weather_forecast(latitude, longitude, start_date, end_date):
    """
    Fetch daily weather forecast for a destination.
    """

    try:
        response = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": (
                    "weather_code,"
                    "temperature_2m_max,"
                    "temperature_2m_min,"
                    "precipitation_probability_max,"
                    "wind_speed_10m_max"
                ),
                "timezone": "auto",
                "start_date": start_date,
                "end_date": end_date,
                "current": (
                    "temperature_2m,"
                    "apparent_temperature,"
                    "relative_humidity_2m,"
                    "weather_code,"
                    "wind_speed_10m,"
                    "is_day"
                ),
            },
            timeout=15
        )

        response.raise_for_status()
        data = response.json()

        daily = data.get("daily", {})

        return {
            "success": True,
            "dates": daily.get("time", []),
            "weather_codes": daily.get("weather_code", []),
            "max_temperatures": daily.get("temperature_2m_max", []),
            "min_temperatures": daily.get("temperature_2m_min", []),
            "rain_probability": daily.get(
                "precipitation_probability_max", []
            ),
            "wind_speed": daily.get("wind_speed_10m_max", []),
            "current": data.get("current", {}),
        }

    except requests.RequestException:
        return {
            "success": False,
            "error": "Weather information is temporarily unavailable."
        }