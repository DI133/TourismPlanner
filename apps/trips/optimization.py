import math
import requests


OSRM_TABLE_URL = "https://router.project-osrm.org/table/v1/driving/"


def get_road_distance_matrix(locations):
    """
    Get road-distance matrix from OSRM.
    Locations: [(longitude, latitude), ...]
    """

    coordinates = ";".join(
        f"{lon},{lat}" for lon, lat in locations
    )

    response = requests.get(
        OSRM_TABLE_URL + coordinates,
        params={"annotations": "distance"},
        timeout=30
    )
    response.raise_for_status()

    data = response.json()

    if data.get("code") != "Ok" or not data.get("distances"):
        raise ValueError("Unable to calculate road-distance matrix.")

    return data["distances"]


def nearest_neighbour(matrix):
    """Generate an initial route from the fixed starting location."""

    remaining = set(range(1, len(matrix)))
    route = [0]
    current = 0

    while remaining:
        next_location = min(
            remaining,
            key=lambda index: (
                matrix[current][index]
                if matrix[current][index] is not None
                else math.inf
            )
        )

        if matrix[current][next_location] is None:
            raise ValueError("Some destinations are not connected by road.")

        route.append(next_location)
        remaining.remove(next_location)
        current = next_location

    return route


def calculate_route_distance(route, matrix):
    total = 0

    for index in range(len(route) - 1):
        distance = matrix[route[index]][route[index + 1]]

        if distance is None:
            return math.inf

        total += distance

    return total


def two_opt(route, matrix):
    """Improve the route using 2-opt while keeping the start fixed."""

    best_route = route[:]
    improved = True

    while improved:
        improved = False
        best_distance = calculate_route_distance(best_route, matrix)

        for i in range(1, len(best_route) - 1):
            for j in range(i + 1, len(best_route)):

                candidate = (
                    best_route[:i]
                    + best_route[i:j + 1][::-1]
                    + best_route[j + 1:]
                )

                candidate_distance = calculate_route_distance(
                    candidate, matrix
                )

                if candidate_distance < best_distance:
                    best_route = candidate
                    best_distance = candidate_distance
                    improved = True
                    break

            if improved:
                break

    return best_route


def optimize_day_route(start_location, destinations):
    """
    Optimize one day's destination sequence.

    start_location: (longitude, latitude)
    destinations: list of dictionaries containing coordinates.
    """

    if not destinations:
        raise ValueError("No destinations available.")

    locations = [start_location]

    for destination in destinations:
        coordinates = destination.get("location", {}).get("coordinates")

        if not coordinates or len(coordinates) != 2:
            raise ValueError("A destination has invalid coordinates.")

        lon, lat = coordinates

        locations.append((float(lon), float(lat)))

    matrix = get_road_distance_matrix(locations)

    initial_route = nearest_neighbour(matrix)
    optimized_route = two_opt(initial_route, matrix)

    original_order = list(range(len(destinations) + 1))

    return {
        "original_distance_m": calculate_route_distance(
            original_order, matrix
        ),
        "optimized_distance_m": calculate_route_distance(
            optimized_route, matrix
        ),
        "optimized_indices": [
            index - 1 for index in optimized_route[1:]
        ]
    }