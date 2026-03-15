from flexopus import FlexopusClient, helper
import os
from datetime import datetime
from argparse import ArgumentParser
import requests

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
    args = parser.parse_args()

    client = FlexopusClient(args.host, args.token, cookie_file=args.cookie_file)
    user_id, vehicle = get_user_vehicle(client)
    desk_bookings, parking_bookings = parse_bookings(client, user_id)

    process_desk_bookings(
        client,
        desk_bookings,
        parking_bookings,
        vehicle["id"],
        args.prefered_parking_spaces
    )