import time
import logging
from flask import Blueprint, request, jsonify





logger = logging.getLogger(__name__)



engine_bp = Blueprint("engine", __name__, url_prefix="/engine")






@engine_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "success", "message": "Engine is running"})


@engine_bp.route("/sample_strategy", methods=["POST"])
def sample_backtest():
    
    ...