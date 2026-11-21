const savedPlaceIds = new Set();

function getExplorePlaceId(place) {
    return String(place.id || place.osm_id || "");
}

async function loadSavedPlaceIds() {
    try {
        const response = await fetch("/places/api/saved-places/");
        const result = await response.json();

        if (!response.ok || !result.success) {
            return;
        }

        savedPlaceIds.clear();

        (result.places || []).forEach(record => {
            const place = record.place || {};
            const id = getExplorePlaceId(place);

            if (id) {
                savedPlaceIds.add(id);
            }
        });

        updateExploreSaveButtons();

    } catch (error) {
        console.error("Could not load saved-place status:", error);
    }
}

function updateExploreSaveButtons() {
    document.querySelectorAll(".place-card").forEach(card => {
        const id = card.dataset.placeId;
        const button = card.querySelector(".save-place-button");

        if (id && button && savedPlaceIds.has(id)) {
            button.textContent = "♥ Saved";
            button.classList.add("saved");
            button.disabled = true;
        }
    });
}

/* =========================================
   TOURISMPLANNER - EXPLORE FUNCTIONALITY
   ========================================= */

const API_URL = "/places/api/explore/";
const PAGE_SIZE = 12;

let currentPage = 1;
let allFetchedPlaces = [];
let selectedLocalCategory = "";
let latestPlacesRequestId = 0;
let currentSubcategory = "";
let currentPlaceType = "";
let currentQuery = "";
let currentState = "";
let currentDistrict = "";
let currentStateCode = "";

let map;
let markersLayer;
let searchTimeout = null;

/* =========================================
   DOM ELEMENTS
   ========================================= */

const searchInput = document.getElementById("searchInput");
const searchButton = document.getElementById("searchButton");
const stateFilter = document.getElementById("stateFilter");
const districtFilter = document.getElementById("districtFilter");

const placesGrid = document.getElementById("placesGrid");
const loadingState = document.getElementById("loadingState");
const emptyState = document.getElementById("emptyState");
const errorState = document.getElementById("errorState");
const errorMessage = document.getElementById("errorMessage");

const resultsCount = document.getElementById("resultsCount");
const pagination = document.getElementById("pagination");

const resetFilters = document.getElementById("resetFilters");
const retryButton = document.getElementById("retryButton");

// loadLocationFilters();

/* =========================================
   MAP INITIALIZATION
   ========================================= */

    function initializeMap() {
        if (typeof L === "undefined") {
            console.error("Leaflet library was not loaded.");
            return;
        }

        map = L.map("exploreMap").setView(
            [11.2588, 75.7804],
            12
        );
        
        L.tileLayer(
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            {
                attribution:
                    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
                maxZoom: 19,
                referrerPolicy: "strict-origin-when-cross-origin"
            }
        ).addTo(map);

        markersLayer = L.featureGroup().addTo(map);
    }

    /* =========================================
    HTML SAFETY
    ========================================= */

    function escapeHTML(value) {
        return String(value ?? "").replace(/[&<>"']/g, character => {
            const entities = {
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#039;"
            };

            return entities[character];
        });
    }

    /* =========================================
    CATEGORY LABELS
    ========================================= */

    function getCategoryLabel(place) {
        const subcategory = place.subcategory || place.place_type || "place";

        return subcategory
            .replaceAll("_", " ")
            .replace(/\b\w/g, character => character.toUpperCase());
    }

/* =========================================
   LOADING AND ERROR STATES
   ========================================= */

function showLoading() {
    loadingState.hidden = false;
    placesGrid.innerHTML = "";
    emptyState.hidden = true;
    errorState.hidden = true;
    pagination.innerHTML = "";
}

function hideLoading() {
    loadingState.hidden = true;
}

function showError(message) {
    hideLoading();

    placesGrid.innerHTML = "";
    emptyState.hidden = true;
    errorState.hidden = false;

    errorMessage.textContent = message;
    resultsCount.textContent = "Unable to load destinations";
}

/* =========================================
   FETCH PLACES FROM DJANGO API
   ========================================= */

function getLocalCategory(place) {
    const values = [
        place.category,
        place.subcategory,
        place.place_type,
        place.tourism_details?.tourism,
        place.tags?.tourism,
        place.tags?.amenity,
        place.tags?.historic,
        ...(Array.isArray(place.tags) ? place.tags : [])
    ].filter(Boolean).map(value => String(value).toLowerCase().replaceAll(" ", "_"));

    if (values.some(value => ["hotel", "hostel", "guest_house", "motel", "accommodation"].includes(value))) return "hotel";
    if (values.some(value => ["restaurant", "fast_food", "food_court"].includes(value))) return "restaurant";
    if (values.some(value => ["cafe", "coffee_shop"].includes(value))) return "cafe";
    if (values.some(value => ["museum"].includes(value))) return "museum";
    if (values.some(value => ["aquarium"].includes(value))) return "aquarium";
    if (values.some(value => ["artwork", "gallery", "arts_centre"].includes(value))) return "artwork";
    if (values.some(value => ["historic", "historic_site", "monument", "memorial", "castle", "archaeological_site"].includes(value))) return "historic";
    if (values.some(value => ["attraction", "viewpoint", "zoo", "theme_park", "attraction"].includes(value))) return "attraction";
    return "other";
}

function getLocallyFilteredPlaces() {
    if (!selectedLocalCategory) return allFetchedPlaces;
    return allFetchedPlaces.filter(place => {
        const group = getLocalCategory(place);
        if (selectedLocalCategory === "historic") return group === "historic";
        return group === selectedLocalCategory;
    });
}

function renderCurrentLocalPage() {
    const filtered = getLocallyFilteredPlaces();
    const total = filtered.length;
    const totalPages = Math.ceil(total / PAGE_SIZE);
    currentPage = Math.max(1, Math.min(currentPage, totalPages || 1));
    const start = (currentPage - 1) * PAGE_SIZE;
    const pagePlaces = filtered.slice(start, start + PAGE_SIZE);

    renderPlaces(pagePlaces);
    renderMarkers(pagePlaces);
    renderPagination({
        current_page: currentPage,
        page_size: PAGE_SIZE,
        total_count: total,
        total_pages: totalPages,
        has_previous: currentPage > 1,
        has_next: currentPage < totalPages
    });

    resultsCount.textContent = `${total} destinations found`;
    emptyState.hidden = pagePlaces.length !== 0;
    if (!pagePlaces.length) resultsCount.textContent = "No destinations found";
}

