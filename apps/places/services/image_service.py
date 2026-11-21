
from __future__ import annotations

import html
import logging
import re
from urllib.parse import urlparse

import requests


COMMONS_API = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

# Known alternative names for destinations.
# Add more aliases as the destination database grows.
DESTINATION_WIKIPEDIA_ALIASES = {
    "calicut beach": "Kozhikode Beach",
    "kozhikode beach": "Kozhikode Beach",
}
USER_AGENT = (
    "TourismPlanner/1.0 "
    "(tourism destination discovery application)"
)

REQUEST_TIMEOUT = 20

# Only allow licenses suitable for reuse in a potentially
# commercial project.
OPENVERSE_LICENSES = "cc0,pdm,by,by-sa"

logger = logging.getLogger(__name__)


class ImageServiceError(RuntimeError):
    """Raised when destination image retrieval fails."""


def _clean_html(value: str | None) -> str | None:
    """Remove HTML markup from metadata."""

    if not value:
        return None

    cleaned = re.sub(r"<[^>]*>", "", str(value))
    return html.unescape(cleaned).strip() or None


def _get_metadata(metadata: dict, key: str) -> str | None:
    """Safely extract Wikimedia metadata."""

    item = metadata.get(key)

    if not isinstance(item, dict):
        return None

    return _clean_html(item.get("value"))

def _build_attribution(metadata):
    """Build attribution using available Wikimedia metadata."""

    artist = _get_metadata(metadata, "Artist")
    credit = _get_metadata(metadata, "Credit")
    attribution = _get_metadata(metadata, "Attribution")
    license_name = _get_metadata(metadata, "LicenseShortName")

    # Prefer the attribution supplied by Wikimedia.
    if attribution:
        return attribution

    # Otherwise use the available creator and licence information.
    parts = []

    if artist:
        parts.append(f"Photo by {artist}")

    if credit and credit != artist:
        parts.append(f"Credit: {credit}")

    if license_name:
        parts.append(f"licensed under {license_name}")

    return ", ".join(parts) if parts else None


def _get_location(place: dict) -> str:
    """Build a location string from a place document."""

    address = place.get("address") or {}

    if not isinstance(address, dict):
        return ""

    parts = [
        address.get("city"),
        address.get("state"),
        address.get("country"),
    ]

    return " ".join(
        str(part).strip()
        for part in parts
        if part
    )


def _build_search_term(place: dict) -> str:
    """Build a destination search query."""

    name = place.get("name")

    if not isinstance(name, str) or not name.strip():
        return ""

    location = _get_location(place)

    if location:
        return f"{name.strip()} {location}"

    return name.strip()


def _is_https_url(value: str | None) -> bool:
    """Check that a URL uses HTTPS and has a hostname."""

    if not isinstance(value, str):
        return False

    try:
        parsed = urlparse(value)

        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
        )

    except ValueError:
        return False


def _validate_limit(limit: int) -> int:
    """Validate and cap the number of requested images."""

    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit < 1
    ):
        raise ValueError(
            "Image limit must be a positive integer."
        )

    return min(limit, 10)

# ============================================================
# WIKIPEDIA LEAD IMAGE DISCOVERY
# ============================================================

def _get_wikipedia_article_title(place: dict) -> str | None:
    """
    Get a reliable Wikipedia article title.

    Prefer an explicit Wikipedia reference from OSM.
    Otherwise, use known destination aliases or an exact name.
    """

    tourism_details = place.get("tourism_details") or {}

    wikipedia_reference = (
        tourism_details.get("wikipedia")
        or place.get("wikipedia")
    )

    if isinstance(wikipedia_reference, str) and wikipedia_reference.strip():
        reference = wikipedia_reference.strip()

        if reference.startswith("https://en.wikipedia.org/wiki/"):
            return reference.rsplit("/wiki/", 1)[-1].replace("_", " ")

        if ":" in reference:
            language, title = reference.split(":", 1)

            if language.lower() == "en" and title.strip():
                return title.strip().replace("_", " ")

    name = place.get("name")

    if not isinstance(name, str) or not name.strip():
        return None

    normalized_name = name.strip().lower()

    if normalized_name in DESTINATION_WIKIPEDIA_ALIASES:
        return DESTINATION_WIKIPEDIA_ALIASES[normalized_name]

    # Exact-name lookup only. We deliberately avoid guessing
    # a potentially unrelated Wikipedia article.
    return name.strip()


