"""Region endpoints for Indonesian provinces and cities."""
import json
import os
from pathlib import Path

from flask import Blueprint, jsonify, request

regions_bp = Blueprint("regions", __name__, url_prefix="/api")

# Load regions data once at module level
_DATA_DIR = Path(__file__).parent.parent / "data"
_REGIONS_FILE = _DATA_DIR / "regions.json"
_regions_data = None


def _get_regions():
    """Lazy load regions data from JSON file."""
    global _regions_data
    if _regions_data is None:
        try:
            with open(_REGIONS_FILE, "r", encoding="utf-8") as f:
                _regions_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            _regions_data = {}
    return _regions_data


@regions_bp.route("/provinces", methods=["GET"])
def get_provinces():
    """Return all provinces in Indonesia."""
    regions = _get_regions()
    provinces = sorted(regions.keys())
    return jsonify({"provinces": provinces}), 200


@regions_bp.route("/cities", methods=["GET"])
def get_cities():
    """Return cities for a given province.
    
    Query params:
        province: Province name (case-insensitive)
    """
    province = request.args.get("province", "").strip()
    if not province:
        return jsonify({"error": "Parameter 'province' wajib diisi."}), 400
    
    regions = _get_regions()
    
    # Case-insensitive lookup
    province_key = None
    for key in regions.keys():
        if key.lower() == province.lower():
            province_key = key
            break
    
    if not province_key:
        return jsonify({"error": f"Provinsi '{province}' tidak ditemukan."}), 404
    
    cities = regions.get(province_key, [])
    return jsonify({
        "province": province_key,
        "cities": cities
    }), 200
