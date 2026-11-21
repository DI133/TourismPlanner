
const openButton = document.getElementById("openTripForm");
const cancelButton = document.getElementById("cancelTripForm");
const tripForm = document.getElementById("tripForm");
const createForm = document.getElementById("createTripForm");
const tripsGrid = document.getElementById("tripsGrid");
const message = document.getElementById("message");

let editingTripId = null;

function getCookie(name) {
    const cookies = document.cookie.split(";");

    for (const cookie of cookies) {
        const trimmed = cookie.trim();

        if (trimmed.startsWith(name + "=")) {
            return decodeURIComponent(trimmed.substring(name.length + 1));
        }
    }

    return "";
}

function showMessage(text, isError = false) {
    message.textContent = text;
    message.style.color = isError ? "#b42318" : "#276849";
}

function resetTripForm() {
    editingTripId = null;
    createForm.reset();
    tripForm.classList.add("hidden");

    document.querySelector("#tripForm h2").textContent = "Create a new trip";
    createForm.querySelector('button[type="submit"]').textContent = "Create Trip";
}

openButton.addEventListener("click", () => {
    resetTripForm();
    tripForm.classList.remove("hidden");
    showMessage("");
});

cancelButton.addEventListener("click", () => {
    resetTripForm();
    showMessage("");
});

function formatDate(value) {
    if (!value) return "Not specified";

    return new Date(value + "T00:00:00").toLocaleDateString(
        "en-IN",
        { day: "numeric", month: "short", year: "numeric" }
    );
}

function renderTrips(trips) {
    tripsGrid.innerHTML = "";

    if (!trips.length) {
        tripsGrid.innerHTML = `
            <div class="empty-state">
                <h3>No trips planned yet</h3>
                <p>Create your first trip to start planning your journey.</p>
            </div>
        `;
        return;
    }

    trips.forEach(trip => {
        const totalPlaces = (trip.days || []).reduce(
            (total, day) => total + (day.items || []).length,
            0
        );

        const totalDays = (trip.days || []).length;

        const completedDays = (trip.days || []).filter(
            day => day.completed === true
        ).length;

        const progressPercentage = totalDays > 0
            ? Math.round((completedDays / totalDays) * 100)
                : 0;

        const card = document.createElement("article");
        card.className = "trip-card";

        const title = document.createElement("h3");
        title.textContent = trip.title;

        const dates = document.createElement("p");
        dates.className = "trip-meta";
        dates.textContent =
            `${formatDate(trip.start_date)} – ${formatDate(trip.end_date)}`;

        const days = document.createElement("p");
        days.className = "trip-meta";
        days.textContent = `${(trip.days || []).length} days`;

        const places = document.createElement("p");
        places.className = "trip-meta";
        places.textContent = `${totalPlaces} places added`;

        const status = document.createElement("span");
        status.className = "trip-status";
        status.textContent = trip.status || "planned";

        if (totalDays > 0 && completedDays === totalDays) {
            status.textContent = "Trip Completed";
            status.classList.add("trip-completed-status");
        }

        const actions = document.createElement("div");
        actions.className = "trip-card-actions";

        const editButton = document.createElement("button");
        editButton.type = "button";
        editButton.className = "edit-trip-button";
        editButton.textContent = "Edit Trip";

        editButton.addEventListener("click", event => {
            event.stopPropagation();
            startEditingTrip(trip);
        });

        actions.appendChild(editButton);

        
        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.className = "delete-trip-button";
        deleteButton.textContent = "Delete Trip";

        deleteButton.addEventListener("click", async (event) => {
            event.stopPropagation();

            const confirmed = confirm(
            `Are you sure you want to delete "${trip.title}"? This will permanently delete its itinerary too.`
        );

        if (!confirmed) return;

        deleteButton.disabled = true;
        deleteButton.textContent = "Deleting...";

        try {
            const response = await fetch("/trips/api/delete/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCookie("csrftoken")
                },
                body: JSON.stringify({
                    trip_id: trip._id
                })
            });
            

            const result = await response.json();

            if (!response.ok || !result.success) {
                throw new Error(result.error || "Unable to delete trip.");
            }

            showMessage("Trip deleted successfully!");
            await loadTrips();

        } catch (error) {
            showMessage(error.message, true);
            deleteButton.disabled = false;  
            deleteButton.textContent = "Delete Trip";
        }
    });

        actions.appendChild(deleteButton);
        const progressSection = document.createElement("div");

        progressSection.className = "trip-progress";

        const progressLabel = document.createElement("div");
        progressLabel.className = "trip-progress-label";
        progressLabel.textContent =
            `Progress: ${completedDays}/${totalDays} days completed (${progressPercentage}%)`;

        const progressTrack = document.createElement("div");
        progressTrack.className = "trip-progress-track";

        const progressFill = document.createElement("div");
        progressFill.className = "trip-progress-fill";
        progressFill.style.width = `${progressPercentage}%`;

        progressTrack.appendChild(progressFill);
        progressSection.append(progressLabel, progressTrack);

        card.append(title, dates, days, places, status, progressSection, actions);

        card.style.cursor = "pointer";

        card.addEventListener("click", () => {
            window.location.href = `/trips/${trip._id}/`;
        });


        tripsGrid.appendChild(card);
    });
}