async function fetchPlaces() {
    const requestId = ++latestPlacesRequestId;
    showLoading();

    const params = new URLSearchParams();
    // Fetch all pages from the selected district. Category filtering is local.
    params.set("page", "1");
    params.set("page_size", "100");
    if (currentQuery) params.set("q", currentQuery);
    if (currentState) params.set("state", currentState);
    if (currentDistrict) params.set("district", currentDistrict);

    try {
        let collected = [];
        let page = 1;
        let totalPages = 1;

        do {
            params.set("page", String(page));
            const response = await fetch(`${API_URL}?${params.toString()}`, {
                method: "GET",
                headers: { "Accept": "application/json" }
            });
            if (!response.ok) throw new Error(`Server returned HTTP ${response.status}`);
            const result = await response.json();
            if (!result.success) throw new Error(result.error || "Unable to fetch places.");
            if (requestId !== latestPlacesRequestId) return;

            collected = collected.concat(result.data || []);
            totalPages = result.pagination?.total_pages || 0;
            page += 1;
        } while (page <= totalPages);

        if (requestId !== latestPlacesRequestId) return;
        allFetchedPlaces = collected;
        currentPage = 1;
        renderCurrentLocalPage();
        console.info(`Explore loaded ${allFetchedPlaces.length} MongoDB records before local category filtering.`);

    } catch (error) {
        if (requestId !== latestPlacesRequestId) return;
        console.error("Explore API error:", error);
        showError("We couldn't retrieve destinations. Please check your connection and try again.");
    } finally {
        if (requestId === latestPlacesRequestId) hideLoading();
    }
}

// =========================================
// IMAGE AND DESTINATION HELPERS
// =========================================

function getSafeCommonsImage(image) {
    if (!image || typeof image.url !== "string") {
        return null;
    }

    try {
        const url = new URL(image.url);
        return url.protocol === "https:" ? url.href : null;
    } catch {
        return null;
    }
}

function getSafeCommonsSource(image) {
    if (!image || typeof image.source_url !== "string") {
        return null;
    }

    try {
        const url = new URL(image.source_url);
        return url.protocol === "https:" ? url.href : null;
    } catch {
        return null;
    }
}

function getPlaceDescription(place) {
    const description = place.description;

    if (
        typeof description === "string" &&
        description.trim()
    ) {
        return description.trim();
    }

    return "Explore this destination and discover what makes it special.";
}

function getTourismDetails(place) {
    const details = place.tourism_details;

    return details && typeof details === "object"
        ? details
        : {};
}

function getPlaceMetadata(place) {
    const details = getTourismDetails(place);

    const metadata = [];

    if (details.opening_hours) {
        metadata.push({
            label: "Opening hours",
            value: details.opening_hours
        });
    }

    if (details.fee) {
        const fee = String(details.fee).toLowerCase();

        let feeText = details.fee;

        if (fee === "yes") {
            feeText = "Paid entry";
        } else if (fee === "no") {
            feeText = "Free entry";
        }

        metadata.push({
            label: "Entry",
            value: feeText
        });
    }

    if (details.wheelchair) {
        const wheelchair = String(
            details.wheelchair
        ).toLowerCase();

        let accessibility = details.wheelchair;

        if (wheelchair === "yes") {
            accessibility = "Wheelchair accessible";
        } else if (wheelchair === "no") {
            accessibility = "Not wheelchair accessible";
        }

        metadata.push({
            label: "Accessibility",
            value: accessibility
        });
    }

    return metadata;
}

async function loadPlaceImage(place, card) {
    const params = new URLSearchParams({
        id: place.source?.osm_id || place.osm_id || place.id || "",
        name: place.name || "",
        city: place.address?.city || "",
        state: place.address?.state || ""
    });

    try {
        const response = await fetch(
            `/places/api/place-image/?${params.toString()}`
        );

        if (!response.ok) return;

        const result = await response.json();
        const image = result.images?.[0];

        if (!image) return;

        const imageURL = getSafeCommonsImage(image);

        if (!imageURL || !card.isConnected) return;

        const imageContainer = card.querySelector(".place-image");

        if (!imageContainer || imageContainer.querySelector("img")) return;

        const img = document.createElement("img");

        img.src = imageURL;
        img.alt = place.name || "Destination photograph";
        img.loading = "lazy";
        img.referrerPolicy = "no-referrer";

        img.addEventListener("error", () => img.remove(), {
            once: true
        });

        const placeholder = imageContainer.querySelector(
            ".place-placeholder"
        );

        if (placeholder) {
            placeholder.remove();
        }

        imageContainer.prepend(img);

        const source = getSafeCommonsSource(image);

        if (source) {
            const credit = document.createElement("div");
            credit.className = "image-credit";

            const link = document.createElement("a");
            link.href = source;
            link.target = "_blank";
            link.rel = "noopener noreferrer";

            link.href = source;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent =
                `${image.artist || "Unknown creator"} · ${image.license || "Licence details"}`;

            credit.appendChild(link);

            const info = card.querySelector(".place-info");
            const footer = info?.querySelector(".place-card-footer");

            if (footer) {
                info.insertBefore(credit, footer);
            }
        }

    } catch (error) {
        console.warn("Image loading failed:", place.name, error);
    }
}



// =========================================
// DESTINATION DETAILS MODAL
// =========================================

const detailsModal = document.getElementById("placeDetailsModal");

function closePlaceDetails() {
    detailsModal.hidden = true;
    document.body.style.overflow = "";
}



function getTripCSRFToken() {
    const cookie = document.cookie
        .split("; ")
        .find(row => row.startsWith("csrftoken="));

    return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}


async function saveDestination(place, button) {
    const originalText = button.textContent;

    button.disabled = true;
    button.textContent = "Saving...";

    try {
        const response = await fetch("/places/api/save-place/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getTripCSRFToken()
            },
            body: JSON.stringify({ place })
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.error || "Unable to save destination.");
        }

        // Update saved-place tracking.
        const placeId = getExplorePlaceId(place);

        if (placeId) {
            savedPlaceIds.add(placeId);
        }

        // Update all matching Explore cards.
        updateExploreSaveButtons();

        button.textContent = "♥ Saved";
        button.classList.add("saved");
        button.disabled = true;

    } catch (error) {
        alert(error.message);
        button.textContent = originalText;
        button.disabled = false;
    }
}

