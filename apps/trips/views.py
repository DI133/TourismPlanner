
import json
import logging

from io import BytesIO
from decimal import Decimal
from xml.sax.saxutils import escape
from urllib.request import urlopen
from urllib.parse import urlencode

from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)

from apps.trips.optimization import optimize_day_route
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from apps.trips.services import remove_place_from_trip
from apps.accounts.decorators import tourism_login_required
from apps.trips.services import update_trip 
from apps.trips.weather_service import get_weather_forecast
from apps.places.services.place_service import find_nearby_places
from django.shortcuts import render, redirect

from apps.trips.services import (
    create_trip,
    get_user_trips,
    get_trip,
    add_place_to_trip,
    remove_place_from_trip,
    reorder_trip_places,
    update_trip,
    delete_trip,
    update_place_visited,
    update_day_completion,
    apply_optimized_order
)


from apps.trips.expense_service import (
    update_trip_budget,
    add_expense,
    get_expense_summary,
    update_expense,
    delete_expense,
)


logger = logging.getLogger(__name__)


def _get_user_id(request):
    return request.session.get("tourism_user_id")


@require_POST
def create_trip_api(request):
    user_id = _get_user_id(request)

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401,
        )

    try:
        data = json.loads(request.body)

        trip = create_trip(
            user_id=user_id,
            title=data.get("title", ""),
            start_date=data.get("start_date", ""),
            end_date=data.get("end_date", ""),
            budget=data.get("budget", 0),
        )

        return JsonResponse({
            "success": True,
            "trip": trip,
        }, status=201)

    except (ValueError, TypeError, KeyError) as exc:
        return JsonResponse({
            "success": False,
            "error": str(exc),
        }, status=400)

    except Exception:
        logger.exception("Trip creation failed.")
        return JsonResponse({
            "success": False,
            "error": "Unable to create trip.",
        }, status=500)


@require_GET
def list_trips_api(request):
    user_id = _get_user_id(request)

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401,
        )

    try:
        trips = get_user_trips(user_id)

        return JsonResponse({
            "success": True,
            "trips": trips,
        })

    except Exception:
        logger.exception("Trip listing failed.")
        return JsonResponse({
            "success": False,
            "error": "Unable to retrieve trips.",
        }, status=500)


@require_POST
def add_place_api(request):
    user_id = _get_user_id(request)

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401,
        )

    try:
        data = json.loads(request.body)

        place = data.get("place")
        if not isinstance(place, dict) or not place.get("name"):
            raise ValueError("Valid destination details are required.")

        item = add_place_to_trip(
            user_id=user_id,
            trip_id=data.get("trip_id", ""),
            day_number=data.get("day_number"),
            place=place,
        )

        return JsonResponse({
            "success": True,
            "message": "Destination added to your itinerary.",
            "place": item,
        }, status=201)

    except (ValueError, TypeError, KeyError) as exc:
        return JsonResponse({
            "success": False,
            "error": str(exc),
        }, status=400)

    except Exception:
        logger.exception("Adding place to trip failed.")
        return JsonResponse({
            "success": False,
            "error": "Unable to add destination.",
        }, status=500)


from django.shortcuts import render, redirect



@tourism_login_required
def trips_page(request):
    if not request.session.get("tourism_user_id"):
        return redirect("accounts:login")

    return render(request, "trips/trips.html")


@tourism_login_required
def trip_detail_page(request, trip_id):
    user_id = request.session.get("tourism_user_id")

    print("TRIP DETAIL DEBUG")
    print("USER ID:", user_id)
    print("TRIP ID:", trip_id)

    if not user_id:
        return redirect("accounts:login")

    trip = get_trip(user_id, trip_id)

    print("TRIP FOUND:", trip is not None)

    if not trip:
        return redirect("trips:list")

    return render(request, "trips/itinerary.html", {
        "trip": trip,
        "trip_id": trip["_id"],
    })