def search_wikipedia_lead_image(place: dict) -> list[dict]:
    """
    Retrieve a destination's Wikipedia lead image.

    The image's actual URL, author, licence and attribution
    are retrieved from Wikimedia Commons.

    Returns an empty list when no usable image is available.
    """

    if not isinstance(place, dict):
        raise ValueError("Place must be a dictionary.")

    article_title = _get_wikipedia_article_title(place)

    if not article_title:
        return []

    headers = {"User-Agent": USER_AGENT}

    try:
        # Step 1: Retrieve the Wikipedia article's lead image.
        response = requests.get(
            WIKIPEDIA_API,
            params={
                "action": "query",
                "format": "json",
                "redirects": 1,
                "titles": article_title,
                "prop": "pageimages",
                "piprop": "name",
            },
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()
        payload = response.json()

        pages = payload.get("query", {}).get("pages", {})

        if not pages:
            return []

        page = next(iter(pages.values()))

        if page.get("missing") or page.get("invalid"):
            return []

        image_name = page.get("pageimage")
        resolved_title = page.get("title")

        if not image_name:
            return []

        # Step 2: Retrieve image metadata from Wikimedia Commons.
        response = requests.get(
            COMMONS_API,
            params={
                "action": "query",
                "format": "json",
                "titles": f"File:{image_name}",
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": 900,
            },
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()
        payload = response.json()

        pages = payload.get("query", {}).get("pages", {})

        if not pages:
            return []

        image_page = next(iter(pages.values()))
        image_info_list = image_page.get("imageinfo", [])

        if not image_info_list:
            return []

        info = image_info_list[0]
        metadata = info.get("extmetadata", {})

        image_url = info.get("thumburl") or info.get("url")
        source_url = info.get("descriptionurl")

        if not _is_https_url(image_url):
            return []

        if not _is_https_url(source_url):
            return []

        image = {
            "provider": "wikipedia",
            "title": image_page.get("title"),
            "url": image_url,
            "source_url": source_url,
            "artist": _get_metadata(metadata, "Artist"),
            "credit": _get_metadata(metadata, "Credit"),
            "attribution": _build_attribution(metadata),
            "license": _get_metadata(
                metadata,
                "LicenseShortName",
            ),
            "license_url": _get_metadata(
                metadata,
                "LicenseUrl",
            ),
            "image_type": "exact_article_image",
            "article_title": resolved_title,
            "article_url": (
                f"https://en.wikipedia.org/wiki/"
                f"{resolved_title.replace(' ', '_')}"
            ),
        }

        logger.info(
            "Found Wikipedia lead image for %s: %s",
            place.get("name"),
            image.get("title"),
        )

        return [image]

    except (
        requests.RequestException,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:

        logger.warning(
            "Wikipedia image discovery failed for %s: %s",
            place.get("name"),
            exc,
        )

        return []

# ============================================================
# WIKIMEDIA COMMONS SEARCH
# ============================================================

def _search_commons_images_only(
    place: dict,
    limit: int = 5,
) -> list[dict]:
    """
    Search Wikimedia Commons for destination photographs.

    Returns normalized image metadata.
    Does not save anything to MongoDB.

    This is the internal Commons-only implementation.
    """

    if not isinstance(place, dict):
        raise ValueError("Place must be a dictionary.")

    search_term = _build_search_term(place)

    if not search_term:
        return []

    limit = _validate_limit(limit)

    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {search_term}",
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 900,
    }

    try:
        response = requests.get(
            COMMONS_API,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()
        payload = response.json()

    except requests.RequestException as exc:
        raise ImageServiceError(
            f"Unable to communicate with Wikimedia Commons: {exc}"
        ) from exc

    except ValueError as exc:
        raise ImageServiceError(
            "Wikimedia Commons returned invalid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise ImageServiceError(
            "Unexpected Wikimedia response format."
        )

    if payload.get("error"):
        raise ImageServiceError(
            f"Wikimedia API error: {payload['error']}"
        )

    pages = payload.get("query", {}).get("pages", {})

    images = []

    for page in pages.values():

        image_info_list = page.get("imageinfo", [])

        if not image_info_list:
            continue

        info = image_info_list[0]
        metadata = info.get("extmetadata", {})

        image_url = (
            info.get("thumburl")
            or info.get("url")
        )

        source_url = info.get("descriptionurl")

        if not _is_https_url(image_url):
            continue

        if not _is_https_url(source_url):
            continue

        images.append({
            "provider": "wikimedia_commons",
            "title": page.get("title"),
            "url": image_url,
            "source_url": source_url,
            "artist": _get_metadata(metadata, "Artist"),
            "credit": _get_metadata(metadata, "Credit"),
            "attribution": _build_attribution(metadata),
            "license": _get_metadata(
                metadata,
                "LicenseShortName",
            ),
            "license_url": _get_metadata(
                metadata,
                "LicenseUrl",
            ),
        })

    return images


# ============================================================
# OPENVERSE SEARCH
# ============================================================

def search_openverse_images(
    place: dict,
    limit: int = 5,
) -> list[dict]:
    """
    Search Openverse for openly licensed destination photographs.

    Restricts results to CC0, public domain, CC BY and CC BY-SA.

    Returns normalized image metadata.
    Does not save anything to MongoDB.
    """

    if not isinstance(place, dict):
        raise ValueError("Place must be a dictionary.")

    search_term = _build_search_term(place)

    if not search_term:
        return []

    limit = _validate_limit(limit)

    params = {
        "q": search_term,
        "page_size": limit,
        "mature": "false",
        "license": OPENVERSE_LICENSES,
    }

    try:
        response = requests.get(
            OPENVERSE_API,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=(10, 60),
        )

        response.raise_for_status()
        payload = response.json()

    except requests.RequestException as exc:
        raise ImageServiceError(
            f"Unable to communicate with Openverse: {exc}"
        ) from exc

    except ValueError as exc:
        raise ImageServiceError(
            "Openverse returned invalid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise ImageServiceError(
            "Unexpected Openverse response format."
        )

    results = payload.get("results", [])

    if not isinstance(results, list):
        raise ImageServiceError(
            "Openverse returned an invalid results collection."
        )

    images = []

    for result in results:

        if not isinstance(result, dict):
            continue

        image_url = (
            result.get("thumbnail")
            or result.get("url")
        )

        source_url = result.get("foreign_landing_url")

        if not _is_https_url(image_url):
            continue

        if not _is_https_url(source_url):
            continue

        license_name = result.get("license")
        license_version = result.get("license_version")

        if not license_name:
            continue

        license_name = str(license_name).upper()

        if license_name not in {
            "CC0",
            "PDM",
            "BY",
            "BY-SA",
        }:
            continue

        if license_version:
            license_display = (
                f"{license_name} {license_version}"
            )
        else:
            license_display = license_name

        creator = result.get("creator")

        images.append({
            "provider": "openverse",
            "title": result.get("title"),
            "url": image_url,
            "source_url": source_url,
            "artist": creator,
            "credit": result.get("attribution"),
            "attribution": result.get("attribution"),
            "license": license_display,
            "license_url": result.get("license_url"),
        })

    return images



def search_destination_images(
    place: dict,
    limit: int = 5,
) -> list[dict]:

    if not isinstance(place, dict):
        raise ValueError("Place must be a dictionary.")

    limit = _validate_limit(limit)

    all_images = []

    # 1. Search Wikipedia
    try:
        all_images.extend(
            search_wikipedia_lead_image(place)
        )
    except Exception as exc:
        logger.warning("Wikipedia search failed: %s", exc)

    # 2. Search Wikimedia Commons
    try:
        all_images.extend(
            _search_commons_images_only(place, limit=limit)
        )
    except ImageServiceError as exc:
        logger.warning("Commons search failed: %s", exc)

    # 3. Search Openverse
    try:
        all_images.extend(
            search_openverse_images(place, limit=limit)
        )
    except ImageServiceError as exc:
        logger.warning("Openverse search failed: %s", exc)

    # 4. Remove duplicate image URLs
    unique_images = []
    seen_urls = set()

    for image in all_images:
        image_url = image.get("url")

        if image_url and image_url not in seen_urls:
            seen_urls.add(image_url)
            unique_images.append(image)

    return unique_images


# ============================================================
# BACKWARD COMPATIBILITY
# ============================================================

# Existing management commands import search_commons_images.
# Keep that name working, but route it through hybrid search.
#
# IMPORTANT:
# The hybrid function calls _search_commons_images_only()
# directly, so this alias cannot cause recursion.

search_commons_images = search_destination_images