async function openAddToTripModal(place) {
    let trips;

    const urlParams = new URLSearchParams(window.location.search);
    const preferredTripId = urlParams.get("trip_id");
    const preferredDay = urlParams.get("day");

    // Fetch the user's trips
    try {
        const response = await fetch("/trips/api/list/");
        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.error || "Unable to load your trips.");
        }

        trips = result.trips || [];

    } catch (error) {
        alert(error.message);
        return;
    }

    // Remove an existing modal
    const existingModal = document.getElementById("addToTripModal");
    if (existingModal) existingModal.remove();

    const modal = document.createElement("div");
    modal.id = "addToTripModal";
    modal.className = "trip-modal-overlay";

    if (trips.length === 0) {
        modal.innerHTML = `
            <div class="trip-modal">
                <button class="trip-modal-close" type="button">&times;</button>
                <h2>No trips found</h2>
                <p>Create a trip before adding destinations.</p>
                <a href="/trips/" class="trip-modal-submit">
                    Create a Trip
                </a>
            </div>
        `;
    } else {
        modal.innerHTML = `
            <div class="trip-modal">
                <button class="trip-modal-close" type="button">&times;</button>

                <h2>Add to your itinerary</h2>
                <p class="trip-modal-place">${escapeHTML(place.name)}</p>

                <label for="selectTrip">Select Trip</label>
                <select id="selectTrip">
                    ${trips.map(trip => `
                        <option value="${escapeHTML(trip._id)}">
                            ${escapeHTML(trip.title)}
                        </option>
                    `).join("")}
                </select>

                <label for="selectTripDay">Select Day</label>
                <select id="selectTripDay"></select>

                <p id="tripModalMessage"></p>

                <button id="confirmAddToTrip" class="trip-modal-submit">
                    Add Destination
                </button>
            </div>
        `;
    }

    document.body.appendChild(modal);

    const closeModal = () => modal.remove();

    modal.querySelector(".trip-modal-close")
        .addEventListener("click", closeModal);

    modal.addEventListener("click", event => {
        if (event.target === modal) closeModal();
    });

    if (trips.length === 0) return;

    const tripSelect = modal.querySelector("#selectTrip");
    const daySelect = modal.querySelector("#selectTripDay");
    const message = modal.querySelector("#tripModalMessage");
    const submitButton = modal.querySelector("#confirmAddToTrip");

    // Automatically select the trip from the itinerary URL
    if (
        preferredTripId &&
        trips.some(trip => trip._id === preferredTripId)
    ) {
        tripSelect.value = preferredTripId;
    }

    // Populate itinerary days
    function updateDays() {
        const selectedTrip = trips.find(
            trip => trip._id === tripSelect.value
        );

        daySelect.innerHTML = "";

        (selectedTrip?.days || []).forEach(day => {
            const option = document.createElement("option");

            option.value = day.day_number;
            option.textContent = `Day ${day.day_number} — ${day.date}`;

            daySelect.appendChild(option);
        });

        // Automatically select the day from the itinerary URL
        if (
            preferredDay &&
            daySelect.querySelector(
                `option[value="${CSS.escape(preferredDay)}"]`
            )
        ) {
            daySelect.value = preferredDay;
        }

        submitButton.disabled = daySelect.options.length === 0;

        message.textContent = daySelect.options.length === 0
            ? "No itinerary days available."
            : "";
    }

    tripSelect.addEventListener("change", updateDays);
    updateDays();

    // Save destination to the selected trip and day
    submitButton.addEventListener("click", async () => {
        const tripId = tripSelect.value;
        const dayNumber = Number(daySelect.value);

        if (!tripId || !dayNumber) {
            message.textContent = "Please select a trip and day.";
            return;
        }

        submitButton.disabled = true;
        submitButton.textContent = "Adding...";

        try {
            const response = await fetch("/trips/api/add-place/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getTripCSRFToken()
                },
                body: JSON.stringify({
                    trip_id: tripId,
                    day_number: dayNumber,
                    place: place
                })
            });

            const result = await response.json();

            if (!response.ok || !result.success) {
                throw new Error(
                    result.error || "Unable to add destination."
                );
            }

            message.textContent = "Destination added successfully!";
            message.className = "trip-modal-success";
            submitButton.textContent = "Added successfully";

            // Return to the updated trip itinerary
            setTimeout(() => {
                window.location.href = `/trips/${tripId}/`;
            }, 900);

        } catch (error) {
            message.textContent = error.message;
            message.className = "trip-modal-error";

            submitButton.disabled = false;
            submitButton.textContent = "Add Destination";
        }
    });
}


