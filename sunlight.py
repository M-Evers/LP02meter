from yoctopuce.yocto_api import *
from yoctopuce.yocto_voltage import *

import csv
import os
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt


def load_config(filename="config.xml"):
    root = ET.parse(filename).getroot()

    return {
        "hub_ip": root.findtext("yoctohub/ip"),
        "channel": root.findtext("sensor/channel"),
        "calibration_uv_per_wm2": float(root.findtext("sensor/calibration_uv_per_wm2")),
        "csv_file": root.findtext("logging/csv_file"),
        "state_file": root.findtext("logging/state_file"),
        "log_frequency": root.findtext("logging/log_frequency"),
        "poll_seconds": int(root.findtext("logging/poll_seconds")),
        "sample_interval_seconds": int(root.findtext("logging/sample_interval_seconds")),
    }


def ensure_csv(csv_file):
    if not os.path.exists(csv_file):
        with open(csv_file, "w", newline="") as f:
            csv.writer(f).writerow([
                "starttijd",
                "eindtijd",
                "serienummer",
                "kanaal",
                "gemiddelde_V",
                "minimum_V",
                "maximum_V",
                "aantal_samples",
                "uitleestijd"
            ])


def load_state(state_file):
    if os.path.exists(state_file):
        with open(state_file, "r") as f:
            return json.load(f)
    return {}


def save_state(state_file, state):
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def find_voltage_channel(channel_name):
    sensor = YVoltage.FirstVoltage()

    while sensor is not None:
        hardware_id = sensor.get_hardwareId()
        friendly_name = sensor.get_friendlyName()

        if (
            hardware_id.endswith("." + channel_name)
            or friendly_name.endswith("." + channel_name)
            or channel_name in hardware_id
            or channel_name in friendly_name
        ):
            return sensor

        sensor = sensor.nextVoltage()

    return None


def setup_datalogger(sensor, log_frequency):
    sensor.set_logFrequency(log_frequency)   # 12/h = elke 5 minuten
    sensor.startDataLogger()


def append_new_logger_data(sensor, config, state):
    state_key = sensor.get_hardwareId()
    last_seen = int(state.get(state_key, 0))

    dataset = sensor.get_recordedData(last_seen, 0)

    while dataset.loadMore() > 0:
        pass

    measures = dataset.get_measures()

    serial = sensor.get_module().get_serialNumber()
    kanaal = sensor.get_friendlyName()
    uitleestijd = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    nieuwste_eindtijd = last_seen
    nieuwe_regels = 0

    with open(config["csv_file"], "a", newline="") as f:
        writer = csv.writer(f)

        for m in measures:
            start_utc = int(m.get_startTimeUTC())
            end_utc = int(m.get_endTimeUTC())

            if end_utc <= last_seen:
                continue

            starttijd = datetime.fromtimestamp(start_utc).strftime("%Y-%m-%d %H:%M:%S")
            eindtijd = datetime.fromtimestamp(end_utc).strftime("%Y-%m-%d %H:%M:%S")

            duur = max(0, end_utc - start_utc)
            aantal_samples = int(duur / config["sample_interval_seconds"])

            writer.writerow([
                starttijd,
                eindtijd,
                serial,
                kanaal,
                m.get_averageValue(),
                m.get_minValue(),
                m.get_maxValue(),
                aantal_samples,
                uitleestijd
            ])

            nieuwste_eindtijd = max(nieuwste_eindtijd, end_utc)
            nieuwe_regels += 1

    state[state_key] = nieuwste_eindtijd
    return nieuwe_regels


def plot_today(csv_file, calibration_uv_per_wm2):
    if not os.path.exists(csv_file):
        return

    df = pd.read_csv(csv_file)

    if df.empty:
        return

    df["eindtijd"] = pd.to_datetime(df["eindtijd"])

    vandaag = datetime.now().date()
    df = df[df["eindtijd"].dt.date == vandaag].copy()

    if df.empty:
        return

    df = df.sort_values("eindtijd")

    df["gemiddelde_Wm2"] = (
        df["gemiddelde_V"] * 1_000_000 / calibration_uv_per_wm2
    )

    plt.clf()
    plt.plot(df["eindtijd"], df["gemiddelde_Wm2"], label="Gemiddelde W/m²")

    plt.title("LP02 instraling vandaag")
    plt.xlabel("Tijd")
    plt.ylabel("W/m²")
    plt.grid(True)
    plt.legend()
    plt.gcf().autofmt_xdate()

    plt.pause(0.1)


def main():
    config = load_config()
    ensure_csv(config["csv_file"])

    errmsg = YRefParam()

    if YAPI.RegisterHub(config["hub_ip"], errmsg) != YAPI.SUCCESS:
        raise RuntimeError("YoctoHub niet bereikbaar: " + errmsg.value)

    try:
        sensor = find_voltage_channel(config["channel"])

        if sensor is None:
            raise RuntimeError(f"Voltagekanaal niet gevonden: {config['channel']}")

        setup_datalogger(sensor, config["log_frequency"])

        state = load_state(config["state_file"])

        print("LP02 logger gestart.")
        print(f"Hub: {config['hub_ip']}")
        print(f"Kanaal: {sensor.get_friendlyName()}")
        print(f"CSV: {config['csv_file']}")
        print("De Yoctopuce-datalogger logt intern elke 5 minuten.")
        print("CSV wordt aangevuld met nieuwe of gemiste loggerrecords.")

        plt.ion()
        plt.figure(figsize=(12, 5))

        while True:
            if sensor.isOnline():
                aantal = append_new_logger_data(sensor, config, state)
                save_state(config["state_file"], state)

                print(
                    f"{datetime.now():%Y-%m-%d %H:%M:%S}: "
                    f"{aantal} nieuwe regels toegevoegd."
                )

                plot_today(
                    config["csv_file"],
                    config["calibration_uv_per_wm2"]
                )
            else:
                print(f"{datetime.now():%Y-%m-%d %H:%M:%S}: sensor offline.")

            time.sleep(config["poll_seconds"])

    except KeyboardInterrupt:
        print("Gestopt door gebruiker.")

    finally:
        YAPI.FreeAPI()


if __name__ == "__main__":
    main()
