import requests
import os
import json
from datetime import datetime, timezone, timedelta

ODDS_API_KEY = os.environ["ODDS_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

PICKS_FILE = "picks.json"

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


def send_photo_telegram(image_bytes, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
                  files={"photo": ("chart.png", image_bytes, "image/png")})


def cargar_picks():
    if os.path.exists(PICKS_FILE):
        with open(PICKS_FILE) as f:
            return json.load(f)
    return []


def guardar_picks(picks):
    with open(PICKS_FILE, "w") as f:
        json.dump(picks, f, indent=2, ensure_ascii=False)


def commit_picks():
    """Sube el picks.json actualizado al repo de GitHub."""
    try:
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            print("Sin GH_TOKEN, no se puede hacer commit")
            return

        with open(PICKS_FILE, "rb") as f:
            import base64
            contenido = base64.b64encode(f.read()).decode()

        # Obtener SHA actual del archivo
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        repo = "figueinardo/Empates-Bot"
        url = f"https://api.github.com/repos/{repo}/contents/{PICKS_FILE}"

        r = requests.get(url, headers=headers)
        sha = r.json().get("sha", "") if r.status_code == 200 else ""

        # Hacer commit
        payload = {
            "message": f"bot: actualizar picks {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
            "content": contenido,
            "sha": sha
        }
        requests.put(url, headers=headers, json=payload)
        print("picks.json actualizado en GitHub")
    except Exception as e:
        print(f"Error commit picks: {e}")


def obtener_scores(liga):
    url = f"https://api.the-odds-api.com/v4/sports/{liga}/scores/"
    params = {"apiKey": ODDS_API_KEY, "daysFrom": 1}
    r = requests.get(url, params=params)
    if r.status_code != 200:
        print(f"Error scores {liga}: {r.status_code}")
        return []
    return r.json()


def normalizar(nombre):
    return nombre.lower().strip()


def buscar_resultado(home, away, scores):
    for partido in scores:
        if not partido.get("completed"):
            continue
        h = normalizar(partido.get("home_team", ""))
        a = normalizar(partido.get("away_team", ""))
        if normalizar(home) in h or h in normalizar(home):
            if normalizar(away) in a or a in normalizar(away):
                return partido
    return None


def determinar_resultado(partido_score):
    scores = partido_score.get("scores")
    if not scores:
        return None
    marcador = {s["name"]: int(s["score"]) for s in scores if s["score"] is not None}
    teams = list(marcador.keys())
    if len(teams) < 2:
        return None
    if marcador[teams[0]] == marcador[teams[1]]:
        return "W"
    return "L"


def actualizar_resultados():
    picks = cargar_picks()
    pendientes = [p for p in picks if p.get("resultado") is None]
    if not pendientes:
        return []

    ligas_pendientes = {}
    for pick in pendientes:
        liga_key = next((k for k, v in NOMBRES_LIGAS.items() if v == pick["liga"]), None)
        if liga_key and liga_key not in ligas_pendientes:
            ligas_pendientes[liga_key] = obtener_scores(liga_key)

    actualizados = []
    for pick in picks:
        if pick.get("resultado") is not None:
            continue
        liga_key = next((k for k, v in NOMBRES_LIGAS.items() if v == pick["liga"]), None)
        if not liga_key or liga_key not in ligas_pendientes:
            continue
        scores = ligas_pendientes[liga_key]
        partido = buscar_resultado(pick["home"], pick["away"], scores)
        if partido:
            resultado = determinar_resultado(partido)
            if resultado:
                pick["resultado"] = resultado
                pick["profit"] = round(pick["cuota"] - 1, 2) if resultado == "W" else -1
                actualizados.append(pick)

    if actualizados:
        guardar_picks(picks)
        commit_picks()

    return actualizados


def generar_grafica():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import io

        picks = cargar_picks()
        resueltos = [p for p in picks if p["profit"] is not None]
        if len(resueltos) < 2:
            return None

        profits = [p["profit"] for p in resueltos]
        cum_profit = []
        acum = 0
        for p in profits:
            acum += p
            cum_profit.append(round(acum, 2))

        n = len(resueltos)
        yields = [round((cum_profit[i] / (i + 1)) * 100, 2) for i in range(n)]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), facecolor="#1a1a2e")
        for ax in [ax1, ax2]:
            ax.set_facecolor("#16213e")
            ax.tick_params(colors="white")
            ax.yaxis.label.set_color("white")
            ax.xaxis.label.set_color("white")
            for spine in ax.spines.values():
                spine.set_edgecolor("#444")

        x = list(range(1, n + 1))
        ax1.plot(x, cum_profit, color="#00ff88", linewidth=2, marker="o", markersize=3)
        ax1.axhline(0, color="#666", linestyle="--", linewidth=0.8)
        ax1.fill_between(x, cum_profit, 0, where=[v >= 0 for v in cum_profit], alpha=0.2, color="#00ff88")
        ax1.fill_between(x, cum_profit, 0, where=[v < 0 for v in cum_profit], alpha=0.2, color="#ff4444")
        ax1.set_title("📈 Beneficio Acumulado (u)", color="white", fontsize=12, pad=8)
        ax1.set_ylabel("Unidades", color="white")

        ax2.plot(x, yields, color="#00aaff", linewidth=2, marker="o", markersize=3)
        ax2.axhline(0, color="#666", linestyle="--", linewidth=0.8)
        ax2.set_title("📊 Yield (%)", color="white", fontsize=12, pad=8)
        ax2.set_ylabel("Yield %", color="white")
        ax2.set_xlabel("Nº de picks", color="white")

        wins = sum(1 for p in resueltos if p["profit"] and p["profit"] > 0)
        losses = sum(1 for p in resueltos if p["profit"] and p["profit"] < 0)
        voids = sum(1 for p in resueltos if p["profit"] == 0)

        fig.suptitle(
            f"BOT EMPATES VERANO  |  {n} picks  |  {wins}W {losses}L {voids}V  |  "
            f"Profit: {cum_profit[-1]:+.2f}u  |  Yield: {yields[-1]:+.2f}%",
            color="white", fontsize=11, y=0.98
        )
        plt.tight_layout(rect=[0, 0, 1, 0.96])

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=130, bbox_inches="tight")
        buf.seek(0)
        plt.close()
        return buf.read()

    except Exception as e:
        print(f"Error generando gráfica: {e}")
        return None


