from flask import Flask
from flask_cors import CORS
import logging
from data import meta_data



logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] [%(threadName)s] : %(message)s",
)
logger = logging.getLogger(__name__)


app = Flask(__name__)
CORS(app)


meta_data.data_loader.spot_feed.load_data("BTCUSD", 20260101, 20260201)


from engine.routes import engine_bp
app.register_blueprint(engine_bp)


app.run(host="0.0.0.0", port=5003, debug=True, use_reloader=False)