async function openPlaceDetails(place) {
    detailsModal.hidden = false;
    document.body.style.overflow = "hidden";

    document.getElementById("detailsName").textContent = place.name || "";
    document.getElementById("detailsCategory").textContent =
        getCategoryLabel(place);

    const address = place.address || {};

    document.getElementById("detailsLocation").textContent = [
        address.city,
        address.district,
        address.state,
        address.country
    ].filter(Boolean).join(", ") || "Location unavailable";

    document.getElementById("detailsDescription").textContent =
        getPlaceDescription(place);

    const metadata = getPlaceMetadata(place);

    document.getElementById("detailsMetadata").innerHTML =
        metadata.length
            ? metadata.map(item => `
                <p>
                    <strong>${escapeHTML(item.label)}:</strong>
                    ${escapeHTML(item.value)}
                </p>
            `).join("")
            : "<p>Additional visitor information is not available.</p>";

    const osmLink = document.getElementById("detailsOSMLink");
    const sourceURL = place.source?.source_url;

    try {
        const parsed = new URL(sourceURL);

        if (
            parsed.protocol === "https:" &&
            parsed.hostname === "www.openstreetmap.org"
        ) {
            osmLink.href = parsed.href;
            osmLink.hidden = false;
        } else {
            osmLink.hidden = true;
        }
    } catch {
        osmLink.hidden = true;
    }

    const gallery = document.getElementById("detailsGallery");

    gallery.innerHTML = `
        <div class="place-placeholder">
            <span>✦</span>
            <small>Loading photographs...</small>
        </div>
    `;

    // First use images already available on the place.
    let images = Array.isArray(place.images) ? place.images : [];

    // Fetch additional images separately if necessary.
    if (images.length === 0) {
        try {
            const params = new URLSearchParams({
                id: place.source?.osm_id || place.osm_id || place.id || "",
                name: place.name || "",
                city: address.city || "",
                state: address.state || ""
            });

            const response = await fetch(
                `/places/api/place-image/?${params.toString()}`
            );

            if (response.ok) {
                const result = await response.json();
                images = result.images || [];
            }
        } catch (error) {
            console.warn("Gallery image lookup failed:", error);

        }
    }

    // Ignore an outdated response if the modal was closed.
    if (detailsModal.hidden) return;

    gallery.innerHTML = "";

    const validImages = images.filter(image =>
        getSafeCommonsImage(image)
    );

    if (validImages.length === 0) {
        gallery.innerHTML = `
            <div class="place-placeholder">
                <span>✦</span>
                <small>No photographs available yet</small>
            </div>
        `;
    } else {
        validImages.slice(0, 3).forEach(image => {
            const wrapper = document.createElement("div");
            wrapper.style.minWidth = "100%";

            const img = document.createElement("img");
            img.src = getSafeCommonsImage(image);
            img.alt = place.name || "Destination photograph";
            img.loading = "lazy";

            img.addEventListener("error", () => {
                wrapper.remove();

                if (!gallery.querySelector("img")) {
                    gallery.innerHTML = `
                        <div class="place-placeholder">
                            <span>✦</span>
                            <small>Photograph unavailable</small>
                        </div>
                    `;
                }
            }, { once: true });

            wrapper.appendChild(img);

            if (image.artist || image.license) {
                const credit = document.createElement("small");
                credit.textContent =
                    `${image.artist || "Unknown creator"} · ${image.license || ""}`;
                wrapper.appendChild(credit);
            }

            gallery.appendChild(wrapper);
        });
    }

    const detailsActions = document.querySelector(".details-actions");

let saveButton = document.getElementById("saveDetailsPlaceButton");

if (!saveButton) {
    saveButton = document.createElement("button");
    saveButton.id = "saveDetailsPlaceButton";
    saveButton.type = "button";
    saveButton.className = "save-place-button";
    saveButton.textContent = "♡ Save";

    detailsActions.insertBefore(
        saveButton,
        document.getElementById("addToTripButton")
    );
}

saveButton.disabled = false;
saveButton.textContent = "♡ Save";
saveButton.classList.remove("saved");

saveButton.onclick = () => saveDestination(place, saveButton);

document.getElementById("addToTripButton").onclick = () => {
    openAddToTripModal(place);
};
}

// Modal close actions
document.getElementById("closeDetailsModal")
    .addEventListener("click", closePlaceDetails);

document.getElementById("detailsOverlay")
    .addEventListener("click", closePlaceDetails);

document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !detailsModal.hidden) {
        closePlaceDetails();
    }
});


// =========================================
// RENDER PLACE CARDS
// =========================================