def resumen_stats():
    picks = cargar_picks()
    resueltos = [p for p in picks if p["profit"] is not None]
    pendientes = [p for p in picks if p["profit"] is None]
    if not resueltos:
        return None

    total = len(resueltos)
    wins = sum(1 for p in resueltos if p["profit"] > 0)
    losses = sum(1 for p in resueltos if p["profit"] < 0)
    voids = sum(1 for p in resueltos if p["profit"] == 0)
    profit = sum(p["profit"] for p in resueltos)
    yield_pct = (profit / total) * 100 if total else 0
    racha = 0
    for p in reversed(resueltos):
        if p["profit"] > 0:
            racha += 1
        else:
            break

    return (
        f"📊 <b>RESUMEN BOT EMPATES</b>\n\n"
        f"Picks resueltos: <b>{total}</b>\n"
        f"✅ Wins: <b>{wins}</b>  ❌ Losses: <b>{losses}</b>  ➖ Void: <b>{voids}</b>\n"
        f"💰 Profit: <b>{profit:+.2f}u</b>\n"
        f"📈 Yield: <b>{yield_pct:+.2f}%</b>\n"
        f"🔥 Racha actual: <b>{racha} wins seguidos</b>\n"
        f"⏳ Pendientes: <b>{len(pendientes)}</b>"
    )


def es_hoy(fecha_str):
    try:
        fecha = datetime.fromisoformat(fecha_str.replace("Z", "+00:00"))
        hoy = datetime.now(timezone.utc).date()
        return fecha.date() == hoy
    except Exception:
        return False


