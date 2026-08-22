import json
import time
from pathlib import Path
import requests

# Coordenadas aproximadas de las comunas sugeridas (Gran Santiago)
COMUNAS = {
    "Santiago": {"lat": -33.45, "lon": -70.66},
    "Puente_Alto": {"lat": -33.61, "lon": -70.57},
    "Maipu": {"lat": -33.51, "lon": -70.75},
    "La_Florida": {"lat": -33.52, "lon": -70.52},
    "Pudahuel": {"lat": -33.44, "lon": -70.76},
}

# Período de extracción: Junio 2023 (invierno, alta presencia de material particulado)
START_DATE = "2023-06-01"
END_DATE = "2023-06-30"


def fetch_air_quality(lat: float, lon: float) -> dict:
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm2_5,pm10",
        "start_date": START_DATE,
        "end_date": END_DATE,
    }

    print(f"Descargando datos para Lat: {lat}, Lon: {lon} (PM2.5 y PM10)...")
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def main() -> None:
    dataset_completo = {}

    for comuna, coords in COMUNAS.items():
        try:
            data = fetch_air_quality(coords["lat"], coords["lon"])
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            pm25 = hourly.get("pm2_5", [])
            pm10 = hourly.get("pm10", [])

            dataset_completo[comuna] = {
                "time": times,
                "pm2_5": pm25,
                "pm10": pm10,
            }
            time.sleep(1)
        except Exception as e:
            print(f"Error al descargar {comuna}: {e}")

    output_path = Path("datasets/dataset_aire.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dataset_completo, f, indent=4)

    print(f"Datos cacheados correctamente en {output_path}")


if __name__ == "__main__":
    main()