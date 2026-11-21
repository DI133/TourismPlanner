
import math
import threading
import time
from functools import lru_cache

import requests


# ==========================================================
# API CONFIGURATION
# ==========================================================

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

HEADERS = {
    "User-Agent": "TourismPlanner/1.0 (tourism planning project)",
    "Accept": "application/json",
}

SEARCH_RADIUS_KM = 30
OVERPASS_TIMEOUT = 35
MAX_RESULTS = 100

REQUEST_LOCK = threading.Lock()
LAST_REQUEST_TIME = 0


# ==========================================================
# CATEGORY CONFIGURATION
# ==========================================================

CATEGORY_ALIASES = {
    "all": None,
    "all places": None,
    "attractions": "attraction",
    "attraction": "attraction",
    "museums": "museum",
    "museum": "museum",
    "aquariums": "aquarium",
    "aquarium": "aquarium",
    "historic": "historic_site",
    "historic sites": "historic_site",
    "historic_site": "historic_site",
    "art & culture": "art_culture",
    "art_culture": "art_culture",
    "hotels": "hotel",
    "hotel": "hotel",
    "restaurants": "restaurant",
    "restaurant": "restaurant",
    "cafés": "cafe",
    "cafes": "cafe",
    "cafe": "cafe",
}

CATEGORY_SEARCH_PHRASES = {
    "attraction": [
        "attraction",
        "viewpoint",
        "zoo",
        "theme park",
    ],
    "museum": ["museum"],
    "aquarium": ["aquarium"],
    "historic_site": [
        "historic site",
        "monument",
    ],
    "art_culture": [
        "art gallery",
        "arts centre",
        "theatre",
    ],
    "hotel": [
        "hotel",
        "hostel",
        "guest house",
    ],
    "restaurant": ["restaurant"],
    "cafe": ["cafe"],
}


# Overpass tag selectors for the same categories.
OVERPASS_CATEGORY_FILTERS = {
    "attraction": [
        '["tourism"~"attraction|theme_park|viewpoint|zoo"]',
        '["amenity"="place_of_worship"]',
        '["leisure"~"park|garden|nature_reserve"]',
    ],
    "museum": [
        '["tourism"="museum"]',
        '["amenity"="museum"]',
    ],
    "aquarium": [
        '["tourism"="aquarium"]',
    ],
    "historic_site": [
        '["historic"]',
    ],
    "art_culture": [
        '["tourism"~"artwork|gallery"]',
        '["amenity"~"arts_centre|theatre"]',
    ],
    "hotel": [
        '["tourism"~"hotel|hostel|guest_house|motel"]',
    ],
    "restaurant": [
        '["amenity"="restaurant"]',
    ],
    "cafe": [
        '["amenity"="cafe"]',
    ],
}


# ==========================================================
# NOMINATIM API
# ==========================================================

def _fetch_nominatim(query, limit=10, viewbox=None):
    """Fetch search results from Nominatim with rate limiting."""

    global LAST_REQUEST_TIME

    with REQUEST_LOCK:
        elapsed = time.monotonic() - LAST_REQUEST_TIME

        if elapsed < 1:
            time.sleep(1 - elapsed)

        LAST_REQUEST_TIME = time.monotonic()

    params = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "extratags": 1,
        "namedetails": 1,
        "limit": limit,
        "countrycodes": "in",
    }

    if viewbox:
        params["viewbox"] = viewbox
        params["bounded"] = 1

    response = requests.get(
        NOMINATIM_URL,
        params=params,
        headers=HEADERS,
        timeout=(5, 15),
    )

    response.raise_for_status()

    return response.json()


@lru_cache(maxsize=256)
def _cached_search(query, limit=10, viewbox=None):
    """Cache identical Nominatim requests."""

    return _fetch_nominatim(
        query,
        limit=limit,
        viewbox=viewbox,
    )


# ==========================================================
# DISTANCE CALCULATION
# ==========================================================

