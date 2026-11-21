
document.addEventListener("DOMContentLoaded", () => {
    const container = document.getElementById("tripWeatherContainer");
    const refreshButton = document.getElementById("refreshWeatherButton");

    if (!container || !refreshButton) return;

    const weatherDescriptions = {
        0: ["Clear sky", "☀️"],
        1: ["Mainly clear", "🌤️"],
        2: ["Partly cloudy", "⛅"],
        3: ["Overcast", "☁️"],
        45: ["Fog", "🌫️"],
        48: ["Depositing rime fog", "🌫️"],
        51: ["Light drizzle", "🌦️"],
        53: ["Moderate drizzle", "🌦️"],
        55: ["Dense drizzle", "🌧️"],
        61: ["Slight rain", "🌧️"],
        63: ["Moderate rain", "🌧️"],
        65: ["Heavy rain", "🌧️"],
        71: ["Slight snowfall", "🌨️"],
        73: ["Moderate snowfall", "🌨️"],
        75: ["Heavy snowfall", "❄️"],
        80: ["Rain showers", "🌦️"],
        81: ["Moderate rain showers", "🌧️"],
        82: ["Violent rain showers", "⛈️"],
        95: ["Thunderstorm", "⛈️"],
        96: ["Thunderstorm with hail", "⛈️"],
        99: ["Severe thunderstorm with hail", "⛈️"]
    };

    function escapeHTML(value) {
        return String(value ?? "").replace(/[&<>"']/g, char => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#039;"
        })[char]);
    }

    function formatDate(value) {
        return new Date(value + "T00:00:00").toLocaleDateString(
            "en-IN",
            { day: "numeric", month: "short", year: "numeric" }
        );
    }

    function renderWeather(weatherItems) {
        if (!weatherItems.length) {
            container.innerHTML = `
                <p>No destinations with valid coordinates were found.
                Add destinations to your itinerary to see weather.</p>
            `;
            return;
        }

        container.innerHTML = weatherItems.map(item => {
            const weather = item.weather;

            if (!weather || !weather.success || !weather.dates?.length) {
                return `
                    <article class="weather-card weather-unavailable">
                        <h3>${escapeHTML(item.place_name)}</h3>
                        <p>${formatDate(item.date)}</p>
                        <p>Weather forecast is currently unavailable.</p>
                    </article>
                `;
            }

            const code = weather.weather_codes[0];
            const description = weatherDescriptions[code] ||
                ["Unknown conditions", "🌡️"];

            const maxTemp = weather.max_temperatures[0];
            const minTemp = weather.min_temperatures[0];
            const rain = weather.rain_probability[0];
            const wind = weather.wind_speed[0];

            return `
                <article class="weather-card">
                    <div class="weather-card-heading">
                        <div>
                            <span class="weather-day">
                                Day ${escapeHTML(item.day_number)}
                            </span>
                            <h3>${escapeHTML(item.place_name)}</h3>
                            <p>${formatDate(item.date)}</p>
                        </div>
                        <span class="weather-icon">${description[1]}</span>
                    </div>

                    <p class="weather-description">
                        ${escapeHTML(description[0])}
                    </p>

                    <div class="weather-temperature">
                        <span>${maxTemp ?? "--"}°C</span>
                        <span>${minTemp ?? "--"}°C</span>
                    </div>

                    <div class="weather-details">
                        <span>🌧️ Rain: ${rain ?? "--"}%</span>
                        <span>💨 Wind: ${wind ?? "--"} km/h</span>
                    </div>
                </article>
            `;
        }).join("");
    }

    async function loadWeather() {
        container.innerHTML = "<p>Loading destination weather...</p>";
        refreshButton.disabled = true;

        try {
            const response = await fetch(
                `/trips/api/weather/?trip_id=${encodeURIComponent(window.TRIP_ID)}`
            );

            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.error || "Unable to load weather.");
            }

            renderWeather(data.weather || []);

        } catch (error) {
            container.innerHTML = `
                <p class="weather-error">
                    ${escapeHTML(error.message)}
                </p>
            `;
        } finally {
            refreshButton.disabled = false;
        }
    }

    refreshButton.addEventListener("click", loadWeather);

    loadWeather();
});
