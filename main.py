from flexopus import FlexopusClient, helper
import os
from datetime import datetime, timedelta, timezone, time
from argparse import ArgumentParser
import requests
from collections import Counter

def get_user_vehicle(client: FlexopusClient):
    user = client.getSelfUser()["data"]
    vehicles = user["vehicles"]

    if not vehicles:
        print(
            "No vehicles found for the user. Please add a vehicle to your profile to enable automatic parking booking."
        )
        exit(0)

    vehicle = vehicles[0]

    print(
        f"Using vehicle {vehicle['id']} with license plate {vehicle['license_plate']} for parking bookings.\n"
    )

    return user["id"], vehicle

def parse_bookings(client: FlexopusClient, user_id: str):
    bookings = client.getUserBookings(user_id)["data"]
    desk_bookings = []
    parking_bookings = []

    for booking in bookings:
        if booking["external_user_id"] is not None:
            continue
        
        bookable = booking["bookable"]
        bookable_type = bookable["type"]
        
        from_time = datetime.fromisoformat(booking["from_time"].replace("Z", "+00:00"))
        to_time = datetime.fromisoformat(booking["to_time"].replace("Z", "+00:00"))

        booking_data = {
            "id": booking["id"],
            "building_id": bookable["location"]["building"]["id"],
            "location_id": bookable["location"]["id"],
            "from_time": from_time,
            "to_time": to_time,
        }

        if bookable_type == "DESK":
            desk_bookings.append(booking_data)
        elif bookable_type == "PARKING_SPACE":
            parking_bookings.append(booking_data)
    return desk_bookings, parking_bookings

def get_user_vehicle(client):
    user = client.getSelfUser()["data"]
    vehicles = user["vehicles"]

    if not vehicles:
        print(
            "No vehicles found for the user. Please add a vehicle to your profile to enable automatic parking booking."
        )
        exit(0)

    vehicle = vehicles[0]

    print(
        f"Using vehicle {vehicle['id']} with license plate {vehicle['license_plate']} for parking bookings.\n"
    )

    return user["id"], vehicle

def has_parking_for_desk(desk, parking_bookings):
    desk_day = desk["from_time"].date()

    for parking in parking_bookings:
        parking_day = parking["from_time"].date()

        if (
            desk["building_id"] == parking["building_id"]
            and desk_day == parking_day
        ):
            return True

    return False


def book_parking(client, desk, vehicle_id, prefered_parking_spaces: list[str] = []):
    free_space = helper.getPreferedFreeParkingSpace(
        client,
        desk["building_id"],
        desk["from_time"],
        desk["to_time"],
        prefered_parking_spaces,
    )

    if not free_space:
        print(f"-> No free parking space found for desk booking {desk['id']}")
        return

    try:
        client.createBooking(
            location_id=free_space["location_id"],
            bookable_id=free_space["id"],
            from_time=desk["from_time"],
            to_time=desk["to_time"],
            user_vehicle_id=vehicle_id,
        )

        print(
            f"-> Booked parking space {free_space['id']} for desk booking {desk['id']}"
        )
    except requests.exceptions.HTTPError as e:
        # 422 -> 12:00 Uhr DG Limit noch nicht erfüllt
        if e.response.status_code >= 400 and e.response.status_code < 500:
            print(f"-> Failed to book parking space {free_space['id']} for desk booking {desk['id']}: {e.response.json()['message']}")
        else:
            print(f"-> Failed to book parking space {free_space['id']} for desk booking {desk['id']}: {e}")
    except Exception as e:
        print(
            f"-> Failed to book parking space {free_space['id']} for desk booking {desk['id']}: {e}"
        )


def process_desk_bookings(client, desk_bookings, parking_bookings, vehicle_id, prefered_parking_spaces: list[str] = []):
    for desk in desk_bookings:
        print(
            f"Booking ID: {desk['id']}, "
            f"Building ID: {desk['building_id']}, "
            f"Location ID: {desk['location_id']}, "
            f"From: {desk['from_time']}, "
            f"To: {desk['to_time']}"
        )

        if has_parking_for_desk(desk, parking_bookings):
            print("-> Parking already booked for this desk booking.")
        else:
            book_parking(client, desk, vehicle_id, prefered_parking_spaces)

        print("")


def get_booking_times_for_date(desk_bookings, target_date):
    start_times = []
    end_times = []
    for booking in desk_bookings:
        start_times.append(booking["from_time"].time())
        end_times.append(booking["to_time"].time())
    
    if start_times and end_times:
        common_start = Counter(start_times).most_common(1)[0][0]
        common_end = Counter(end_times).most_common(1)[0][0]
    else:
        common_start = time(7, 0, 0)
        common_end = time(17, 0, 0)
        
    if common_end < common_start:
        # The booking spans a day boundary (e.g. UTC day boundary due to timezone offset)
        # End time belongs to the target date, start time belongs to the previous day in UTC
        from_time = datetime.combine(target_date - timedelta(days=1), common_start, tzinfo=timezone.utc)
    else:
        from_time = datetime.combine(target_date, common_start, tzinfo=timezone.utc)
        
    to_time = datetime.combine(target_date, common_end, tzinfo=timezone.utc)
    return from_time, to_time