def _distance_km(lat1, lon1, lat2, lon2):
    """Calculate distance using the Haversine formula."""

    radius = 6371

    lat1, lon1, lat2, lon2 = map(
        math.radians,
        [lat1, lon1, lat2, lon2],
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return radius * 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )


# ==========================================================
# COMMON PLACE FORMATTER
# ==========================================================

def _format_place(item, category, subcategory):
    """Convert a Nominatim result into the Explore card format."""

    address_data = item.get("address") or {}
    tags = item.get("extratags") or {}

    city = (
        address_data.get("city")
        or address_data.get("town")
        or address_data.get("village")
        or address_data.get("municipality")
        or ""
    )

    osm_id = item.get("osm_id", item.get("place_id", ""))
    osm_type = item.get("osm_type", "node")

    name = (
        item.get("name")
        or (item.get("namedetails") or {}).get("name")
        or item.get("display_name", "").split(",")[0]
        or "Unnamed place"
    )

    description = (
        tags.get("description")
        or f"Discover {name} in "
           f"{city or address_data.get('state', 'India')}."
    )

    return {
        "id": f"osm_{osm_type}_{osm_id}",
        "name": name,
        "category": category,
        "subcategory": subcategory,
        "place_type": subcategory,
        "description": description,
        "address": {
            "city": city,
            "district": address_data.get("state_district", ""),
            "state": address_data.get("state", ""),
            "country": address_data.get("country", "India"),
        },
        "location": {
            "coordinates": [
                float(item["lon"]),
                float(item["lat"]),
            ]
        },
        "images": [],
        "tourism_details": {
            "opening_hours": tags.get("opening_hours", ""),
            "fee": tags.get("fee", ""),
            "wheelchair": tags.get("wheelchair", ""),
        },
        "source": {
            "source_url": (
                f"https://www.openstreetmap.org/"
                f"{osm_type}/{osm_id}"
            )
        },
    }


# ==========================================================
# OVERPASS API QUERY BUILDER
# ==========================================================

def _build_overpass_query(latitude, longitude, category=None):
    """Build an Overpass query around the selected city."""

    if category:
        categories = [category]
    else:
        categories = list(OVERPASS_CATEGORY_FILTERS.keys())

    selectors = []

    for category_name in categories:
        for selector in OVERPASS_CATEGORY_FILTERS[category_name]:
            selectors.append(
                f'nwr(around:{SEARCH_RADIUS_KM * 1000},'
                f'{latitude},{longitude})'
                f'["name"]{selector};'
            )

    query = f"""
    [out:json][timeout:30];
    (
        {"".join(selectors)}
    );
    out center tags;
    """

    return query


# ==========================================================
# OVERPASS API REQUEST
# ==========================================================

@lru_cache(maxsize=64)
def _fetch_overpass(latitude, longitude, category=None):
    """
    Fetch additional destinations from Overpass.

    Tries alternate Overpass endpoints if one fails.
    """

    query = _build_overpass_query(
        latitude,
        longitude,
        category,
    )

    last_error = None

    for endpoint in OVERPASS_ENDPOINTS:
        try:
            print(f"Trying Overpass endpoint: {endpoint}")

            response = requests.post(
                endpoint,
                data={"data": query},
                headers=HEADERS,
                timeout=(5, OVERPASS_TIMEOUT),
            )

            response.raise_for_status()

            payload = response.json()

            elements = payload.get("elements", [])

            if not isinstance(elements, list):
                raise ValueError("Invalid Overpass response.")

            print(
                f"Overpass returned {len(elements)} elements."
            )

            return elements

        except (
            requests.RequestException,
            ValueError,
        ) as exc:
            last_error = exc
            print(f"Overpass endpoint failed: {exc}")

    print(f"All Overpass endpoints failed: {last_error}")

    return []


# ==========================================================
# OVERPASS RESULT FORMATTER
# ==========================================================