@tourism_login_required
def download_trip_pdf(request, trip_id):
    user_id = request.session.get("tourism_user_id")
    trip = get_trip(user_id, trip_id)

    if not trip:
        return redirect("trips:list")

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TripTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=colors.HexColor("#245c46"),
        alignment=TA_CENTER,
        spaceAfter=12,
    )

    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#245c46"),
        spaceBefore=14,
        spaceAfter=8,
    )

    normal_style = styles["BodyText"]
    story = []

    # --------------------------------------------------
    # TRIP TITLE AND DATES
    # --------------------------------------------------

    story.append(
        Paragraph(
            escape(str(trip.get("title", "My Trip"))),
            title_style,
        )
    )

    story.append(
        Paragraph(
            f"<b>Travel Dates:</b> "
            f"{escape(str(trip.get('start_date', '')))} to "
            f"{escape(str(trip.get('end_date', '')))}",
            normal_style,
        )
    )

    story.append(Spacer(1, 12))

    # --------------------------------------------------
    # FINANCIAL CALCULATIONS
    # --------------------------------------------------

    def to_amount(value):
        if hasattr(value, "to_decimal"):
            value = value.to_decimal()

        return Decimal(str(value or 0))

    budget = to_amount(trip.get("budget", 0))
    expenses = trip.get("expenses", [])

    total_spent = sum(
        (
            to_amount(expense.get("amount", 0))
            for expense in expenses
        ),
        Decimal("0"),
    )

    remaining = budget - total_spent

    # --------------------------------------------------
    # FINANCIAL OVERVIEW
    # --------------------------------------------------

    story.append(
        Paragraph("Trip Financial Overview", heading_style)
    )

    financial_data = [
        ["Total Budget", "Total Spent", "Remaining Budget"],
        [
            f"Rs. {budget:,.2f}",
            f"Rs. {total_spent:,.2f}",
            f"Rs. {remaining:,.2f}",
        ],
    ]

    financial_table = Table(
        financial_data,
        colWidths=[55 * mm, 55 * mm, 55 * mm],
    )

    financial_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#245c46")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#edf4ef")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("PADDING", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ])
    )

    story.append(financial_table)

    # --------------------------------------------------
    # DAY-WISE ITINERARY
    # --------------------------------------------------

    story.append(
        Paragraph("Day-wise Itinerary", heading_style)
    )

    for day in trip.get("days", []):

        day_story = []

        day_number = day.get("day_number", "")
        day_date = day.get("date", "")

        day_story.append(
            Paragraph(
                f"Day {day_number} - {escape(str(day_date))}",
                styles["Heading3"],
            )
        )

        status = (
            "Completed"
            if day.get("completed", False)
            else "Pending"
        )

        day_story.append(
            Paragraph(
                f"<b>Day Status:</b> {status}",
                normal_style,
            )
        )

        items = day.get("items", [])

        # --------------------------------------------------
        # ROUTE DETAILS - DESTINATIONS ONLY
        # --------------------------------------------------

        day_story.append(
            Paragraph(
                "Route Details – As per Your Sequence",
                heading_style,
            )
        )

        locations = []

        # Only destinations are included.
        # Starting location is intentionally excluded.

        for item in items:

            coordinates = (
                (item.get("location") or {}).get("coordinates", [])
            )

            try:
                lon = float(coordinates[0])
                lat = float(coordinates[1])

                if (
                    -180 <= lon <= 180
                    and -90 <= lat <= 90
                    and (lon != 0 or lat != 0)
                ):
                    locations.append({
                        "name": str(item.get("name", "Destination")),
                        "lon": lon,
                        "lat": lat,
                    })

            except (TypeError, ValueError, IndexError):
                continue

        # Display journey sequence

        if locations:

            route_sequence = " → ".join(
                escape(location["name"])
                for location in locations
            )

            day_story.append(
                Paragraph(
                    f"<b>Journey Sequence:</b> {route_sequence}",
                    normal_style,
                )
            )

        # --------------------------------------------------
        # CALCULATE EVERY CONSECUTIVE ROUTE SEGMENT
        # --------------------------------------------------

        if len(locations) >= 2:

            total_distance = 0
            total_duration = 0
            route_segments = []

            try:

                for index in range(len(locations) - 1):

                    start = locations[index]
                    end = locations[index + 1]

                    coordinates = (
                        f"{start['lon']},{start['lat']};"
                        f"{end['lon']},{end['lat']}"
                    )

                    route_url = (
                        "https://router.project-osrm.org/route/v1/driving/"
                        f"{coordinates}?overview=false&steps=false"
                    )

                    with urlopen(route_url, timeout=12) as response:

                        result = json.loads(
                            response.read().decode("utf-8")
                        )

                    if (
                        result.get("code") != "Ok"
                        or not result.get("routes")
                    ):
                        raise ValueError("Route unavailable")

                    route = result["routes"][0]

                    distance = route["distance"]
                    duration = route["duration"]

                    total_distance += distance
                    total_duration += duration

                    # Segment duration

                    segment_minutes = round(duration / 60)
                    segment_hours = segment_minutes // 60
                    remaining_minutes = segment_minutes % 60

                    segment_duration_text = (
                        f"{segment_hours} hr {remaining_minutes} min"
                        if segment_hours
                        else f"{segment_minutes} min"
                    )

                    route_segments.append({
                        "number": index + 1,
                        "start": start["name"],
                        "end": end["name"],
                        "distance": distance / 1000,
                        "duration": segment_duration_text,
                    })

                # Total route duration

                total_minutes = round(total_duration / 60)

                total_hours = total_minutes // 60
                remaining_minutes = total_minutes % 60

                total_duration_text = (
                    f"{total_hours} hr {remaining_minutes} min"
                    if total_hours
                    else f"{total_minutes} min"
                )

                day_story.append(
                    Paragraph(
                        f"<b>Total Driving Distance:</b> "
                        f"{total_distance / 1000:.1f} km",
                        normal_style,
                    )
                )

                day_story.append(
                    Paragraph(
                        f"<b>Estimated Driving Time:</b> "
                        f"{total_duration_text}",
                        normal_style,
                    )
                )

                # Journey Breakdown

                day_story.append(
                    Paragraph(
                        "<b>Journey Breakdown</b>",
                        styles["Heading3"],
                    )
                )

                for segment in route_segments:

                    day_story.append(
                        Paragraph(
                            f"<b>Segment {segment['number']}:</b> "
                            f"{escape(segment['start'])} → "
                            f"{escape(segment['end'])}<br/>"
                            f"Primary Route<br/>"
                            f"<b>{segment['distance']:.1f} km · "
                            f"{segment['duration']}</b>",
                            normal_style,
                        )
                    )

                    day_story.append(Spacer(1, 6))

                day_story.append(
                    Paragraph(
                        "<i>Estimated time excludes live traffic.</i>",
                        normal_style,
                    )
                )

            except Exception:

                day_story.append(
                    Paragraph(
                        "Route distance and journey breakdown are "
                        "currently unavailable.",
                        normal_style,
                    )
                )

        elif len(locations) == 1:

            day_story.append(
                Paragraph(
                    "Add another destination to calculate a driving route.",
                    normal_style,
                )
            )

        else:

            day_story.append(
                Paragraph(
                    "Route details unavailable because valid coordinates "
                    "are missing.",
                    normal_style,
                )
            )

        day_story.append(Spacer(1, 10))

        # --------------------------------------------------
        # DESTINATION DETAILS
        # --------------------------------------------------

        if not items:

            day_story.append(
                Paragraph(
                    "No destinations added.",
                    normal_style,
                )
            )

        for index, item in enumerate(items, start=1):

            name = escape(
                str(item.get("name", "Unknown"))
            )

            category = escape(
                str(item.get("category", "N/A"))
            )

            address = item.get("address") or {}

            address_parts = [
                address.get("street"),
                address.get("city"),
                address.get("district"),
                address.get("state"),
                address.get("country"),
            ]

            address_text = ", ".join(
                escape(str(part))
                for part in address_parts
                if part
            )

            visited = (
                "Visited"
                if item.get("visited", False)
                else "Not visited"
            )

            day_story.append(
                Paragraph(
                    f"<b>{index}. {name}</b>",
                    normal_style,
                )
            )

            day_story.append(
                Paragraph(
                    f"Category: {category}<br/>"
                    f"Address: {address_text or 'Not available'}<br/>"
                    f"Status: {visited}",
                    normal_style,
                )
            )

            day_story.append(Spacer(1, 7))

        day_story.append(Spacer(1, 10))

        # Keep the day's content together when it fits on a page.
        story.append(KeepTogether(day_story))

    # --------------------------------------------------
    # EXPENSE HISTORY
    # --------------------------------------------------

    story.append(
        Paragraph("Expense History", heading_style)
    )

    expense_data = [
        ["Date", "Category", "Description", "Amount"]
    ]

    for expense in expenses:

        expense_data.append([
            str(expense.get("date", "")),
            str(expense.get("category", "")),
            str(expense.get("description", "") or "-"),
            f"Rs. {to_amount(expense.get('amount', 0)):,.2f}",
        ])

    if not expenses:

        expense_data.append([
            "-",
            "-",
            "No expenses recorded",
            "Rs. 0.00",
        ])

    expense_table = Table(
        expense_data,
        colWidths=[28 * mm, 35 * mm, 75 * mm, 35 * mm],
        repeatRows=1,
    )

    expense_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#245c46")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 7),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ])
    )

    story.append(expense_table)

    # --------------------------------------------------
    # PDF FOOTER
    # --------------------------------------------------

    def add_pdf_footer(canvas, doc):

        canvas.saveState()

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)

        canvas.drawString(
            18 * mm,
            10 * mm,
            "Generated by TourismPlanner",
        )

        canvas.drawRightString(
            A4[0] - 18 * mm,
            10 * mm,
            f"Page {doc.page}",
        )

        canvas.restoreState()

    # --------------------------------------------------
    # GENERATE PDF
    # --------------------------------------------------

    document.build(
        story,
        onFirstPage=add_pdf_footer,
        onLaterPages=add_pdf_footer,
    )

    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(
        pdf,
        content_type="application/pdf",
    )

    trip_name = slugify(
        trip.get("title", "My Trip")
    ) or "my_trip"

    today = timezone.localdate().strftime("%Y-%m-%d")

    response["Content-Disposition"] = (
        f'attachment; filename="{trip_name}_{today}.pdf"'
    )

    return response

