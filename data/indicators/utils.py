from typing import Dict

from data.indicators.enums import SOURCE
from data.indicators.models import EmaSetting, IndicatorSettings, SmaSetting


def quote_in_range(date: int, start_date: int, end_date: int) -> bool:
    return start_date <= date <= end_date


#####################################################################################################################
#####################################################################################################################
##########################.  GET SETTINGS OF INDICATORS
#####################################################################################################################
#####################################################################################################################


def get_sma_setting(strategy_json: Dict) -> SmaSetting:
    try:
        sma_setting: dict = strategy_json.get("sma_setting")
        if sma_setting:
            if not (sma_setting["use_default"]):
                length: list = sma_setting["sma_length"]
                source: SOURCE | str = sma_setting.get("source")
                if not source:
                    sma_source = SOURCE.CLOSE
                else:
                    sma_source = SOURCE(source.upper())
                if length < 1 or length > 50:
                    return None
                return SmaSetting(length, sma_source)

            return SmaSetting()
    except:
        return None


def get_ema_setting(strategy_json: Dict) -> EmaSetting:
    try:
        ema_setting = strategy_json.get("ema_setting")
        if ema_setting:
            if not (ema_setting["use_default"]):
                length: list = ema_setting["ema_length"]
                source: SOURCE | str = ema_setting.get("source")
                if not source:
                    source = SOURCE.CLOSE
                else:
                    source = SOURCE(source.upper())
                if length < 1 or length > 50:
                    return None
                return EmaSetting(length, source)

            return EmaSetting()
    except:
        return None


def get_indicator_settings(strategy_json) -> IndicatorSettings:
    sma_setting = get_sma_setting(strategy_json)
    ema_setting = get_ema_setting(strategy_json)

    return IndicatorSettings(
        sma_setting,
        ema_setting,
    )


#####################################################################################################################
#####################################################################################################################
##########################.  GET SETTINGS OF INDICATORS
#####################################################################################################################
#####################################################################################################################