def _format_overpass_result(
    item,
    city_name,
    state_name,
):
    """Convert an Overpass element into Explore card format."""

    tags = item.get("tags") or {}
    center = item.get("center") or {}

    latitude = item.get("lat", center.get("lat"))
    longitude = item.get("lon", center.get("lon"))

    if latitude is None or longitude is None:
        return None

    name = tags.get("name")

    if not name:
        return None

    tourism = tags.get("tourism", "")
    amenity = tags.get("amenity", "")
    historic = tags.get("historic", "")
    leisure = tags.get("leisure", "")

    # Classify the result.
    if amenity == "restaurant":
        category = "restaurant"
        subcategory = "restaurant"

    elif amenity == "cafe":
        category = "cafe"
        subcategory = "cafe"

    elif tourism in (
        "hotel",
        "hostel",
        "guest_house",
        "motel",
    ):
        category = "hotel"
        subcategory = tourism

    elif historic:
        category = "historic_site"
        subcategory = historic

    elif tourism == "museum" or amenity == "museum":
        category = "museum"
        subcategory = "museum"

    elif tourism == "aquarium":
        category = "aquarium"
        subcategory = "aquarium"

    elif tourism in ("artwork", "gallery"):
        category = "art_culture"
        subcategory = tourism

    elif amenity in ("arts_centre", "theatre"):
        category = "art_culture"
        subcategory = amenity

    elif amenity == "place_of_worship":
        category = "attraction"
        subcategory = "place_of_worship"

    elif leisure in (
        "park",
        "garden",
        "nature_reserve",
    ):
        category = "attraction"
        subcategory = leisure

    elif tourism in (
        "attraction",
        "viewpoint",
        "zoo",
        "theme_park",
    ):
        category = "attraction"
        subcategory = tourism

    else:
        return None

    osm_type = item.get("type", "node")
    osm_id = item.get("id")

    if osm_id is None:
        return None

    return {
        "id": f"osm_{osm_type}_{osm_id}",
        "name": name,
        "category": category,
        "subcategory": subcategory,
        "place_type": subcategory,
        "description": (
            tags.get("description")
            or f"Discover {name} in {city_name or state_name}, India."
        ),
        "address": {
            "city": tags.get("addr:city") or city_name,
            "district": tags.get("addr:district", ""),
            "state": tags.get("addr:state") or state_name,
            "country": tags.get("addr:country") or "India",
        },
        "location": {
            "coordinates": [
                float(longitude),
                float(latitude),
            ]
        },
        "images": [],
        "tourism_details": {
            "opening_hours": tags.get("opening_hours", ""),
            "fee": tags.get("fee", ""),
            "wheelchair": tags.get("wheelchair", ""),
        },
        "source": {
            "source_url": (
                f"https://www.openstreetmap.org/"
                f"{osm_type}/{osm_id}"
            )
        },
    }


# ==========================================================
# MAIN LIVE SEARCH FUNCTION
# ==========================================================

