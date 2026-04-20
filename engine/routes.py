import time
import logging
from flask import Blueprint, request, jsonify


from engine.evaluator import sample_strategy


logger = logging.getLogger(__name__)


engine_bp = Blueprint("engine", __name__, url_prefix="/engine")


@engine_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "success", "message": "Engine is running"})


@engine_bp.route("/sample_strategy", methods=["POST"])
def sample_backtest():

    try:

        strategy = sample_strategy.models.SampleStrategy(request.json)
        sample_strategy.excecute(strategy)

        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "faild", "err": str(e)})
    ...