function renderPlaces(places) {
    placesGrid.innerHTML = "";

    if (!Array.isArray(places) || places.length === 0) {
        return;
    }

    const primaryPlace = places.find(place => place.is_primary);
    const nearbyPlaces = places.filter(place => !place.is_primary);

    // Determine the correct display group using all available
    // category fields in the MongoDB records.
    function getPlaceGroup(place) {
        const values = [
            place.category,
            place.subcategory,
            place.place_type,
            place.tourism_details?.tourism,
            place.tags?.tourism,
            place.tags?.amenity,
            place.tags?.historic
        ]
            .filter(Boolean)
            .map(value =>
                String(value).toLowerCase().replaceAll(" ", "_")
            );

        if (values.some(value =>
            ["hotel", "hostel", "guest_house", "motel", "accommodation"]
                .includes(value)
        )) {
            return "hotel";
        }

        if (values.includes("restaurant")) {
            return "restaurant";
        }

        if (values.includes("cafe")) {
            return "cafe";
        }

        if (values.some(value => [
            "attraction",
            "historic",
            "historic_site",
            "museum",
            "aquarium",
            "artwork",
            "viewpoint",
            "monument",
            "memorial",
            "gallery",
            "zoo",
            "theme_park",
            "archaeological_site",
            "castle"
        ].includes(value))) {
            return "attraction";
        }

        return "other";
    }

    const groups = [
        {
            key: "attraction",
            title: "Nearby Attractions"
        },
        {
            key: "hotel",
            title: "Nearby Hotels"
        },
        {
            key: "restaurant",
            title: "Nearby Restaurants"
        },
        {
            key: "cafe",
            title: "Nearby Cafés"
        },
        {
            key: "other",
            title: "Other Places"
        }
    ];

    // Group every record. No destination is discarded.
    const groupedPlaces = {
        attraction: [],
        hotel: [],
        restaurant: [],
        cafe: [],
        other: []
    };

    nearbyPlaces.forEach(place => {
        const group = getPlaceGroup(place);
        groupedPlaces[group].push(place);
    });

    const orderedPlaces = [
        ...(primaryPlace ? [primaryPlace] : []),
        ...groups.flatMap(group => groupedPlaces[group.key])
    ];

    let currentGroup = "";

    orderedPlaces.forEach(place => {
        const group = primaryPlace === place
            ? "primary"
            : getPlaceGroup(place);

        // Add section headings.
        if (group !== currentGroup) {
            currentGroup = group;

            const heading = document.createElement("h2");
            heading.className = "place-section-heading";

            if (group === "primary") {
                heading.textContent = "Main Destination";
            } else {
                heading.textContent =
                    groups.find(item => item.key === group)?.title ||
                    "Other Places";
            }

            placesGrid.appendChild(heading);
        }

        const card = document.createElement("article");
        card.className = "place-card";

        card.dataset.placeId = getExplorePlaceId(place);

        const name = escapeHTML(place.name || "Unnamed destination");
        const category = escapeHTML(getCategoryLabel(place));

        const distanceHTML = place.is_primary
            ? `<span class="place-distance primary-distance">Exact destination</span>`
            : Number.isFinite(place.distance_km)
                ? `<span class="place-distance">${place.distance_km.toFixed(2)} km away</span>`
                : "";

        const address = place.address || {};

        const locationParts = [
            address.city,
            address.state,
            address.country
        ].filter(Boolean);

        const locationText = locationParts.length
            ? locationParts.join(", ")
            : "Location information unavailable";

        const description = escapeHTML(getPlaceDescription(place));

        const coordinates = place.location?.coordinates;

        const hasCoordinates =
            Array.isArray(coordinates) &&
            coordinates.length === 2 &&
            coordinates.every(Number.isFinite) &&
            coordinates[0] >= -180 &&
            coordinates[0] <= 180 &&
            coordinates[1] >= -90 &&
            coordinates[1] <= 90;

        // Destination photograph.
        const images = Array.isArray(place.images)
            ? place.images
            : [];

        const selectedImage = images.find(image =>
            getSafeCommonsImage(image)
        );

        let imageHTML = `
            <div class="place-placeholder">
                <span>✦</span>
                <small>Photo coming soon</small>
            </div>
        `;

        let imageCreditHTML = "";

        if (selectedImage) {
            const imageURL = getSafeCommonsImage(selectedImage);
            const imageSource = getSafeCommonsSource(selectedImage);

            const artist = selectedImage.artist
                ? escapeHTML(selectedImage.artist)
                : "Unknown creator";

            const license = selectedImage.license
                ? escapeHTML(selectedImage.license)
                : "License information unavailable";

            imageHTML = `
                <img
                    src="${escapeHTML(imageURL)}"
                    alt="${name}"
                    loading="lazy"
                    referrerpolicy="no-referrer"
                >
            `;

            if (imageSource) {
                imageCreditHTML = `
                    <div class="image-credit">
                        Photo: ${artist}
                        <span> · </span>
                        <a
                            href="${escapeHTML(imageSource)}"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            ${license}
                        </a>
                    </div>
                `;
            } else {
                imageCreditHTML = `
                    <div class="image-credit">
                        Photo: ${artist} · ${license}
                    </div>
                `;
            }
        }

        // Additional destination information.
        const metadata = getPlaceMetadata(place);

        const metadataHTML = metadata.length
            ? `

                        <div class="place-metadata">
                    ${metadata.map(item => `
                        <div class="metadata-item">
                            <span>${escapeHTML(item.label)}</span>
                            <strong>${escapeHTML(item.value)}</strong>
                        </div>
                    `).join("")}
                </div>
            `
            : "";

        // OpenStreetMap source link.
        const sourceURL = place.source?.source_url;
        let sourceLink = "";

        if (sourceURL) {
            try {
                const parsedURL = new URL(sourceURL);

                if (
                    parsedURL.protocol === "https:" &&
                    parsedURL.hostname === "www.openstreetmap.org"
                ) {
                    sourceLink = `
                        <a
                            class="view-place-button"
                            href="${escapeHTML(parsedURL.href)}"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            View on OSM ↗
                        </a>
                    `;
                }
            } catch (error) {
                console.warn("Invalid place source URL:", error);
            }
        }

        // Google Maps directions link.
        const directionsLink = hasCoordinates
            ? `
                <a
                    class="directions-button"
                    href="https://www.google.com/maps/dir/?api=1&destination=${coordinates[1]},${coordinates[0]}"
                    target="_blank"
                    rel="noopener noreferrer"
                >
                    Get Directions ↗
                </a>
            `
            : "";

        // Build destination card.
        card.innerHTML = `
            <div class="place-image">
                ${imageHTML}
                <span class="place-category">${category}</span>
            </div>

            <div class="place-info">
                <h3>${name}</h3>

                ${distanceHTML}

                <p class="place-location">
                    <span>⌖</span>
                    ${escapeHTML(locationText)}
                </p>

                <p class="place-description">
                    ${description}
                </p>

                ${metadataHTML}
                ${imageCreditHTML}

                <div class="place-card-footer">
                    <span>
                        ${hasCoordinates
                            ? "Map location available"
                            : "Location unavailable"}
                    </span>

                    <div class="place-footer-actions">
                        ${directionsLink}

                        <button
                            type="button"
                            class="save-place-button"
                        >
                            ♡ Save
                        </button>

                        ${sourceLink}
                    </div>
                </div>
            </div>
        `;

        // Compact weather preview.
        if (hasCoordinates) {
            const weatherWidget = document.createElement("div");
            weatherWidget.className = "explore-weather";

            weatherWidget.innerHTML = `
                <div class="explore-weather-summary">
                    <span class="weather-loading">
                        🌤️ Loading weather...
                    </span>
                </div>

                <button type="button" class="explore-weather-toggle">
                    View weather
                </button>

                <div class="explore-weather-details" hidden></div>
            `;

            weatherWidget.addEventListener("click", event => {
                event.stopPropagation();
            });

            card.querySelector(".place-info").appendChild(weatherWidget);

            loadExploreWeather(
                coordinates[1],
                coordinates[0],
                weatherWidget
            );
        }

        // Image fallback.
        const imageElement = card.querySelector(".place-image img");

        if (imageElement) {
            imageElement.addEventListener("error", () => {
                const container = imageElement.parentElement;
                imageElement.remove();

                const fallback = document.createElement("div");
                fallback.className = "place-placeholder";
                fallback.innerHTML = `
                    <span>✦</span>
                    <small>Image unavailable</small>
                `;

                container.prepend(fallback);
            }, { once: true });
        }

        // Save destination.
        const saveButton = card.querySelector(".save-place-button");

        if (savedPlaceIds.has(getExplorePlaceId(place))) {
            saveButton.textContent = "♥ Saved";
            saveButton.classList.add("saved");
            saveButton.disabled = true;
        }

        saveButton.addEventListener("click", event => {
            event.stopPropagation();
            saveDestination(place, saveButton);
        });

        // Map and destination details interaction.
        if (hasCoordinates) {
            card.addEventListener("click", event => {
                if (event.target.closest("a, button")) {
                    return;
                }

                focusPlace(place);
                openPlaceDetails(place);
            });

            card.style.cursor = "pointer";
        }

        placesGrid.appendChild(card);

        // Load additional destination images.
        loadPlaceImage(place, card);
    });
}