@lru_cache(maxsize=64)
def search_live_places(location, category=None):
    """
    Search a city using BOTH Nominatim and Overpass.

    Nominatim:
        Resolves the city and finds destinations.

    Overpass:
        Finds additional destinations within 30 km.

    Results:
        Merged and deduplicated before returning.
    """

    location = (location or "").strip()

    if not location:
        return []

    # ------------------------------------------------------
    # 1. Normalize category
    # ------------------------------------------------------

    selected_category = (category or "").strip().lower()

    selected_category = CATEGORY_ALIASES.get(
        selected_category,
        selected_category or None,
    )

    if selected_category not in CATEGORY_SEARCH_PHRASES:
        selected_category = None

    # ------------------------------------------------------
    # 2. Resolve city using Nominatim
    # ------------------------------------------------------

    try:
        city_results = _cached_search(
            location,
            limit=10,
        )
    except requests.RequestException as exc:
        print(f"Nominatim city search failed: {exc}")
        return []

    if not city_results:
        return []

    boundary_candidates = [
        item
        for item in city_results
        if item.get("osm_type") == "relation"
        and item.get("osm_id")
        and item.get("boundingbox")
        and item.get("class") == "boundary"
        and item.get("type") == "administrative"
    ]

    primary = next(
        (
            item
            for item in boundary_candidates
            if item.get("addresstype") in (
                "city",
                "town",
                "municipality",
            )
        ),
        boundary_candidates[0] if boundary_candidates else city_results[0],
    )

    # ------------------------------------------------------
    # 3. Prepare main destination
    # ------------------------------------------------------

    primary_place = _format_place(
        primary,
        "destination",
        "main_destination",
    )

    primary_place["is_primary"] = True
    primary_place["distance_km"] = 0

    primary_address = primary.get("address") or {}

    city_name = (
        primary_address.get("city")
        or primary_address.get("town")
        or primary_address.get("municipality")
        or location.split(",")[0].strip()
    )

    state_name = primary_address.get("state", "")

    if not primary.get("lat") or not primary.get("lon"):
        return [primary_place]

    city_latitude = float(primary["lat"])
    city_longitude = float(primary["lon"])

    # ------------------------------------------------------
    # 4. Build geographic viewbox
    # ------------------------------------------------------

    latitude_delta = SEARCH_RADIUS_KM / 111.0

    longitude_delta = SEARCH_RADIUS_KM / (
        111.0 * max(
            abs(math.cos(math.radians(city_latitude))),
            0.01,
        )
    )

    south = city_latitude - latitude_delta
    north = city_latitude + latitude_delta
    west = city_longitude - longitude_delta
    east = city_longitude + longitude_delta

    viewbox = f"{west},{north},{east},{south}"

    location_text = (
        location
        if "india" in location.lower()
        else f"{location}, India"
    )

    # ------------------------------------------------------
    # 5. Search Nominatim
    # ------------------------------------------------------

    categories_to_search = (
        [selected_category]
        if selected_category
        else list(CATEGORY_SEARCH_PHRASES.keys())
    )

    unique_places = {}

    for result_category in categories_to_search:

        for phrase in CATEGORY_SEARCH_PHRASES[result_category]:

            search_query = f"{phrase} in {location_text}"

            try:
                results = _cached_search(
                    search_query,
                    limit=40,
                    viewbox=viewbox,
                )
            except requests.RequestException as exc:
                print(f"Nominatim search failed: {exc}")
                continue

            for item in results:

                if not item.get("lat") or not item.get("lon"):
                    continue

                osm_class = (item.get("class") or "").lower()
                osm_type = (item.get("type") or "").lower()
                extra_tags = item.get("extratags") or {}

                tourism = (
                    extra_tags.get("tourism")
                    or (osm_type if osm_class == "tourism" else "")
                )

                amenity = (
                    extra_tags.get("amenity")
                    or (osm_type if osm_class == "amenity" else "")
                )

                historic = (
                    extra_tags.get("historic")
                    or (osm_type if osm_class == "historic" else "")
                )

                leisure = (
                    extra_tags.get("leisure")
                    or (osm_type if osm_class == "leisure" else "")
                )

                if amenity == "restaurant":
                    actual_category = "restaurant"
                    subcategory = "restaurant"

                elif amenity == "cafe":
                    actual_category = "cafe"
                    subcategory = "cafe"

                elif tourism in (
                    "hotel",
                    "hostel",
                    "guest_house",
                    "motel",
                ):
                    actual_category = "hotel"
                    subcategory = tourism

                elif historic:
                    actual_category = "historic_site"
                    subcategory = historic

                elif tourism == "museum" or amenity == "museum" or osm_type == "museum":
                    actual_category = "museum"
                    subcategory = "museum"

                elif tourism == "aquarium" or osm_type == "aquarium":
                    actual_category = "aquarium"
                    subcategory = "aquarium"

                elif (
                    tourism in ("artwork", "gallery")
                    or amenity in ("arts_centre", "theatre")
                ):
                    actual_category = "art_culture"
                    subcategory = tourism or amenity

                elif (
                    tourism in (
                        "attraction",
                        "viewpoint",
                        "zoo",
                        "theme_park",
                    )
                    or leisure in (
                        "park",
                        "garden",
                        "nature_reserve",
                    )
                ):
                    actual_category = "attraction"
                    subcategory = tourism or leisure

                else:
                    continue

                if actual_category != result_category:
                    continue

                latitude = float(item["lat"])
                longitude = float(item["lon"])

                distance = _distance_km(
                    city_latitude,
                    city_longitude,
                    latitude,
                    longitude,
                )

                if distance > SEARCH_RADIUS_KM:
                    continue

                formatted = _format_place(
                    item,
                    actual_category,
                    subcategory,
                )

                if not formatted:
                    continue

                formatted["is_primary"] = False
                formatted["distance_km"] = round(distance, 2)

                place_name = (
                    item.get("name")
                    or (item.get("namedetails") or {}).get("name")
                    or item.get("display_name", "").split(",")[0]
                )

                formatted["name"] = place_name

                osm_id = item.get("osm_id") or item.get("place_id")
                osm_element_type = item.get("osm_type") or "place"

                unique_id = f"osm_{osm_element_type}_{osm_id}"
                formatted["id"] = unique_id

                formatted_address = formatted.get("address") or {}

                formatted_address["city"] = (
                    formatted_address.get("city") or city_name
                )

                formatted_address["state"] = (
                    formatted_address.get("state") or state_name
                )

                formatted_address["country"] = (
                    formatted_address.get("country") or "India"
                )

                formatted["address"] = formatted_address

                unique_places[unique_id] = formatted

    nominatim_count = len(unique_places)

    print(f"Nominatim results: {nominatim_count}")

    # ------------------------------------------------------
    # 6. Search Overpass for EVERY city search
    # ------------------------------------------------------

    try:
        overpass_elements = _fetch_overpass(
            city_latitude,
            city_longitude,
            selected_category,
        )

        overpass_count = 0

        for item in overpass_elements:

            formatted = _format_overpass_result(
                item,
                city_name,
                state_name,
            )

            if not formatted:
                continue

            if (
                selected_category
                and formatted["category"] != selected_category
            ):
                continue

            coordinates = formatted["location"]["coordinates"]

            longitude, latitude = coordinates

            distance = _distance_km(
                city_latitude,
                city_longitude,
                latitude,
                longitude,
            )

            if distance > SEARCH_RADIUS_KM:
                continue

            formatted["is_primary"] = False
            formatted["distance_km"] = round(distance, 2)

            # Same OSM ID means the result is a duplicate.
            # Keep the first result (Nominatim, if already found).
            if formatted["id"] not in unique_places:
                unique_places[formatted["id"]] = formatted
                overpass_count += 1

        print(f"Additional Overpass results: {overpass_count}")

    except Exception as exc:
        # Nominatim results are still returned if Overpass fails.
        print(f"Overpass search failed: {exc}")

    # ------------------------------------------------------
    # 7. Sort and return combined results
    # ------------------------------------------------------

    attractions = list(unique_places.values())

    attractions.sort(
        key=lambda place: place.get(
            "distance_km",
            float("inf"),
        )
    )

    attractions = attractions[:MAX_RESULTS]

    print(
        f"FINAL RESULTS: {len(attractions)} destinations "
        f"(Nominatim: {nominatim_count})"
    )

    return [primary_place] + attractions


# ==========================================================
# REVERSE GEOCODING
# ==========================================================

def get_place_address(latitude, longitude):
    """Get address details from coordinates using Nominatim."""

    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": latitude,
                "lon": longitude,
                "format": "jsonv2",
                "addressdetails": 1,
            },
            headers=HEADERS,
            timeout=(5, 10),
        )

        response.raise_for_status()

        address = response.json().get("address", {})

        return {
            "city": (
                address.get("city")
                or address.get("town")
                or address.get("village")
                or address.get("municipality")
                or ""
            ),
            "district": address.get("state_district", ""),
            "state": address.get("state", ""),
            "country": address.get("country", ""),
        }

    except requests.RequestException:
        return {
            "city": "",
            "district": "",
            "state": "",
            "country": "",
        }