@require_POST
def remove_place_api(request):
    user_id = request.session.get("tourism_user_id")

    if not user_id:
        return JsonResponse({
            "success": False,
            "error": "Please log in first."
        }, status=401)

    try:
        data = json.loads(request.body)

        remove_place_from_trip(
            user_id=user_id,
            trip_id=data.get("trip_id"),
            day_number=data.get("day_number"),
            place_index=data.get("place_index"),
        )

        return JsonResponse({
            "success": True,
            "message": "Destination removed successfully."
        })

    except (ValueError, TypeError) as error:
        return JsonResponse({
            "success": False,
            "error": str(error)
        }, status=400)

    except Exception as error:
        return JsonResponse({
            "success": False,
            "error": "Unable to remove destination."
        }, status=500)


@require_POST
def update_trip_api(request):
    user_id = request.session.get("tourism_user_id")

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in first."},
            status=401
        )

    try:
        data = json.loads(request.body)

        update_trip(
            user_id=user_id,
            trip_id=data.get("trip_id"),
            title=data.get("title"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            budget=data.get("budget"),
        )

        return JsonResponse({
            "success": True,
            "message": "Trip updated successfully."
        })

    except (ValueError, TypeError) as error:
        return JsonResponse({
            "success": False,
            "error": str(error)
        }, status=400)

    except Exception:
        return JsonResponse({
            "success": False,
            "error": "Unable to update trip."
        }, status=500)  

@require_POST
def reorder_place_api(request):
    user_id = request.session.get("tourism_user_id")

    if not user_id:
        return JsonResponse({
            "success": False,
            "error": "Please log in first."
        }, status=401)

    try:
        data = json.loads(request.body)

        reorder_trip_places(
            user_id=user_id,
            trip_id=data.get("trip_id"),
            day_number=data.get("day_number"),
            place_index=data.get("place_index"),
            direction=data.get("direction"),
        )

        return JsonResponse({
            "success": True,
            "message": "Destination order updated successfully."
        })

    except (ValueError, TypeError) as error:
        return JsonResponse({
            "success": False,
            "error": str(error)
        }, status=400)

    except Exception as error:
        import traceback
        traceback.print_exc()

        return JsonResponse({
            "success": False,
            "error": str(error)
        }, status=500)



@require_POST
def delete_trip_api(request):
    user_id = request.session.get("tourism_user_id")

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in first."},
            status=401
        )

    try:
        data = json.loads(request.body)

        delete_trip(
            user_id=user_id,
            trip_id=data.get("trip_id")
        )

        return JsonResponse({
            "success": True,
            "message": "Trip deleted successfully."
        })

    except (ValueError, TypeError) as error:
        return JsonResponse(
            {"success": False, "error": str(error)},
            status=400
        )

    except Exception:
        return JsonResponse(
            {"success": False, "error": "Unable to delete trip."},
            status=500
        )