/* =========================================
   LEAFLET MAP MARKERS
   ========================================= */

function renderMarkers(places) {
    if (!map || !markersLayer) {
        return;
    }

    markersLayer.clearLayers();

    const validPlaces = places.filter(place => {
        const coordinates = place.location?.coordinates;

        return (
            Array.isArray(coordinates) &&
            coordinates.length === 2 &&
            coordinates.every(Number.isFinite) &&
            coordinates[0] >= -180 &&
            coordinates[0] <= 180 &&
            coordinates[1] >= -90 &&
            coordinates[1] <= 90
        );
    });

    validPlaces.forEach(place => {
        const coordinates = place.location.coordinates;

        const longitude = coordinates[0];
        const latitude = coordinates[1];

        const marker = L.marker([latitude, longitude]);

        marker.bindPopup(`
            <div>
                <div class="map-popup-title">
                    ${escapeHTML(place.name)}
                </div>

                <div class="map-popup-category">
                    ${escapeHTML(getCategoryLabel(place))}
                </div>
            </div>
        `);

        marker.addTo(markersLayer);
    });

    if (validPlaces.length > 0) {
        map.fitBounds(markersLayer.getBounds(), {
            padding: [30, 30],
            maxZoom: 14
        });
    }
}


/* =========================================
   FOCUS ON A PLACE
   ========================================= */

function focusPlace(place) {
    if (!map || !place.location?.coordinates) {
        return;
    }

    const [longitude, latitude] = place.location.coordinates;

    map.setView(
        [latitude, longitude],
        16,
        { animate: true }
    );

    markersLayer.eachLayer(marker => {
        const position = marker.getLatLng();

        if (
            Math.abs(position.lat - latitude) < 0.000001 &&
            Math.abs(position.lng - longitude) < 0.000001
        ) {
            marker.openPopup();
        }
    });
}


/* =========================================
   PAGINATION
   ========================================= */

function renderPagination(pageInfo) {
    pagination.innerHTML = "";

    if (!pageInfo || pageInfo.total_pages <= 1) {
        return;
    }

    const previousButton = document.createElement("button");

    previousButton.className = "page-button";
    previousButton.textContent = "‹";
    previousButton.disabled = !pageInfo.has_previous;

    previousButton.addEventListener("click", () => {
        if (pageInfo.has_previous) {
            currentPage--;
            renderCurrentLocalPage();
        }
    });

    pagination.appendChild(previousButton);

    for (let page = 1; page <= pageInfo.total_pages; page++) {
        const pageButton = document.createElement("button");

        pageButton.className = "page-button";

        if (page === pageInfo.current_page) {
            pageButton.classList.add("active");
        }

        pageButton.textContent = page;

        pageButton.addEventListener("click", () => {
            currentPage = page;
            renderCurrentLocalPage();
        });

        pagination.appendChild(pageButton);
    }

    const nextButton = document.createElement("button");

    nextButton.className = "page-button";
    nextButton.textContent = "›";
    nextButton.disabled = !pageInfo.has_next;

    nextButton.addEventListener("click", () => {
        if (pageInfo.has_next) {
            currentPage++;
            renderCurrentLocalPage();
        }
    });

    pagination.appendChild(nextButton);
}


/* =========================================
   SEARCH
   ========================================= */
function performSearch() {
    currentQuery = searchInput.value.trim();
    currentPage = 1;

    fetchPlaces();
}

searchButton.addEventListener("click", performSearch);

searchInput.addEventListener("keydown", event => {
    if (event.key === "Enter") {
        performSearch();
    }
});

// Live search with a short debounce.
searchInput.addEventListener("input", () => {
    clearTimeout(searchTimeout);

    searchTimeout = setTimeout(() => {
        performSearch();
    }, 400);
});


/* =========================================
   CATEGORY FILTERS
   ========================================= */


document.querySelectorAll(".filter-chip").forEach(button => {
    button.addEventListener("click", () => {

        document.querySelectorAll(".filter-chip").forEach(chip => {
            chip.classList.remove("active");
        });

        button.classList.add("active");

        currentSubcategory = button.dataset.subcategory || "";
        currentPlaceType = "";
        selectedLocalCategory = button.dataset.category || currentSubcategory;
        currentPage = 1;
        renderCurrentLocalPage();
    });
});




/* =========================================
   STATE AND DISTRICT FILTERS
   ========================================= */

const LGD_API = "https://india-lgd-index-api.vercel.app/v1";

function formatLocationName(name) {
    return String(name || "")
        .toLowerCase()
        .replace(/\b\w/g, character => character.toUpperCase());
}

async function loadIndianStates() {
    if (!stateFilter || !districtFilter) {
        console.error("State or district dropdown is missing from explore.html.");
        return;
    }

    try {
        stateFilter.disabled = true;
        stateFilter.innerHTML = '<option value="">Loading states...</option>';

        const response = await fetch(`${LGD_API}/states`);
        if (!response.ok) {
            throw new Error(`State API returned HTTP ${response.status}`);
        }

        const result = await response.json();
        if (!result.success || !Array.isArray(result.data)) {
            throw new Error("Invalid state directory response.");
        }

        stateFilter.innerHTML = '<option value="">All states and UTs</option>';

        result.data.forEach(state => {
            const option = new Option(
                formatLocationName(state.name),
                state.name
            );
            option.dataset.code = state.code;
            stateFilter.add(option);
        });

        // Always start unfiltered so Django returns the existing regional cache.
        stateFilter.value = "";
        currentState = "";
        currentStateCode = "";
        currentDistrict = "";

        districtFilter.innerHTML = '<option value="">All districts</option>';
        districtFilter.value = "";
        districtFilter.disabled = true;
        stateFilter.disabled = false;

        console.info(`Loaded ${result.data.length} Indian states and UTs.`);
    } catch (error) {
        console.error("State directory error:", error);
        stateFilter.innerHTML = '<option value="">Unable to load states</option>';
        stateFilter.disabled = false;
        districtFilter.innerHTML = '<option value="">All districts</option>';
        districtFilter.disabled = true;
    }
}

