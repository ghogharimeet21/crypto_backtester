from flask import Flask
from flask_cors import CORS
import logging
from data.storage import meta_data


from pandas import read_csv
from os import getcwd
from os.path import join


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] [%(threadName)s] : %(message)s",
)
logger = logging.getLogger(__name__)


app = Flask(__name__)
CORS(app)


cwd = getcwd()
default_loads = read_csv(join(cwd, "default_load.csv"))
logger.info("start default data loading...")
for i in range(len(default_loads)):
    load = default_loads.iloc[i]
    symbol = load["symbol"]
    start_date = str(load["start_date"])
    end_date = str(load["end_date"])
    meta_data.load_data(symbol, start_date, end_date)
logger.info("default data loaded.")

# Registering blueprints
from engine.routes import engine_bp

app.register_blueprint(engine_bp)


app.run(host="0.0.0.0", port=5002, debug=True, use_reloader=False)