@require_POST
def update_place_visited_api(request):
    user_id = request.session.get("tourism_user_id")

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in first."},
            status=401
        )

    try:
        data = json.loads(request.body)

        update_place_visited(
            user_id=user_id,
            trip_id=data.get("trip_id"),
            day_number=data.get("day_number"),
            place_index=data.get("place_index"),
            visited=data.get("visited")
        )

        return JsonResponse({
            "success": True,
            "message": "Destination status updated."
        })

    except (ValueError, TypeError) as error:
        return JsonResponse(
            {"success": False, "error": str(error)},
            status=400
        )

    except Exception:
        return JsonResponse(
            {"success": False, "error": "Unable to update destination status."},
            status=500
        )


@require_POST
def update_day_completion_api(request):
    user_id = _get_user_id(request)

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401
        )

    try:
        data = json.loads(request.body)

        update_day_completion(
            user_id=user_id,
            trip_id=data.get("trip_id"),
            day_number=data.get("day_number"),
            completed=data.get("completed")
        )

        return JsonResponse({
            "success": True,
            "message": "Day completion updated successfully."
        })

    except (ValueError, TypeError) as error:
        return JsonResponse(
            {"success": False, "error": str(error)},
            status=400
        )

    except Exception:
        logger.exception("Day completion update failed.")
        return JsonResponse(
            {"success": False, "error": "Unable to update day completion."},
            status=500
        )


