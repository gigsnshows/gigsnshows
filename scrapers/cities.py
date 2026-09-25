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
        "Ranchi", "Raipur", "Varanasi", "Agra", "Amritsar", "Ludhiana", "Shillong", "Madurai", "Rishikesh",
        "Gangtok", "Siliguri", "Jammu", "Srinagar", "Shimla", "Manali", "Dharamshala", "Kanpur", "Thrissur",
        "Lonavala", "Dubai", "Abu Dhabi", "Singapore", "Bangkok", "Kathmandu", "Colombo", "Dhaka"]},
}

_ALIAS_TO_CITY = {alias: city for city, aliases in CITIES.items() for alias in aliases}
_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in sorted(_ALIAS_TO_CITY, key=len, reverse=True)) + r")\b", re.I)


def detect_city(text):
    """The city named in `text`, or None. When several appear, the last one wins —
    addresses run from street to city, and venue labels end 'Venue: City'."""
    matches = _PATTERN.findall(text or "")
    return _ALIAS_TO_CITY[matches[-1].lower()] if matches else None
