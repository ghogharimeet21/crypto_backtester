import time
import logging
import traceback
from flask import Blueprint, request, jsonify
from commons.utils import seconds_to_hms
from engine.evaluator import sma_crossover, trend_confluence, test_sets
from engine.runtime import RUNTIME


logger = logging.getLogger(__name__)


engine_bp = Blueprint("engine", __name__, url_prefix="/engine")


@engine_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "success", "message": "Engine is running"})


@engine_bp.route("/sma_crossover", methods=["POST"])
def sma_crossover_backtest():
    try:
        start_time = time.time()

        result = sma_crossover.execute(
            sma_crossover.models.SmaCrossoverStrategy(request.json)
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "execution_time_sec": round(time.time() - start_time, 3),
                    "result": result.to_dict(),
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(traceback.format_exc())
        return jsonify({"status": "failed", "err": str(e)}), 400


@engine_bp.route("/trend_confluence", methods=["POST"])
def trend_confluence_backtest():
    try:
        start_time = time.time()

        result = trend_confluence.execute(
            trend_confluence.models.TrendConfluenceStrategy(request.json)
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "execution_time_sec": round(time.time() - start_time, 3),
                    "result": result.to_dict(),
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(traceback.format_exc())
        return jsonify({"status": "failed", "err": str(e)}), 400



@engine_bp.route("/test_area", methods=["POST"])
def test_area():

    test_sets.execute()

    return jsonify({"msg": "all_good"}), 200