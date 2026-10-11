import math
import requests

POSTCODE_CACHE = {}

def get_coordinates(postcode: str):
    clean_postcode = postcode.replace(" ", "").upper()
    if clean_postcode in POSTCODE_CACHE:
        return POSTCODE_CACHE[clean_postcode]
    
    url = f"https://api.postcodes.io/postcodes/{clean_postcode}"
    try:
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            coords = (data['result']['latitude'], data['result']['longitude'])
            POSTCODE_CACHE[clean_postcode] = coords
            return coords
    except Exception:
        pass
    return None

def haversine_distance(coord1, coord2):
    R = 3958.8 
    lat1, lon1 = map(math.radians, coord1)
    lat2, lon2 = map(math.radians, coord2)
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calculate_uk_route(origin_postcode: str, destination_postcode: str):
    coords_origin = get_coordinates(origin_postcode)
    coords_dest = get_coordinates(destination_postcode)
    
    if not coords_origin or not coords_dest:
        return {"distance_miles": 5.0, "travel_time_mins": 15}
    
    direct_miles = haversine_distance(coords_origin, coords_dest)
    road_miles = direct_miles * 1.28
    
    if road_miles < 5.0:
        avg_speed_mph = 14.0 
    elif road_miles < 15.0:
        avg_speed_mph = 20.0 
    else:
        avg_speed_mph = 26.0 
        
    drive_time_mins = (road_miles / avg_speed_mph) * 60.0
    total_time_mins = math.ceil(drive_time_mins + 5)
    
    return {
        "distance_miles": round(road_miles, 2),
        "travel_time_mins": int(total_time_mins)
    }