async function loadIndianDistricts(stateCode) {
    if (!districtFilter) return;

    try {
        districtFilter.disabled = true;
        districtFilter.innerHTML = '<option value="">Loading districts...</option>';

        const response = await fetch(
            `${LGD_API}/districts?state=${encodeURIComponent(stateCode)}`
        );
        if (!response.ok) {
            throw new Error(`District API returned HTTP ${response.status}`);
        }

        const result = await response.json();
        if (!result.success || !Array.isArray(result.data)) {
            throw new Error("Invalid district directory response.");
        }

        districtFilter.innerHTML = '<option value="">All districts</option>';
        result.data.forEach(district => {
            districtFilter.add(
                new Option(
                    formatLocationName(district.name),
                    district.name
                )
            );
        });

        districtFilter.value = "";
        districtFilter.disabled = false;
        console.info(`Loaded ${result.data.length} districts for state ${stateCode}.`);
    } catch (error) {
        console.error("District directory error:", error);
        districtFilter.innerHTML = '<option value="">Unable to load districts</option>';
        districtFilter.disabled = true;
    }
}

// Exactly one state-change listener.
if (stateFilter) {
    stateFilter.addEventListener("change", async () => {
        const selectedOption = stateFilter.options[stateFilter.selectedIndex];

        currentState = selectedOption?.value || "";
        currentStateCode = selectedOption?.dataset.code || "";
        currentDistrict = "";
        currentPage = 1;

        if (currentStateCode) {
            await loadIndianDistricts(currentStateCode);
        } else if (districtFilter) {
            districtFilter.innerHTML = '<option value="">All districts</option>';
            districtFilter.disabled = true;
        }

        fetchPlaces();
    });
}

// Exactly one district-change listener.
if (districtFilter) {
    districtFilter.addEventListener("change", () => {
        currentDistrict = districtFilter.value || "";
        currentPage = 1;
        fetchPlaces();
    });
}

/* =========================================
   RESET FILTERS
   ========================================= */

if (resetFilters) {
    resetFilters.addEventListener("click", () => {
        currentState = "";
        currentDistrict = "";
        currentStateCode = "";
        currentQuery = "";
        currentSubcategory = "";
        currentPlaceType = "";
        selectedLocalCategory = "";
        currentPage = 1;

        if (searchInput) searchInput.value = "";
        if (stateFilter) stateFilter.value = "";

        if (districtFilter) {
            districtFilter.innerHTML = '<option value="">All districts</option>';
            districtFilter.value = "";
            districtFilter.disabled = true;
        }

        document.querySelectorAll(".filter-chip").forEach(chip => {
            chip.classList.remove("active");
        });

        document.querySelector(
            '.filter-chip[data-subcategory=""]'
        )?.classList.add("active");

        // No location params are sent: backend returns the preloaded cache.
        fetchPlaces();
    });
}


/* =========================================
   RETRY
   ========================================= */

retryButton.addEventListener("click", fetchPlaces);


/* =========================================
   APPLICATION START
   ========================================= */

async function startExplorePage() {
    initializeMap();
    await loadIndianStates();
    fetchPlaces();
    loadSavedPlaceIds();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startExplorePage, { once: true });
} else {
    startExplorePage();
}


// Cache weather results to avoid repeated API requests.
const exploreWeatherCache = new Map();

async function loadExploreWeather(latitude, longitude, widget) {
    const summary = widget.querySelector(".explore-weather-summary");
    const details = widget.querySelector(".explore-weather-details");
    const toggle = widget.querySelector(".explore-weather-toggle");

    const cacheKey = `${latitude.toFixed(2)},${longitude.toFixed(2)}`;

    try {
        let weather = exploreWeatherCache.get(cacheKey);

        if (!weather) {
            const response = await fetch(
                `/places/api/weather/?latitude=${latitude}&longitude=${longitude}`
            );

            if (!response.ok) {
                throw new Error("Weather unavailable");
            }

            weather = await response.json();

            if (!weather.success) {
                throw new Error("Weather unavailable");
            }

            exploreWeatherCache.set(cacheKey, weather);
        }

        const current = weather.current || {};
        const code = current.weather_code;

        const descriptions = {
            0: ["Clear sky", "☀️"],
            1: ["Mainly clear", "🌤️"],
            2: ["Partly cloudy", "⛅"],
            3: ["Overcast", "☁️"],
            45: ["Fog", "🌫️"],
            48: ["Fog", "🌫️"],
            51: ["Light drizzle", "🌦️"],
            53: ["Drizzle", "🌦️"],
            55: ["Heavy drizzle", "🌧️"],
            61: ["Light rain", "🌧️"],
            63: ["Moderate rain", "🌧️"],
            65: ["Heavy rain", "🌧️"],
            71: ["Light snow", "🌨️"],
            73: ["Snow", "🌨️"],
            75: ["Heavy snow", "❄️"],
            80: ["Rain showers", "🌦️"],
            81: ["Rain showers", "🌧️"],
            82: ["Heavy showers", "⛈️"],
            95: ["Thunderstorm", "⛈️"],
            96: ["Thunderstorm with hail", "⛈️"],
            99: ["Severe thunderstorm", "⛈️"]
        };

        const isDay = current.is_day === 1;

        let condition =
            descriptions[code] || ["Weather available", "🌤️"];

        if (!isDay) {
            const nightIcons = {
                0: "🌙",
                1: "🌙",
                2: "☁️",
                3: "☁️"
            };

            if (nightIcons[code]) {
                condition = [condition[0], nightIcons[code]];
            }
        }

        const temperature = current.temperature_2m;

        summary.innerHTML = `
            <span>${condition[1]}</span>
            <strong>
                ${temperature !== undefined ? `${Math.round(temperature)}°C` : "--"}
            </strong>
            <span>${condition[0]}</span>
        `;

        details.innerHTML = `
            <p>Feels like: ${current.apparent_temperature ?? "--"}°C</p>
            <p>Humidity: ${current.relative_humidity_2m ?? "--"}%</p>
            <p>Wind: ${current.wind_speed_10m ?? "--"} km/h</p>
            <p>Today's high: ${weather.max_temperature ?? "--"}°C</p>
            <p>Today's low: ${weather.min_temperature ?? "--"}°C</p>
            <p>Rain probability: ${weather.rain_probability ?? "--"}%</p>
        `;

        toggle.addEventListener("click", () => {
            details.hidden = !details.hidden;

            toggle.textContent = details.hidden
                ? "View weather"
                : "Hide weather";
        });

    } catch (error) {
        summary.innerHTML =
            `<span>🌤️ Weather currently unavailable</span>`;

        toggle.hidden = true;
    }
}



