"""Stored BSON schema, installed only on the owned rentals collection."""

# Python str.strip()'s whitespace set, explicit because MongoDB's PCRE defaults
# need not classify Unicode whitespace the same way as Python.
NONSPACE = (r"[^\x09-\x0d\x1c-\x20" "\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]")

RENTAL_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "Rental listing",
        "additionalProperties": False,
        "required": ["listingTitle", "status", "propertyType", "availableFrom", "created_at", "updated_at"],
        "properties": {
            "_id": {"bsonType": "objectId"},
            "listingTitle": {
                "bsonType": "string", "minLength": 1, "maxLength": 100,
                # The negative lookahead anchors the absolute end, including a final newline.
                "pattern": rf"\A{NONSPACE}(?:[\s\S]*{NONSPACE})?(?![\s\S])",
                "description": "Required trimmed nonblank title, at most 100 characters",
            },
            "description": {"bsonType": ["string", "null"], "maxLength": 5000},
            "status": {"bsonType": "string", "enum": ["available", "reserved", "rented"]},
            "propertyType": {"bsonType": "string", "enum": ["apartment", "house", "condo", "townhouse"]},
            "availableFrom": {"bsonType": "date"},
            "created_at": {"bsonType": "date"},
            "updated_at": {"bsonType": "date"},
        },
    }
}