@require_POST
def optimize_day_route_api(request):
    user_id = _get_user_id(request)

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401
        )

    try:
        data = json.loads(request.body)

        trip_id = data.get("trip_id")
        day_number = int(data.get("day_number"))

        start_location = data.get("start_location", {})
        longitude = float(start_location["longitude"])
        latitude = float(start_location["latitude"])

        trip = get_trip(user_id, trip_id)

        if not trip:
            raise ValueError("Trip not found.")

        day = next(
            (
                item for item in trip["days"]
                if item["day_number"] == day_number
            ),
            None
        )

        if not day:
            raise ValueError("Selected itinerary day does not exist.")

        if day.get("completed", False):
            raise ValueError("Completed days cannot be optimized.")

        destinations = day.get("items", [])

        if len(destinations) < 2:
            raise ValueError("Add at least two destinations to optimize.")

        result = optimize_day_route(
            (longitude, latitude),
            destinations
        )

        optimized_items = [
            destinations[index]["name"]
            for index in result["optimized_indices"]
        ]

        return JsonResponse({
            "success": True,
            "optimized_indices": result["optimized_indices"],
            "optimized_items": optimized_items,
            "original_distance_km": round(
                result["original_distance_m"] / 1000, 2
            ),
            "optimized_distance_km": round(
                result["optimized_distance_m"] / 1000, 2
            )
        })

    except (ValueError, TypeError, KeyError) as error:
        return JsonResponse(
            {"success": False, "error": str(error)},
            status=400
        )

    except Exception:
        logger.exception("Day route optimization failed.")
        return JsonResponse(
            {"success": False, "error": "Unable to optimize this route."},
            status=500
        )

@require_POST
def accept_optimized_route_api(request):
    user_id = _get_user_id(request)

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401
        )

    try:
        data = json.loads(request.body)

        trip_id = data.get("trip_id")
        day_number = int(data.get("day_number"))
        ordered_indices = data.get("ordered_indices")
        start_location = data.get("start_location")

        apply_optimized_order(
            user_id,
            trip_id,
            day_number,
            ordered_indices,
            start_location
        )

        return JsonResponse({
            "success": True,
            "message": "Optimized route saved successfully."
        })

    except (ValueError, TypeError, KeyError) as error:
        return JsonResponse({
            "success": False,
            "error": str(error)
        }, status=400)

    except Exception:
        logger.exception("Accept optimized route failed.")
        return JsonResponse({
            "success": False,
            "error": "Unable to save optimized route."
        }, status=500)


