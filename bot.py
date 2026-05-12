import requests
import os
from datetime import datetime, timezone

ODDS_API_KEY = os.environ["ODDS_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

LIGAS = [
    "soccer_usa_mls",
    "soccer_china_superleague",
    "soccer_finland_veikkausliiga",
    "soccer_argentina_primera_division",
    "soccer_brazil_campeonato",
    "soccer_japan_j_league",
    "soccer_mexico_ligamx",
    "soccer_sweden_allsvenskan",
    "soccer_norway_eliteserien",
    "soccer_korea_kleague1",
    "soccer_uruguay_primera_division",
    "soccer_australia_aleague",
]

NOMBRES_LIGAS = {
    "soccer_usa_mls": "🇺🇸 MLS",
    "soccer_china_superleague": "🇨🇳 Superliga China",
    "soccer_finland_veikkausliiga": "🇫🇮 Veikkausliiga",
    "soccer_argentina_primera_division": "🇦🇷 Argentina Primera",
    "soccer_brazil_campeonato": "🇧🇷 Brasileirao",
    "soccer_japan_j_league": "🇯🇵 J-League",
    "soccer_mexico_ligamx": "🇲🇽 Liga MX",
    "soccer_sweden_allsvenskan": "🇸🇪 Allsvenskan",
    "soccer_norway_eliteserien": "🇳🇴 Eliteserien",
    "soccer_korea_kleague1": "🇰🇷 K-League 1",
    "soccer_uruguay_primera_division": "🇺🇾 Uruguay Primera",
    "soccer_australia_aleague": "🇦🇺 A-League",
}

MIN_CUOTA_EMPATE = 3.10
MIN_CUOTA_FAVORITO = 2.20


def send_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML"
    })


def es_hoy(fecha_str):
    fecha = datetime.fromisoformat(fecha_str.replace("Z", "+00:00"))
    hoy = datetime.now(timezone.utc).date()
    return fecha.date() == hoy


def obtener_partidos(liga):
    url = f"https://api.the-odds-api.com/v4/sports/{liga}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": "h2h",
        "oddsFormat": "decimal",
        "bookmakers": "bet365",
    }
    r = requests.get(url, params=params)
    if r.status_code != 200:
        return []
    return r.json()


def analizar_partido(partido, nombre_liga):
    if not es_hoy(partido.get("commence_time", "")):
        return None

    bookmakers = partido.get("bookmakers", [])
    if not bookmakers:
        return None

    mercados = bookmakers[0].get("markets", [])
    h2h = next((m for m in mercados if m["key"] == "h2h"), None)
    if not h2h:
        return None

    outcomes = h2h.get("outcomes", [])
    cuotas = {}
    for o in outcomes:
        cuotas[o["name"]] = o["price"]

    home = partido["home_team"]
    away = partido["away_team"]
    empate = cuotas.get("Draw", 0)
    c_home = cuotas.get(home, 0)
    c_away = cuotas.get(away, 0)

    if empate < MIN_CUOTA_EMPATE:
        return None

    favorito = min(c_home, c_away)
    if favorito < MIN_CUOTA_FAVORITO:
        return None

    fecha = datetime.fromisoformat(partido["commence_time"].replace("Z", "+00:00"))
    hora = fecha.strftime("%H:%M UTC")

    return (
        f"⚽ <b>{nombre_liga}</b>\n"
        f"🏟 {home} vs {away}\n"
        f"🕐 Hoy {hora}\n"
        f"1: {c_home:.2f}  |  X: <b>{empate:.2f}</b>  |  2: {c_away:.2f}"
    )


def main():
    alertas = []

    for liga in LIGAS:
        partidos = obtener_partidos(liga)
        nombre = NOMBRES_LIGAS.get(liga, liga)
        for partido in partidos:
            alerta = analizar_partido(partido, nombre)
            if alerta:
                alertas.append(alerta)

    if alertas:
        cabecera = f"🔔 <b>EMPATES DEL DÍA</b> — {datetime.now(timezone.utc).strftime('%d/%m/%Y')}\n\n"
        mensaje = cabecera + "\n\n".join(alertas)
        send_telegram(mensaje)
        print(f"{len(alertas)} alertas enviadas.")
    else:
        print("Sin alertas hoy.")


if __name__ == "__main__":
    main()
  
