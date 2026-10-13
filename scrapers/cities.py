"""
Work out which city a show is really in from its venue, address or title.

Listing pages can't be trusted for this: BookMyShow's "Kochi" page lists shows in
Bengaluru and Mumbai, and Skillbox's "Pune" page includes Mumbai gigs. So each
show's own location text is checked against the names below. Neighbourhoods and
satellite towns roll up to the metro people would search for (Thane -> Mumbai,
Gurgaon -> Delhi), which is how the ticketing sites group them too.

To add a city, add a line: "City name": ["other spellings", "neighbourhoods", ...].
"""

import re

CITIES = {
    "Mumbai": ["mumbai", "bombay", "thane", "navi mumbai", "vashi", "kharghar", "panvel", "kalyan", "dombivli",
               "mira road", "mira bhayandar", "vasai", "virar", "bhiwandi", "andheri", "bandra", "juhu", "powai",
               "worli", "lower parel", "colaba", "dadar", "matunga", "malad", "goregaon", "borivali", "kandivali",
               "vile parle", "santacruz", "khar", "chembur", "mulund", "ghatkopar", "kurla", "bkc", "mahalaxmi",
               "nariman point", "byculla", "prabhadevi", "versova", "oshiwara", "jogeshwari", "sakinaka", "marol",
               "nesco", "ncpa", "nmacc", "jio world"],
    "Delhi": ["delhi", "new delhi", "delhi ncr", "gurugram", "gurgaon", "noida", "greater noida", "ghaziabad",
              "faridabad", "saket", "hauz khas", "connaught place", "vasant kunj", "aerocity", "dwarka",
              "rajouri garden", "greater kailash", "chanakyapuri", "mehrauli", "pragati maidan", "bharat mandapam"],
    "Bengaluru": ["bengaluru", "bangalore", "indiranagar", "koramangala", "whitefield", "hsr layout", "jayanagar",
                  "jp nagar", "hebbal", "yelahanka", "marathahalli", "electronic city", "malleshwaram"],
    "Pune": ["pune", "poona", "pimpri", "chinchwad", "baner", "koregaon park", "viman nagar", "kharadi",
             "hinjewadi", "kothrud", "wakad", "hadapsar", "aundh", "magarpatta"],
    "Hyderabad": ["hyderabad", "secunderabad", "gachibowli", "hitec city", "hitech city", "jubilee hills",
                  "banjara hills", "madhapur", "kondapur", "kokapet"],
    "Chennai": ["chennai", "madras", "nungambakkam", "anna nagar", "adyar", "besant nagar"],
    "Kolkata": ["kolkata", "calcutta", "salt lake", "howrah"],
    "Kochi": ["kochi", "cochin", "ernakulam", "angamaly", "kakkanad"],
    "Goa": ["goa", "panaji", "panjim", "calangute", "baga", "anjuna", "vagator", "candolim", "morjim", "arambol",
            "mapusa", "margao", "cavelossim", "assagao", "siolim", "ashvem", "colva", "palolem", "porvorim"],
    "Chandigarh": ["chandigarh", "mohali", "panchkula", "zirakpur"],
    "Ahmedabad": ["ahmedabad", "gandhinagar"],
    "Vadodara": ["vadodara", "baroda"],
    "Mysuru": ["mysuru", "mysore"],
    "Mangaluru": ["mangaluru", "mangalore"],
    "Thiruvananthapuram": ["thiruvananthapuram", "trivandrum"],
    "Kozhikode": ["kozhikode", "calicut"],
    "Visakhapatnam": ["visakhapatnam", "vizag"],
    "Puducherry": ["puducherry", "pondicherry"],
    "Aurangabad": ["aurangabad", "chhatrapati sambhajinagar"],
    "Nashik": ["nashik", "nasik"],
    "Alibaug": ["alibaug", "alibag"],
    **{c: [c.lower()] for c in [
        "Jaipur", "Lucknow", "Indore", "Surat", "Nagpur", "Bhopal", "Coimbatore", "Guwahati", "Dehradun",
        "Udaipur", "Jodhpur", "Kolhapur", "Sangli", "Satara", "Solapur", "Vijayawada", "Bhubaneswar", "Patna",
        "Ranchi", "Raipur", "Jalandhar", "Varanasi", "Agra", "Amritsar", "Ludhiana", "Shillong", "Madurai", "Rishikesh",
        "Gangtok", "Siliguri", "Jammu", "Srinagar", "Shimla", "Manali", "Dharamshala", "Kanpur", "Thrissur",
        "Lonavala", "Dubai", "Abu Dhabi", "Singapore", "Bangkok", "Kathmandu", "Colombo", "Dhaka"]},
}

