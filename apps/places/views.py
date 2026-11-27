


import logging
import requests
import json
from datetime import date
from django.http import JsonResponse

from apps.accounts.decorators import tourism_login_required
from django.core.cache import cache
from apps.trips.weather_service import get_weather_forecast
from django.shortcuts import render
from apps.places.services.image_service import search_destination_images
from core.db import get_db
from apps.places.services.place_service import find_nearby_places
from apps.places.services.place_service import search_places_paginated
from apps.places.services.live_search_service import (
    search_live_places,
)
from django.views.decorators.http import require_GET, require_POST
from apps.places.services.saved_places_service import (
    save_place,
    get_saved_places,
    remove_saved_place,
)
from apps.places.services.live_search_service import (
    _cached_search,
)
logger = logging.getLogger(__name__)


def _get_positive_integer(value, default, parameter_name):
    if value is None or value == "":
        return default

    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{parameter_name} must be a valid integer."
        )

    if number < 1:
        raise ValueError(
            f"{parameter_name} must be greater than zero."
        )

    return number

@tourism_login_required
def saved_places_page(request):
    return render(request, "places/saved_places.html")

@tourism_login_required
def explore_page(request):
    return render(request, "places/explore.html")


@require_GET
def explore_place_suggestions(request):
    """Return lightweight destination suggestions while the user types."""

    query = request.GET.get("q", "").strip()

    if len(query) < 2:
        return JsonResponse({
            "success": True,
            "suggestions": [],
        })

    try:
        results = _cached_search(query)

        suggestions = []

        for item in results[:8]:
            address = item.get("address") or {}

            name = (
                item.get("name")
                or (item.get("namedetails") or {}).get("name")
                or item.get("display_name", "").split(",")[0]
            )

            if not name:
                continue

            location_parts = [
                address.get("city")
                or address.get("town")
                or address.get("village")
                or address.get("municipality"),
                address.get("state"),
                address.get("country"),
            ]

            location = ", ".join(
                part for part in location_parts if part
            )

            suggestions.append({
                "name": name,
                "display_name": item.get("display_name", name),
                "location": location,
                "type": item.get("type", ""),
            })

        return JsonResponse({
            "success": True,
            "suggestions": suggestions,
        })

    except requests.RequestException:
        logger.exception("Destination autocomplete request failed.")

        return JsonResponse({
            "success": False,
            "suggestions": [],
            "error": "Suggestions are temporarily unavailable.",
        }, status=503)

    except Exception:
        logger.exception("Destination autocomplete failed.")

        return JsonResponse({
            "success": False,
            "suggestions": [],
        }, status=500)