function startEditingTrip(trip) {
    editingTripId = trip._id;

    document.getElementById("tripTitle").value = trip.title || "";
    document.getElementById("startDate").value = trip.start_date || "";
    document.getElementById("endDate").value = trip.end_date || "";
    document.getElementById("tripBudget").value = trip.budget ?? 0;

    document.querySelector("#tripForm h2").textContent = "Edit your trip";
    createForm.querySelector('button[type="submit"]').textContent = "Save Changes";

    tripForm.classList.remove("hidden");
    showMessage("");

    tripForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadTrips() {
    try {
        const response = await fetch("/trips/api/list/");
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || "Could not load trips.");
        }

        renderTrips(data.trips);
    } catch (error) {
        tripsGrid.innerHTML = "";
        showMessage(error.message, true);
    }
}

createForm.addEventListener("submit", async event => {
    event.preventDefault();

    const title = document.getElementById("tripTitle").value.trim();
    const startDate = document.getElementById("startDate").value;
    const endDate = document.getElementById("endDate").value;
    const budget = document.getElementById("tripBudget").value;

    if (!title || !startDate || !endDate) {
        showMessage("Please fill in all fields.", true);
        return;
    }

    if (endDate < startDate) {
        showMessage("End date cannot be before start date.", true);
        return;
    }

    if (
        budget === "" ||
        !Number.isFinite(Number(budget)) ||
        Number(budget) < 0
    ) {
        showMessage("Please enter a valid trip budget.", true);
        return;
    }

    const submitButton = createForm.querySelector('button[type="submit"]');
    const isEditing = Boolean(editingTripId);

    submitButton.disabled = true;
    submitButton.textContent = isEditing ? "Saving..." : "Creating...";

    try {
        const response = await fetch(
            isEditing ? "/trips/api/update/" : "/trips/api/create/",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCookie("csrftoken")
                },
                body: JSON.stringify({
                    ...(isEditing ? { trip_id: editingTripId } : {}),
                    title: title,
                    start_date: startDate,
                    end_date: endDate,
                    budget: budget
                })
            }
        );

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(
                data.error || (isEditing ? "Trip update failed." : "Trip creation failed.")
            );
        }

        resetTripForm();
        showMessage(isEditing ? "Trip updated successfully!" : "Trip created successfully!");

        await loadTrips();

    } catch (error) {
        showMessage(error.message, true);
    } finally {
        submitButton.disabled = false;
        submitButton.textContent = editingTripId ? "Save Changes" : "Create Trip";
    }
});

loadTrips();