@require_POST
def update_trip_budget_api(request):
    user_id = _get_user_id(request)

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401
        )

    try:
        data = json.loads(request.body)

        update_trip_budget(
            user_id=user_id,
            trip_id=data.get("trip_id"),
            budget=data.get("budget")
        )

        return JsonResponse({
            "success": True,
            "message": "Trip budget updated successfully."
        })

    except (ValueError, TypeError, KeyError) as error:
        return JsonResponse({
            "success": False,
            "error": str(error)
        }, status=400)

    except Exception:
        logger.exception("Trip budget update failed.")
        return JsonResponse({
            "success": False,
            "error": "Unable to update trip budget."
        }, status=500)


@require_POST
def add_expense_api(request):
    user_id = _get_user_id(request)

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401
        )

    try:
        data = json.loads(request.body)

        expense = add_expense(
            user_id=user_id,
            trip_id=data.get("trip_id"),
            amount=data.get("amount"),
            category=data.get("category"),
            description=data.get("description", ""),
            expense_date=data.get("expense_date"),
            day_number=data.get("day_number")
        )

        return JsonResponse({
            "success": True,
            "message": "Expense added successfully.",
            "expense_id": expense["expense_id"]
        }, status=201)

    except (ValueError, TypeError, KeyError) as error:
        return JsonResponse({
            "success": False,
            "error": str(error)
        }, status=400)

    except Exception:
        logger.exception("Adding expense failed.")
        return JsonResponse({
            "success": False,
            "error": "Unable to add expense."
        }, status=500)

@require_GET
def expense_summary_api(request):
    user_id = _get_user_id(request)

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401
        )

    try:
        trip_id = request.GET.get("trip_id")

        summary = get_expense_summary(
            user_id=user_id,
            trip_id=trip_id
        )

        return JsonResponse({
            "success": True,
            "summary": summary
        })

    except (ValueError, TypeError, KeyError) as error:
        return JsonResponse({
            "success": False,
            "error": str(error)
        }, status=400)

    except Exception:
        logger.exception("Expense summary retrieval failed.")
        return JsonResponse({
            "success": False,
            "error": "Unable to retrieve expense summary."
        }, status=500)

@require_POST
def update_expense_api(request):
    user_id = _get_user_id(request)

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401
        )

    try:
        data = json.loads(request.body)

        update_expense(
            user_id=user_id,
            trip_id=data.get("trip_id"),
            expense_id=data.get("expense_id"),
            amount=data.get("amount"),
            category=data.get("category"),
            description=data.get("description", ""),
            expense_date=data.get("expense_date"),
            day_number=data.get("day_number")
        )

        return JsonResponse({
            "success": True,
            "message": "Expense updated successfully."
        })

    except (ValueError, TypeError, KeyError) as error:
        return JsonResponse({
            "success": False,
            "error": str(error)
        }, status=400)

    except Exception:
        logger.exception("Expense update failed.")
        return JsonResponse({
            "success": False,
            "error": "Unable to update expense."
        }, status=500)

@require_POST
def delete_expense_api(request):
    user_id = _get_user_id(request)

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401
        )

    try:
        data = json.loads(request.body)

        delete_expense(
            user_id=user_id,
            trip_id=data.get("trip_id"),
            expense_id=data.get("expense_id")
        )

        return JsonResponse({
            "success": True,
            "message": "Expense deleted successfully."
        })

    except (ValueError, TypeError, KeyError) as error:
        return JsonResponse({
            "success": False,
            "error": str(error)
        }, status=400)

    except Exception:
        logger.exception("Expense deletion failed.")
        return JsonResponse({
            "success": False,
            "error": "Unable to delete expense."
        }, status=500)