# Smaller cities that big tours stop in (Satinder Sartaaj's tour plays a dozen of them).
CITIES.update({c: [c.lower()] for c in ["Bathinda", "Rohtak", "Hisar", "Ambala", "Karnal", "Kota", "Hoshiarpur", "Gurdaspur", "Panipat"]})
CITIES["Ganganagar"] = ["sri ganganagar", "ganganagar"]
CITIES["Yamuna Nagar"] = ["yamuna nagar", "yamunanagar"]
CITIES["Varanasi"] = ["varanasi", "banaras", "benares"]

_ALIAS_TO_CITY = {alias: city for city, aliases in CITIES.items() for alias in aliases}
_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in sorted(_ALIAS_TO_CITY, key=len, reverse=True)) + r")\b", re.I)


def detect_city(text):
    """The city named in `text`, or None. When several appear, the last one wins —
    addresses run from street to city, and venue labels end 'Venue: City'."""
    matches = _PATTERN.findall(text or "")
    return _ALIAS_TO_CITY[matches[-1].lower()] if matches else None


# Where a venue's address names no city we know ("Newtown, West Bengal", "Ekana Stadium, Uttar Pradesh"), its map position
# does: the nearest city on this list, if one is within NEAR_KM.
NEAR_KM = 35
_COORDS = {
    "Mumbai": (19.076, 72.878), "Delhi": (28.614, 77.209), "Bengaluru": (12.972, 77.594), "Pune": (18.520, 73.857),
    "Hyderabad": (17.385, 78.487), "Chennai": (13.083, 80.270), "Kolkata": (22.573, 88.364), "Kochi": (9.932, 76.267),
    "Goa": (15.491, 73.828), "Chandigarh": (30.733, 76.779), "Ahmedabad": (23.023, 72.572), "Vadodara": (22.307, 73.181),
    "Mysuru": (12.296, 76.639), "Mangaluru": (12.914, 74.856), "Thiruvananthapuram": (8.524, 76.937),
    "Kozhikode": (11.259, 75.780), "Visakhapatnam": (17.687, 83.219), "Puducherry": (11.934, 79.831),
    "Aurangabad": (19.877, 75.343), "Nashik": (19.998, 73.789), "Alibaug": (18.641, 72.872), "Jaipur": (26.912, 75.787),
    "Lucknow": (26.847, 80.947), "Indore": (22.720, 75.858), "Surat": (21.170, 72.831), "Nagpur": (21.146, 79.088),
    "Bhopal": (23.259, 77.413), "Coimbatore": (11.017, 76.956), "Guwahati": (26.144, 91.736), "Dehradun": (30.316, 78.032),
    "Udaipur": (24.585, 73.713), "Jodhpur": (26.239, 73.024), "Kolhapur": (16.705, 74.243), "Vijayawada": (16.506, 80.648),
    "Bhubaneswar": (20.296, 85.825), "Patna": (25.594, 85.138), "Ranchi": (23.344, 85.310), "Raipur": (21.251, 81.630),
    "Jalandhar": (31.326, 75.576), "Varanasi": (25.317, 82.973), "Agra": (27.177, 78.008), "Amritsar": (31.634, 74.872),
    "Ludhiana": (30.901, 75.857), "Madurai": (9.925, 78.120), "Kanpur": (26.449, 80.332), "Lonavala": (18.750, 73.407),
    "Hisar": (29.149, 75.722), "Rohtak": (28.895, 76.607), "Bathinda": (30.211, 74.945), "Ambala": (30.378, 76.776),
    "Karnal": (29.686, 76.990), "Kota": (25.213, 75.864), "Hoshiarpur": (31.532, 75.912), "Gurdaspur": (32.041, 75.405),
    "Panipat": (29.391, 76.968), "Ganganagar": (29.922, 73.877), "Yamuna Nagar": (30.130, 77.289),
}


def nearest_city(lat, lng):
    """The listed city within NEAR_KM of a map position, or None."""
    from math import asin, cos, radians, sin, sqrt
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    best, best_km = None, NEAR_KM
    for city, (la, lo) in _COORDS.items():
        a = sin(radians(la - lat) / 2) ** 2 + cos(radians(lat)) * cos(radians(la)) * sin(radians(lo - lng) / 2) ** 2
        km = 12742 * asin(sqrt(a))
        if km < best_km:
            best, best_km = city, km
    return best
