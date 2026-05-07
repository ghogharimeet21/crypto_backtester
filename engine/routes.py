import time
import logging
import traceback
from flask import Blueprint, request, jsonify
from data.utils import seconds_to_hms
from engine.evaluator import sma_crossover

logger = logging.getLogger(__name__)


engine_bp = Blueprint("engine", __name__, url_prefix="/engine")


@engine_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "success", "message": "Engine is running"})


@engine_bp.route("/sma_crossover", methods=["POST"])
def sma_crossover_backtest():
    """
    POST /engine/sma_crossover

    Request body:
    {
        "symbol":       "BTCUSDT",
        "timeframe":    300,
        "fast_period":  10,
        "slow_period":  20,
        "start_date":   20260101,
        "end_date":     20260131
    }
    """
    try:
        start_time = time.time()

        strategy = sma_crossover.models.SmaCrossoverStrategy(request.json)
        result = sma_crossover.execute(strategy)

        return jsonify(
            {
                "status": "success",
                "execution_time_sec": round(time.time() - start_time, 3),
                "result": result.to_dict(),
            }
        )
    except Exception as e:
        logging.error(traceback.format_exc())
        return jsonify({"status": "failed", "err": str(e)}), 400