@require_GET
def trip_weather_api(request):
    user_id = _get_user_id(request)

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Please log in."},
            status=401
        )

    trip_id = request.GET.get("trip_id")
    trip = get_trip(user_id, trip_id)

    if not trip:
        return JsonResponse(
            {"success": False, "error": "Trip not found."},
            status=404
        )

    weather_results = []

    for day in trip.get("days", []):
        day_date = day.get("date")
        day_story = []
                
        for item in day.get("items", []):
            location = item.get("location") or {}
            coordinates = location.get("coordinates")

            if not coordinates or len(coordinates) != 2:
                continue

            longitude, latitude = coordinates

            try:
                longitude = float(longitude)
                latitude = float(latitude)

                if not (-180 <= longitude <= 180):
                    continue

                if not (-90 <= latitude <= 90):
                    continue

            except (TypeError, ValueError):
                continue

            weather = get_weather_forecast(
                latitude,
                longitude,
                day_date,
                day_date
            )

            weather_results.append({
                "day_number": day.get("day_number"),
                "date": day_date,
                "place_name": item.get("name", "Unknown place"),
                "latitude": latitude,
                "longitude": longitude,
                "weather": weather
            })

    return JsonResponse({
        "success": True,
        "weather": weather_results
    })


@require_GET
def nearby_places_api(request):
    user_id = _get_user_id(request)

    if not user_id:
        return JsonResponse(
            {"success": False, "error": "Authentication required"},
            status=401
        )

    try:
        latitude = float(request.GET.get("latitude"))
        longitude = float(request.GET.get("longitude"))

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("Invalid coordinates")

        nearby = find_nearby_places(
            longitude=longitude,
            latitude=latitude,
            max_distance_meters=5000,
            limit=200
        )

        from math import radians, sin, cos, sqrt, atan2

        results = []

        for place in nearby:
            coordinates = place.get("location", {}).get("coordinates", [])

            if len(coordinates) != 2:
                continue

            lon, lat = coordinates

            dlat = radians(lat - latitude)
            dlon = radians(lon - longitude)

            a = (
                sin(dlat / 2) ** 2
                + cos(radians(latitude))
                * cos(radians(lat))
                * sin(dlon / 2) ** 2
            )

            distance = 6371 * 2 * atan2(sqrt(a), sqrt(1 - a))

            place_type = (place.get("place_type") or "").lower()
            subcategory = (place.get("subcategory") or "").lower()
            tags = place.get("tags") or {}

            amenity = str(tags.get("amenity", "")).lower()
            tourism = str(tags.get("tourism", "")).lower()
            historic = str(tags.get("historic", "")).lower()
            craft = str(tags.get("craft", "")).lower()
            leisure = str(tags.get("leisure", "")).lower()

            category = None

            if place_type == "accommodation":
                category = "hotel"

            elif amenity == "restaurant" or subcategory == "restaurant":
                category = "restaurant"

            elif amenity == "cafe" or subcategory == "cafe":
                category = "cafe"

            elif tourism == "museum" or amenity == "museum":
                category = "museum"

            elif historic:
                category = "historic_site"

            elif (
                tourism in ["gallery", "artwork"]
                or amenity in ["arts_centre", "theatre"]
                or craft
            ):
                category = "art_culture"

            elif (
                tourism in [
                    "attraction", "viewpoint", "zoo",
                    "aquarium", "theme_park"
                ]
                or leisure in ["park", "nature_reserve"]
                or place_type == "attraction"
            ):
                category = "attraction"

            if not category:
                continue

            address = place.get("address") or {}

            address_text = ", ".join(
                str(value)
                for value in [
                    address.get("street"),
                    address.get("city"),
                    address.get("state")
                ]
                if value
            )

            results.append({
                "id": str(place.get("id", "")),
                "name": place.get("name") or "Unnamed place",
                "category": category,
                "distance_km": round(distance, 2),
                "address": address_text,
                "latitude": lat,
                "longitude": lon
            })

        results.sort(key=lambda item: item["distance_km"])

        return JsonResponse({
            "success": True,
            "radius_km": 5,
            "results": results
        })

    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "error": "Invalid coordinates"},
            status=400
        )

@tourism_login_required
def nearby_places_page(request):
    print("NEARBY PAGE SESSION:", dict(request.session))
    print("NEARBY USER ID:", request.session.get("tourism_user_id"))

    user_id = request.session.get("tourism_user_id")

    if not user_id:
        return redirect("accounts:login")

    latitude = request.GET.get("latitude", "")
    longitude = request.GET.get("longitude", "")
    destination = request.GET.get("destination", "Selected Destination")

    return render(request, "trips/nearby_places.html", {
        "latitude": latitude,
        "longitude": longitude,
        "destination": destination,
    })