const savedPlacesGrid = document.getElementById("savedPlacesGrid");
const savedCount = document.getElementById("savedCount");
const emptySavedState = document.getElementById("emptySavedState");
const savedMessage = document.getElementById("savedMessage");

function escapeSavedHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    })[character]);
}

function getSavedImage(place) {
    const images = Array.isArray(place.images) ? place.images : [];

    for (const image of images) {
        const url = typeof image === "string"
            ? image
            : image?.url || image?.image_url || image?.thumbnail;

        if (!url) continue;

        try {
            const parsed = new URL(url, window.location.origin);

            if (["https:", "http:"].includes(parsed.protocol)) {
                return parsed.href;
            }
        } catch (error) {
            continue;
        }
    }

    return "";
}

async function loadSavedPlaceImage(place, card) {
    const params = new URLSearchParams({
        id: place.source?.osm_id || place.osm_id || place.id || "",
        name: place.name || "",
        city: place.address?.city || "",
        state: place.address?.state || ""
    });

    try {
        const response = await fetch(
            `/places/api/place-image/?${params.toString()}`,
            {
                headers: { "Accept": "application/json" },
                credentials: "same-origin"
            }
        );

        if (!response.ok) return;

        const result = await response.json();

        const firstImage = (result.images || []).find(image => {
            const url = typeof image === "string"
                ? image
                : image?.url || image?.image_url || image?.thumbnail;

            if (!url) return false;

            try {
                return ["https:", "http:"].includes(
                    new URL(url, window.location.origin).protocol
                );
            } catch {
                return false;
            }
        });

        if (!firstImage || !card.isConnected) return;

        const url = typeof firstImage === "string"
            ? firstImage
            : firstImage.url ||
              firstImage.image_url ||
              firstImage.thumbnail;

        const container = card.querySelector(".saved-card-image");

        if (!container || container.querySelector("img")) return;

        const image = document.createElement("img");

        image.src = url;
        image.alt = place.name || "Saved destination";
        image.loading = "lazy";
        image.referrerPolicy = "no-referrer";

        image.addEventListener("error", () => image.remove(), {
            once: true
        });

        const placeholder = container.querySelector(
            ".saved-image-placeholder"
        );

        if (placeholder) placeholder.remove();

        container.prepend(image);

    } catch (error) {
        console.warn(
            "Saved destination image lookup failed:",
            place.name,
            error
        );
    }
}

function getSavedLocation(place) {
    const address = place.address || {};

    return [
        address.city,
        address.state,
        address.country
    ].filter(Boolean).join(", ") || "Location unavailable";
}

function getSavedDate(value) {
    if (!value) return "";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) return "";

    return "Saved " + date.toLocaleDateString();
}

function getSavedCSRFToken() {
    const cookie = document.cookie
        .split("; ")
        .find(row => row.startsWith("csrftoken="));

    return cookie
        ? decodeURIComponent(cookie.split("=")[1])
        : "";
}

function showSavedMessage(message, success = false) {
    savedMessage.textContent = message;
    savedMessage.classList.toggle("success", success);
    savedMessage.hidden = false;
}

function renderSavedPlaces(records) {
    savedPlacesGrid.innerHTML = "";

    savedCount.textContent =
        `${records.length} saved destination${records.length === 1 ? "" : "s"}`;

    emptySavedState.hidden = records.length !== 0;
    savedPlacesGrid.hidden = records.length === 0;

    if (!records.length) return;

    records.forEach(record => {
        const place = record.place || {};

        const name = escapeSavedHTML(
            place.name || "Unnamed destination"
        );

        const category = escapeSavedHTML(
            place.subcategory ||
            place.category ||
            place.place_type ||
            "Destination"
        );

        const location = escapeSavedHTML(
            getSavedLocation(place)
        );

        const description = escapeSavedHTML(
            place.description ||
            place.details?.description ||
            "Discover this destination and add it to your next journey."
        );

        const imageURL = getSavedImage(place);

        const card = document.createElement("article");
        card.className = "saved-card";

        card.innerHTML = `
            <div class="saved-card-image">
                ${
                    imageURL
                        ? `<img src="${escapeSavedHTML(imageURL)}"
                               alt="${name}"
                               loading="lazy">`
                        : `<div class="saved-image-placeholder">✦</div>`
                }

                <span class="saved-heart">♥</span>
            </div>

            <div class="saved-card-content">
                <span class="saved-category">${category}</span>

                <h3>${name}</h3>

                <p class="saved-location">
                    ⌖ ${location}
                </p>

                <p class="saved-description">
                    ${description}
                </p>

                <div class="saved-card-actions">

                    <span class="saved-date">
                        ${escapeSavedHTML(getSavedDate(record.saved_at))}
                    </span>

                    <button
                        type="button"
                        class="remove-saved-button"
                        data-saved-id="${escapeSavedHTML(record.saved_place_id)}"
                    >
                        Remove ♥
                    </button>

                </div>
            </div>
        `;

        const image = card.querySelector("img");

        if (image) {
            image.addEventListener("error", () => {
                const container = image.parentElement;

                image.remove();

                const fallback = document.createElement("div");

                fallback.className = "saved-image-placeholder";
                fallback.textContent = "✦";

                container.prepend(fallback);

            }, { once: true });
        }

        const removeButton = card.querySelector(
            ".remove-saved-button"
        );

        removeButton.addEventListener("click", () => {
            removeSavedPlace(
                record.saved_place_id,
                removeButton
            );
        });

        savedPlacesGrid.appendChild(card);

        if (!imageURL) {
            loadSavedPlaceImage(place, card);
        }
    });
}

async function loadSavedPlaces() {
    try {
        const response = await fetch(
            "/places/api/saved-places/",
            {
                method: "GET",
                headers: {
                    "Accept": "application/json"
                },
                credentials: "same-origin"
            }
        );

        const result = await response.json();

        if (response.status === 401) {
            savedPlacesGrid.hidden = true;

            showSavedMessage(
                "Please log in to view your saved destinations."
            );

            return;
        }

        if (!response.ok || !result.success) {
            throw new Error(
                result.error || "Unable to load saved destinations."
            );
        }

        renderSavedPlaces(result.places || []);

    } catch (error) {
        savedPlacesGrid.innerHTML = "";

        savedCount.textContent = "Unable to load saved places";

        showSavedMessage(error.message);

        console.error("Saved places loading failed:", error);
    }
}

async function removeSavedPlace(savedPlaceId, button) {
    if (!confirm("Remove this destination from your saved places?")) {
        return;
    }

    button.disabled = true;
    button.textContent = "Removing...";

    try {
        const response = await fetch(
            "/places/api/remove-saved-place/",
            {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getSavedCSRFToken()
                },
                body: JSON.stringify({
                    saved_place_id: savedPlaceId
                })
            }
        );

        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(
                result.error || "Unable to remove destination."
            );
        }

        showSavedMessage(
            "Destination removed from your saved places.",
            true
        );

        await loadSavedPlaces();

    } catch (error) {
        button.disabled = false;
        button.textContent = "Remove ♥";

        showSavedMessage(error.message);
    }
}

document.addEventListener("DOMContentLoaded", loadSavedPlaces);