@require_GET
def explore_places(request):
    """Search MongoDB cache or live OSM places without saving results."""

    try:
        query = request.GET.get("q", "").strip()
        city = request.GET.get("city", "").strip() or None
        state = request.GET.get("state", "").strip() or None
        district = request.GET.get("district", "").strip() or None
        category = request.GET.get("category", "").strip() or None
        place_type = request.GET.get("place_type", "").strip() or None
        subcategory = request.GET.get("subcategory", "").strip() or None

        page = _get_positive_integer(
            request.GET.get("page"), 1, "page"
        )

        page_size = min(
            _get_positive_integer(
                request.GET.get("page_size"), 12, "page_size"
            ),
            100,
        )

        # 1. Live search when the user enters a destination.
        if query and not (state or district):
            places = search_live_places(query)

            total = len(places)
            start = (page - 1) * page_size
            page_results = places[start:start + page_size]
            total_pages = (total + page_size - 1) // page_size

            return JsonResponse({
                "success": True,
                "data": page_results,
                "pagination": {
                    "current_page": page,
                    "page_size": page_size,
                    "total_count": total,
                    "total_pages": total_pages,
                    "has_previous": page > 1,
                    "has_next": page < total_pages,
                },
                "source": "OpenStreetMap Nominatim API",
            })

        # 2. District/state discovery: read ALL active place types from MongoDB.
        # Category chips are intentionally applied in the browser after fetching.
        if state or district:
            if not district:
                return JsonResponse({
                    "success": True,
                    "data": [],
                    "message": "Please select a district to discover places.",
                    "pagination": {
                        "current_page": 1,
                        "page_size": page_size,
                        "total_count": 0,
                        "total_pages": 0,
                        "has_previous": False,
                        "has_next": False,
                    },
                    "source": "MongoDB district search",
                })

            # Merge MongoDB records with live Nominatim discoveries. This is
            # important because MongoDB may contain attractions but no hotels,
            # cafes, or restaurants for the selected district.
            cache_key = (
                "explore_district_merged_v3_"
                f"{(state or '').strip().lower()}_"
                f"{district.strip().lower()}_"
                f"{query.strip().lower()}"
            )
            all_places = cache.get(cache_key)

            if all_places is None:
                # Fetch every MongoDB page before merging; do not merge only
                # the currently requested page.
                mongo_places = []
                mongo_page = 1
                while True:
                    mongo_result = search_places_paginated(
                        query=query,
                        state=state,
                        district=district,
                        # Category chips are filtered locally in the browser.
                        page=mongo_page,
                        page_size=100,
                        attractions_only=False,
                        tourist_places_only=False,
                    )
                    mongo_places.extend(mongo_result["results"])
                    if not mongo_result["pagination"]["has_next"]:
                        break
                    mongo_page += 1

                live_places = search_live_places(
                   f"{district}, {state or ''}, India"
                )

                if query:
                    query_lower = query.casefold()
                    live_places = [
                        place for place in live_places
                        if query_lower in (place.get("name") or "").casefold()
                    ]

                # Prefer MongoDB records when the same OSM place exists in
                # both sources; use name/category/coordinates as fallback.
                all_places = []
                seen = set()

                for place in mongo_places + live_places:
                    source = place.get("source") or {}
                    osm_id = source.get("osm_id") or place.get("osm_id")
                    osm_type = source.get("osm_type") or place.get("osm_type")

                    if osm_id:
                        key = ("osm", str(osm_type or ""), str(osm_id))
                    else:
                        location = place.get("location") or {}
                        coordinates = location.get("coordinates") or []
                        coordinate_key = tuple(
                            round(float(value), 5)
                            for value in coordinates[:2]
                        ) if len(coordinates) >= 2 else ()
                        key = (
                            "fallback",
                            (place.get("name") or "").strip().casefold(),
                            (place.get("category") or "").strip().casefold(),
                            coordinate_key,
                        )

                    if key in seen:
                        continue
                    seen.add(key)
                    all_places.append(place)

                # Cache the combined district inventory to avoid repeating
                # Nominatim requests while the user changes pages/categories.
                cache.set(cache_key, all_places, timeout=3600)

            total = len(all_places)
            start = (page - 1) * page_size
            page_results = all_places[start:start + page_size]
            total_pages = (total + page_size - 1) // page_size

            return JsonResponse({
                "success": True,
                "data": page_results,
                "pagination": {
                    "current_page": page,
                    "page_size": page_size,
                    "total_count": total,
                    "total_pages": total_pages,
                    "has_previous": page > 1,
                    "has_next": page < total_pages,
                },
                "source": "MongoDB + OpenStreetMap Nominatim",
            })


        # 3. Fallback to regular MongoDB search for other cities.
        result = search_places_paginated(
            query=query,
            city=city,
            state=state,
            district=district,
            category=category,
            place_type=place_type,
            subcategory=subcategory,
            page=page,
            page_size=page_size,
            attractions_only=False,
        )

        return JsonResponse({
            "success": True,
            "data": result["results"],
            "pagination": result["pagination"],
            "source": "MongoDB",
        })

    except requests.RequestException:
        logger.exception("Live place search failed.")

        return JsonResponse({
            "success": False,
            "error": (
                "The live places service is temporarily unavailable. "
                "Please try again."
            ),
        }, status=503)

    except ValueError as exc:
        return JsonResponse({
            "success": False,
            "error": str(exc),
        }, status=400)

    except Exception:
        logger.exception("Explore API failed.")

        return JsonResponse({
            "success": False,
            "error": "Unable to retrieve places.",
        }, status=500)