// =========================================
// NEARBY PLACES — 5 KM WITH PAGINATION
// =========================================

document.addEventListener("DOMContentLoaded", () => {
    const section = document.getElementById("nearbyAttractionsSection");
    const status = document.getElementById("nearbyLocationStatus");
    const grid = document.getElementById("nearbyAttractionsGrid");

    if (!section || !status || !grid) {
        console.warn("Nearby Places HTML elements were not found.");
        return;
    }

    const PAGE_SIZE = 12;

    let nearbyPlaces = [];
    let activeCategory = "all";
    let currentNearbyPage = 1;

    const categoryNames = {
        all: "All Places",
        hotel: "Hotels",
        restaurant: "Restaurants",
        cafe: "Cafés",
        attraction: "Attractions",
        museum: "Museums",
        historic_site: "Historic Sites",
        art_culture: "Art & Culture"
    };

    // Create pagination container automatically.
    let pagination = document.getElementById("nearbyPagination");

    if (!pagination) {
        pagination = document.createElement("div");
        pagination.id = "nearbyPagination";
        pagination.className = "nearby-pagination";
        grid.insertAdjacentElement("afterend", pagination);
    }

    // Render nearby place cards.
    function renderNearbyPlaces() {
        const filteredPlaces = activeCategory === "all"
            ? nearbyPlaces
            : nearbyPlaces.filter(
                place => place.category === activeCategory
            );

        const totalPages = Math.ceil(filteredPlaces.length / PAGE_SIZE);

        currentNearbyPage = Math.max(
            1,
            Math.min(currentNearbyPage, totalPages || 1)
        );

        const startIndex = (currentNearbyPage - 1) * PAGE_SIZE;

        const pagePlaces = filteredPlaces.slice(
            startIndex,
            startIndex + PAGE_SIZE
        );

        grid.innerHTML = "";
        pagination.innerHTML = "";

        status.textContent =
            `${filteredPlaces.length} ${categoryNames[activeCategory]} found within 5 km.`;

        if (filteredPlaces.length === 0) {
            status.textContent =
                `0 ${categoryNames[activeCategory]} found within 5 km.`;

            const message = document.createElement("p");
            message.className = "nearby-empty-message";
            message.textContent = "No places found in this category.";

            grid.appendChild(message);
            return;
        }

        pagePlaces.forEach(place => {
            const card = document.createElement("article");
            card.className = "nearby-attraction-card";

            const name = document.createElement("h3");
            name.textContent = place.name || "Unnamed place";

            const category = document.createElement("span");
            category.className = "nearby-attraction-category";
            category.textContent =
                categoryNames[place.category] || place.category || "Place";

            const distance = document.createElement("p");
            distance.textContent =
                `${Number(place.distance_km).toFixed(2)} km away`;

            const address = document.createElement("p");
            address.textContent =
                place.address || "Address unavailable";

            card.append(name, category, distance, address);

            // Google Maps directions.
            if (
                Number.isFinite(Number(place.latitude)) &&
                Number.isFinite(Number(place.longitude))
            ) {
                const directions = document.createElement("a");

                directions.className = "directions-button";
                directions.textContent = "Get Directions ↗";

                directions.href =
                    `https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`;

                directions.target = "_blank";
                directions.rel = "noopener noreferrer";

                card.appendChild(directions);
            }

            grid.appendChild(card);
        });

        renderNearbyPagination(totalPages);
    }

    // Render numbered pagination.
    function renderNearbyPagination(totalPages) {
        pagination.innerHTML = "";

        if (totalPages <= 1) {
            return;
        }

        function createPageButton(label, page, options = {}) {
            const button = document.createElement("button");

            button.type = "button";
            button.className = "nearby-page-btn";
            button.textContent = label;

            if (options.active) {
                button.classList.add("active");
            }

            button.disabled = Boolean(options.disabled);

            button.addEventListener("click", () => {
                currentNearbyPage = page;
                renderNearbyPlaces();

                section.scrollIntoView({
                    behavior: "smooth",
                    block: "start"
                });
            });

            pagination.appendChild(button);
        }

        createPageButton(
            "‹",
            currentNearbyPage - 1,
            { disabled: currentNearbyPage === 1 }
        );

        for (let page = 1; page <= totalPages; page++) {
            createPageButton(
                String(page),
                page,
                { active: page === currentNearbyPage }
            );
        }

        createPageButton(
            "›",
            currentNearbyPage + 1,
            { disabled: currentNearbyPage === totalPages }
        );
    }

    // Category filter buttons.
    document.querySelectorAll(".nearby-category-tab").forEach(button => {
        button.addEventListener("click", () => {
            document.querySelectorAll(".nearby-category-tab")
                .forEach(tab => tab.classList.remove("active"));

            button.classList.add("active");

            activeCategory = button.dataset.nearbyCategory || "all";
            currentNearbyPage = 1;

            renderNearbyPlaces();
        });
    });

    // Get the user's current location.
    if (!navigator.geolocation) {
        status.textContent =
            "Your browser does not support location detection.";

        section.hidden = false;
        return;
    }

    status.textContent = "Finding nearby places...";

    navigator.geolocation.getCurrentPosition(
        async position => {
            const latitude = position.coords.latitude;
            const longitude = position.coords.longitude;

            try {
                const response = await fetch(
                    `/places/api/nearby-attractions/?latitude=${latitude}&longitude=${longitude}`
                );

                const data = await response.json();

                if (!response.ok || !data.success) {
                    throw new Error(
                        data.error || "Unable to load nearby places."
                    );
                }

                nearbyPlaces = data.results || [];
                currentNearbyPage = 1;

                section.hidden = false;

                renderNearbyPlaces();

                console.log(
                    "Explore nearby places loaded:",
                    nearbyPlaces.length
                );

            } catch (error) {
                console.error("Nearby places error:", error);

                status.textContent = error.message;
                grid.innerHTML = "";
                pagination.innerHTML = "";

                section.hidden = false;
            }
        },

        () => {
            status.textContent =
                "Allow location access to discover nearby places.";

            section.hidden = false;
        },

        {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 300000
        }
    );
});
