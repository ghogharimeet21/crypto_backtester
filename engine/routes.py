import time
import logging
import traceback
from flask import Blueprint, request, jsonify
from data.utils import seconds_to_hms
from engine.evaluator import sample_strategy
from engine.evaluator.sample_strategy.models import SampleStrategy

logger = logging.getLogger(__name__)


engine_bp = Blueprint("engine", __name__, url_prefix="/engine")


@engine_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "success", "message": "Engine is running"})


@engine_bp.route("/sample_strategy", methods=["POST"])
def sample_backtest():

    try:
        start_time = time.time()

        strategy = SampleStrategy(request.json)
        sample_strategy.excecute(strategy)

        return jsonify(
            {
                "status": "success",
                "excecution_time": seconds_to_hms(round(start_time - time.time())),
            }
        )
    except Exception as e:
        logging.error(traceback.format_exc())
        return jsonify({"status": "faild", "err": str(e)})
    ...