@require_GET
def place_image(request):
    """Return saved destination images first, then discover suitable images."""
    name = request.GET.get("name", "").strip()
    city = request.GET.get("city", "").strip()
    state = request.GET.get("state", "").strip()
    place_id = request.GET.get("id", "").strip()

    if not name:
        return JsonResponse({"success": False, "images": []}, status=400)

    # Version the key so old cached empty Openverse responses are not reused.
    key = f"place_image_v2_{place_id}_{name}_{city}_{state}".lower()
    cached = cache.get(key)
    if cached is not None:
        return JsonResponse({"success": True, "images": cached})

    place = {
        "name": name,
        "address": {
            "city": city,
            "state": state,
            "country": "India",
        },
    }

    try:
        collection = get_db()["places"]
        stored_place = None

        # Live OSM results use their OSM id as `place.id`. Enriched MongoDB
        # records keep that value under source.osm_id.
        if place_id:
            stored_place = collection.find_one(
                {
                    "source.osm_id": str(place_id),
                    "images": {"$exists": True, "$ne": []},
                },
                {"images": 1, "_id": 0},
            )

        # Also support cached records and saved destinations that only carry
        # the destination name and address.
        if not stored_place and city:
            import re
            stored_place = collection.find_one(
                {
                    "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
                    "address.city": {"$regex": f"^{re.escape(city)}$", "$options": "i"},
                    "images": {"$exists": True, "$ne": []},
                },
                {"images": 1, "_id": 0},
            )

        images = (stored_place or {}).get("images") or []

        # Live search results often have images=[]; use the existing hybrid
        # Wikipedia -> Wikimedia Commons -> Openverse discovery service.
        if not images:
            images = search_destination_images(place, limit=5)

        cache.set(key, images, 60 * 60 * 6 if images else 60 * 10)
        return JsonResponse({"success": True, "images": images})

    except Exception:
        logger.exception("Destination image lookup failed.")
        cache.set(key, [], 60 * 5)
        return JsonResponse({"success": True, "images": []})


@require_GET
def explore_weather_api(request):
    try:
        latitude = float(request.GET.get("latitude"))
        longitude = float(request.GET.get("longitude"))

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return JsonResponse(
                {"success": False, "error": "Invalid coordinates"},
                status=400
            )

        cache_key = f"explore_weather_{round(latitude, 2)}_{round(longitude, 2)}"
        cached_weather = cache.get(cache_key)

        if cached_weather:
            return JsonResponse(cached_weather)

        today = date.today().isoformat()

        weather = get_weather_forecast(
            latitude,
            longitude,
            today,
            today
        )

        if not weather.get("success"):
            return JsonResponse(weather, status=503)

        result = {
            "success": True,
            "current": weather.get("current", {}),
            "max_temperature": (
                weather.get("max_temperatures", [None])[0]
            ),
            "min_temperature": (
                weather.get("min_temperatures", [None])[0]
            ),
            "rain_probability": (
                weather.get("rain_probability", [None])[0]
            ),
        }

        cache.set(cache_key, result, 3600)
        return JsonResponse(result)

    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "error": "Invalid coordinates"},
            status=400
        )
    except Exception:
        return JsonResponse(
            {"success": False, "error": "Weather unavailable"},
            status=503
        )