def obtener_partidos(liga):
    url = f"https://api.the-odds-api.com/v4/sports/{liga}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": "h2h",
        "oddsFormat": "decimal",
        "bookmakers": "pinnacle",
    }
    r = requests.get(url, params=params)
    if r.status_code != 200:
        print(f"Error {r.status_code} en {liga}: {r.text}")
        return []
    return r.json()


def analizar_partido(partido, nombre_liga):
    if not es_hoy(partido.get("commence_time", "")):
        return None, None

    bookmakers = partido.get("bookmakers", [])
    if not bookmakers:
        return None, None

    h2h = None
    for bm in bookmakers:
        mercados = bm.get("markets", [])
        h2h = next((m for m in mercados if m["key"] == "h2h"), None)
        if h2h:
            break

    if not h2h:
        return None, None

    outcomes = h2h.get("outcomes", [])
    cuotas = {o["name"]: o["price"] for o in outcomes}

    home = partido["home_team"]
    away = partido["away_team"]
    empate = cuotas.get("Draw", 0)
    c_home = cuotas.get(home, 0)
    c_away = cuotas.get(away, 0)

    if empate < MIN_CUOTA_EMPATE:
        return None, None

    favorito = min(c_home, c_away)
    if favorito < MIN_CUOTA_FAVORITO:
        return None, None

    hora = datetime.fromisoformat(
        partido["commence_time"].replace("Z", "+00:00")
    ).strftime("%H:%M UTC")

    texto = (
        f"⚽ <b>{nombre_liga}</b>\n"
        f"🏟 {home} vs {away}\n"
        f"🕐 Hoy {hora}\n"
        f"1: {c_home:.2f}  |  X: <b>{empate:.2f}</b>  |  2: {c_away:.2f}"
    )

    pick_data = {
        "liga": nombre_liga,
        "home": home,
        "away": away,
        "cuota": empate,
        "fav": favorito,
    }

    return texto, pick_data


def main():
    # 1. Actualizar resultados pendientes
    actualizados = actualizar_resultados()
    if actualizados:
        for pick in actualizados:
            emoji = "✅" if pick["resultado"] == "W" else "❌"
            msg = (
                f"{emoji} <b>RESULTADO AUTOMÁTICO</b>\n"
                f"{pick['home']} vs {pick['away']}\n"
                f"X @ {pick['cuota']:.2f} → <b>{pick['resultado']}</b>  "
                f"({'+'if pick['profit'] > 0 else ''}{pick['profit']:.2f}u)"
            )
            send_telegram(msg)

        resumen = resumen_stats()
        if resumen:
            send_telegram(resumen)
            img = generar_grafica()
            if img:
                send_photo_telegram(img, "📊 Gráfica actualizada")

    # 2. Buscar nuevas alertas
    picks = cargar_picks()
    picks_hoy = [(p["home"], p["away"]) for p in picks
                 if p["fecha"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")]

    alertas = []
    nuevos_picks = []

    for liga in LIGAS:
        partidos = obtener_partidos(liga)
        nombre = NOMBRES_LIGAS.get(liga, liga)
        for partido in partidos:
            alerta, pick_data = analizar_partido(partido, nombre)
            if alerta and pick_data:
                key = (pick_data["home"], pick_data["away"])
                if key not in picks_hoy:
                    alertas.append(alerta)
                    nuevos_picks.append(pick_data)

    if alertas:
        for pd in nuevos_picks:
            picks.append({
                "id": len(picks) + 1,
                "fecha": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "liga": pd["liga"],
                "home": pd["home"],
                "away": pd["away"],
                "cuota": pd["cuota"],
                "fav": pd["fav"],
                "resultado": None,
                "profit": None,
            })
        guardar_picks(picks)
        commit_picks()

        cabecera = (
            f"🚨 <b>EMPATES DEL DÍA</b> — "
            f"{datetime.now(timezone.utc).strftime('%d/%m/%Y')}\n\n"
        )
        mensaje = cabecera + "\n\n".join(alertas)
        send_telegram(mensaje)
        print(f"{len(alertas)} alertas enviadas.")
    else:
        print("Sin alertas hoy.")


if __name__ == "__main__":
    main()