def find_building(client: FlexopusClient, building_input: str):
    buildings = client.getBuildings()["data"]
    # Check for exact ID match first
    for b in buildings:
        if str(b["id"]) == str(building_input):
            return b
            
    # Check for name match (case-insensitive, strip whitespace)
    for b in buildings:
        if b["name"].strip().lower() == building_input.strip().lower():
            return b
            
    return None


def find_preferred_desk(client: FlexopusClient, name: str, building_id: int, from_time: datetime, to_time: datetime):
    locations = client.getLocations()["data"]
    for location in locations:
        if location["building_id"] != building_id:
            continue
            
        location_id = location["id"]
        try:
            bookables = client.getLocationBookables(location_id, from_time, to_time)["data"]
            for bookable in bookables:
                if bookable["type"] == "DESK" and bookable["name"].strip().lower() == name.strip().lower():
                    return location_id, bookable
        except Exception as e:
            print(f"Warning: Failed to fetch bookables for location {location_id}: {e}")
    return None, None


def book_preferred_desk(client: FlexopusClient, name: str, building_id: int, from_time: datetime, to_time: datetime):
    location_id, desk = find_preferred_desk(client, name, building_id, from_time, to_time)
    if not desk:
        print(f"Preferred desk '{name}' not found in building ID {building_id}.")
        return False

    is_free = desk.get("status") == "FREE" and len(desk.get("actual_bookings", [])) == 0
    if not is_free:
        print(f"Preferred desk '{name}' is not free/available on {from_time.date()}.")
        return False

    print(f"Booking preferred desk '{name}' (ID: {desk['id']}) in location {location_id}...")
    try:
        client.createBooking(
            location_id=location_id,
            bookable_id=desk["id"],
            from_time=from_time,
            to_time=to_time
        )
        print(f"Successfully booked preferred desk '{name}' for {from_time.date()}!")
        return True
    except requests.exceptions.HTTPError as e:
        if e.response.status_code >= 400 and e.response.status_code < 500:
            try:
                msg = e.response.json().get('message', str(e))
            except Exception:
                msg = str(e)
            print(f"Failed to book preferred desk '{name}': {msg}")
        else:
            print(f"Failed to book preferred desk '{name}': {e}")
        return False
    except Exception as e:
        print(f"Failed to book preferred desk '{name}': {e}")
        return False


if __name__ == "__main__":
    parser = ArgumentParser(description="Automatically book parking spaces for desk bookings that don't have a parking space booked yet.")
    parser.add_argument(
        "--host",
        type=str,
        default=os.environ.get("FLEXOPUS_HOST"),
        help="The URL of the Flexopus instance."
    )    
    parser.add_argument(
        "--token",
        type=str,
        default=os.environ.get("FLEXOPUS_TOKEN"),
        help="The API token for authentication."
    )
    parser.add_argument(
        "--cookie-file", 
        type=str, 
        default=os.environ.get("FLEXOPUS_COOKIE_FILE"),
        help="The file to store cookies for authentication.")

    parser.add_argument(
        "--prefered-parking-spaces",
        type=str,
        nargs="*",
        default=[],
        help="A list of prefered parking space names to book. If any of the prefered parking spaces are free, they will be booked instead of a random free parking space."
    )
    parser.add_argument(
        "--preferred-desk",
        type=str,
        default=None,
        help="The name of the preferred desk to book 14 days in the future."
    )
    parser.add_argument(
        "--building",
        type=str,
        default=None,
        help="The name or ID of the building where the preferred desk is located."
    )
    args = parser.parse_args()

    client = FlexopusClient(args.host, args.token, cookie_file=args.cookie_file)
    user_id, vehicle = get_user_vehicle(client)
    desk_bookings, parking_bookings = parse_bookings(client, user_id)

    if args.preferred_desk:
        if not args.building:
            parser.error("--building is required when --preferred-desk is specified.")

        building = find_building(client, args.building)
        if not building:
            print(f"Error: Building '{args.building}' not found.")
            exit(1)

        print(f"Using building: {building['name']} (ID: {building['id']})")

        target_date = (datetime.now() + timedelta(13)).date()
        already_booked = any(desk["from_time"].date() == target_date for desk in desk_bookings)
        if already_booked:
            print(f"A desk is already booked for {target_date}. Skipping preferred desk booking.")
        else:
            print(f"No desk booked for {target_date}. Attempting to book preferred desk '{args.preferred_desk}'...")
            from_time, to_time = get_booking_times_for_date(desk_bookings, target_date)
            success = book_preferred_desk(client, args.preferred_desk, building["id"], from_time, to_time)
            if success:
                desk_bookings, parking_bookings = parse_bookings(client, user_id)

    if args.prefered_parking_spaces:
        process_desk_bookings(
            client,
            desk_bookings,
            parking_bookings,
            vehicle["id"],
            args.prefered_parking_spaces
        )