@require_GET
def nearby_attractions_api(request):
    try:
        latitude = float(request.GET.get("latitude"))
        longitude = float(request.GET.get("longitude"))

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("Invalid coordinates")

        # Versioned key prevents previously cached empty results being reused.
        cache_key = (
            f"nearby_attractions_v4_"
            f"{round(latitude, 4)}_{round(longitude, 4)}"
        )

        cached_response = cache.get(cache_key)
        if cached_response is not None:
            return JsonResponse(cached_response)

        from math import radians, sin, cos, sqrt, atan2

        def calculate_distance(lat, lon):
            dlat = radians(lat - latitude)
            dlon = radians(lon - longitude)

            a = (
                sin(dlat / 2) ** 2
                + cos(radians(latitude))
                * cos(radians(lat))
                * sin(dlon / 2) ** 2
            )

            return 6371 * 2 * atan2(sqrt(a), sqrt(1 - a))

        # 1. Search verified MongoDB attractions first.
        cached_places = find_nearby_places(
            longitude=longitude,
            latitude=latitude,
            max_distance_meters=5000,
            limit=100,
            # attractions_only=True
        )

        final_places = []

        for place in cached_places:
            coordinates = place.get("location", {}).get("coordinates", [])

            if len(coordinates) != 2:
                continue

            lon, lat = coordinates

            final_places.append({
                "id": str(place.get("id", "")),
                "name": place.get("name") or "Unnamed place",
                "category": (
                    place.get("subcategory")
                    or place.get("category")
                    or "attraction"
                ),
                "distance_km": round(calculate_distance(lat, lon), 2),
                "address": ", ".join(
                    str(value)
                    for value in [
                        (place.get("address") or {}).get("city"),
                        (place.get("address") or {}).get("state")
                    ]
                    if value
                ),
                "latitude": lat,
                "longitude": lon,
                "source": "MongoDB"
            })

        # 2. Fetch live attractions if MongoDB has fewer than seven.
        if True:

            overpass_query = f"""
                [out:json][timeout:60];
                (
                    nwr(around:5000,{latitude},{longitude})["tourism"];

                    nwr(around:5000,{latitude},{longitude})["historic"];

                    nwr(around:5000,{latitude},{longitude})
                        ["amenity"="place_of_worship"];

                    nwr(around:5000,{latitude},{longitude})
                        ["amenity"~"museum|arts_centre|theatre|restaurant|cafe"];

                    nwr(around:5000,{latitude},{longitude})
                        ["leisure"~"park|garden|nature_reserve"];   
                );
                out center tags;
                """

            endpoints = [
                "https://overpass.private.coffee/api/interpreter",
                "https://overpass.nchc.org.tw/api/interpreter",
                "https://overpass-api.de/api/interpreter",
                "https://overpass.kumi.systems/api/interpreter",
            ]

            osm_elements = []

            headers = {
                "User-Agent": (
                    "TourismPlanner/1.0 "
                    "(Nearby Attractions; Django application)"
                ),
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            for endpoint in endpoints:
                try:
                    response = requests.post(
                        endpoint,
                        data={"data": overpass_query},
                        headers=headers,
                        timeout=(10, 90)
                    )

                    response.raise_for_status()

                    osm_elements = response.json().get("elements", [])

                    logger.info(
                        "Overpass success: %s returned %s elements",
                        endpoint,
                        len(osm_elements)
                    )

                    break

                except requests.RequestException as exc:
                    logger.warning(
                        "Overpass request failed at %s: %s",
                        endpoint,
                        exc
                    )

                except ValueError as exc:
                    logger.warning(
                        "Invalid Overpass response from %s: %s",
                        endpoint,
                        exc
                    )

            # 3. Merge live results without duplicates.
            existing_names = {
                item["name"].strip().lower()
                for item in final_places
            }

            for element in osm_elements:
            
                tags = element.get("tags") or {}
                name = tags.get("name")

                if not name:
                    continue

                if name.strip().lower() in existing_names:
                    continue

                lat = element.get("lat")
                lon = element.get("lon")

                if lat is None or lon is None:
                    center = element.get("center") or {}
                    lat = center.get("lat")
                    lon = center.get("lon")

                if lat is None or lon is None:
                    continue

                lat = float(lat)
                lon = float(lon)

                distance = calculate_distance(lat, lon)

                if distance > 10:
                    continue

                if any(
                    abs(item["latitude"] - lat) < 0.0001
                    and abs(item["longitude"] - lon) < 0.0001
                    for item in final_places
                ):
                    continue

                tourism = tags.get("tourism", "")       
                historic = tags.get("historic", "")
                amenity = tags.get("amenity", "")
                leisure = tags.get("leisure", "")

                if amenity == "restaurant":
                    category = "restaurant"

                elif amenity == "cafe":
                    category = "cafe"

                elif tourism in ["hotel", "hostel", "guest_house", "motel"]:
                    category = "hotel"

                elif tourism == "museum" or amenity == "museum":
                    category = "museum"

                elif tourism == "aquarium":
                    category = "aquarium"

                elif historic:
                    category = "historic_site"

                elif tourism in ["gallery", "artwork"] or amenity in [
                    "arts_centre", "theatre"
                ]:
                    category = "art_culture"

                elif amenity == "place_of_worship":
                    category = "attraction"

                elif tourism == "viewpoint":
                    category = "attraction"

                elif tourism in ["attraction", "zoo", "theme_park"] or leisure in [
                    "park", "garden", "nature_reserve"
                ]:
                    category = "attraction"

                else:
                    continue

                final_places.append({
                    "id": f"osm_{element.get('type')}_{element.get('id')}",
                    "name": name,
                    "category": category,
                    "distance_km": round(distance, 2),
                    "address": ", ".join(
                        str(value)
                        for value in [
                            tags.get("addr:city"),
                            tags.get("addr:state")
                        ]
                        if value
                    ),
                    "latitude": lat,
                    "longitude": lon,
                    "source": "OpenStreetMap"
                })

                existing_names.add(name.strip().lower())

        # 4. Sort nearest first and return at most seven.
        final_places.sort(key=lambda item: item["distance_km"])
        

        result = {
            "success": True,
            "radius_km": 5,
            "count": len(final_places),
            "results": final_places
        }

        # Cache successful results for 30 minutes.
        # Cache empty results for only 60 seconds so they can be retried.
        cache.set(
            cache_key,
            result,
            3600 if final_places else 60
        )

        print("FINAL NEARBY ATTRACTIONS:", len(final_places))

        return JsonResponse(result)

    except (TypeError, ValueError):
        return JsonResponse({
            "success": False,
            "error": "Invalid coordinates"
        }, status=400)

    except Exception:
        logger.exception("Nearby attractions search failed.")

        return JsonResponse({
            "success": False,
            "error": "Unable to retrieve nearby attractions."
        }, status=500)



@require_POST
def save_place_api(request):
    user_id = request.session.get("tourism_user_id")

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401
        )

    try:
        data = json.loads(request.body)
        saved_place = save_place(user_id, data.get("place"))

        return JsonResponse({
            "success": True,
            "message": "Destination saved successfully.",
            "saved_place_id": saved_place["saved_place_id"]
        }, status=201)

    except (ValueError, TypeError) as exc:
        return JsonResponse({
            "success": False,
            "error": str(exc)
        }, status=400)

    except Exception:
        logger.exception("Saving destination failed.")
        return JsonResponse({
            "success": False,
            "error": "Unable to save destination."
        }, status=500)


@require_GET
def saved_places_api(request):
    user_id = request.session.get("tourism_user_id")

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401
        )

    try:
        places = get_saved_places(user_id)

        return JsonResponse({
            "success": True,
            "places": places,
            "count": len(places)
        })

    except Exception:
        logger.exception("Retrieving saved places failed.")
        return JsonResponse({
            "success": False,
            "error": "Unable to retrieve saved places."
        }, status=500)


@require_POST
def remove_saved_place_api(request):
    user_id = request.session.get("tourism_user_id")

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401
        )

    try:
        data = json.loads(request.body)

        remove_saved_place(
            user_id,
            data.get("saved_place_id")
        )

        return JsonResponse({
            "success": True,
            "message": "Destination removed from saved places."
        })

    except (ValueError, TypeError) as exc:
        return JsonResponse({
            "success": False,
            "error": str(exc)
        }, status=400)

    except Exception:
        logger.exception("Removing saved destination failed.")
        return JsonResponse({
            "success": False,
            "error": "Unable to remove saved destination."
        }, status=500)
