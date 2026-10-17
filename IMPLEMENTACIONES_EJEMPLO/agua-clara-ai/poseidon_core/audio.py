"""poseidon_core.audio · análisis acústico pasivo de tuberías y grifos.

Idea hidráulica
---------------
Cuando una tubería residencial tiene agua circulando, el sonido dominante es
un rumor grave (< 600 Hz). Cuando NO hay agua pero la red sigue presurizada,
el aire comprimido escapa por el grifo como un siseo de banda ancha (ruido
blanco) con energía concentrada en frecuencias altas (> 1500 Hz). Un corte
total sin presión produce silencio.

Detección
---------
1. Se carga el audio (librosa si está disponible; si no, el módulo estándar
   ``wave`` para WAV; si no, ``soundfile``).
2. Se trocea en ventanas de 1 segundo y se calcula, por ventana, el **Centroide
   Espectral**, la **Energía RMS** y la **proporción de energía en banda alta**.
3. Se busca una racha de ventanas con perfil de "aire" (banda alta dominante y
   energía suficiente). Si existe, se marca el segundo exacto de inicio.

Todo el cálculo es determinista (FFT con numpy). No se inventa nada: si el
audio no se puede leer, se devuelve un diccionario de error explícito.
"""
from __future__ import annotations

import os
import tempfile
import wave
from typing import Any, Dict, List, Optional, Tuple

# numpy es el único requisito duro del análisis espectral; sin él degradamos.
try:  # pragma: no cover - depende del entorno
    import numpy as _np
    _NUMPY = True
except Exception:  # pragma: no cover
    _np = None  # type: ignore
    _NUMPY = False

try:  # librosa aporta decodificación universal (ogg/mp3/m4a)
    import librosa as _librosa  # type: ignore
    _LIBROSA = True
except Exception:  # pragma: no cover
    _librosa = None  # type: ignore
    _LIBROSA = False

try:
    import soundfile as _sf  # type: ignore
    _SOUNDFILE = True
except Exception:  # pragma: no cover
    _sf = None  # type: ignore
    _SOUNDFILE = False


# ----------------------------- parámetros hidráulicos -----------------------------

UMBRAL_HZ_DEFECTO: float = 1500.0   # frontera grave (agua) / agudo (aire)
RMS_MINIMO: float = 0.010           # por debajo de esto consideramos silencio
RATIO_BANDA_ALTA_MIN: float = 0.50  # el aire concentra >50% de energía arriba
MIN_VENTANAS_AIRE: int = 2          # racha mínima para declarar "aire"
VENTANA_SEG_DEFECTO: float = 1.0
SR_DEFECTO: int = 22050


# ----------------------------- carga de audio -----------------------------

def _cargar_wav_estandar(path: str) -> Tuple["_np.ndarray", int]:
    """Lee un WAV PCM con el módulo estándar y lo devuelve como float32 mono."""
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n_canales = w.getnchannels()
        ancho = w.getsampwidth()
        frames = w.readframes(w.getnframes())
    if ancho == 2:
        import array
        a = array.array("h")
        a.frombytes(frames)
        data = _np.asarray(a, dtype=_np.float32) / 32768.0
    elif ancho == 1:
        data = (_np.frombuffer(frames, dtype=_np.uint8).astype(_np.float32) - 128.0) / 128.0
    elif ancho == 4:
        data = _np.frombuffer(frames, dtype=_np.int32).astype(_np.float32) / 2147483648.0
    else:
        raise ValueError(f"Ancho de muestra no soportado: {ancho} bytes")
    if n_canales > 1:
        data = data.reshape(-1, n_canales).mean(axis=1)
    return data.astype(_np.float32), int(sr)


def _cargar_audio(file_path: str, sr: int = SR_DEFECTO) -> Tuple["_np.ndarray", int, str]:
    """Carga audio con la mejor herramienta disponible. Devuelve (señal, sr, método)."""
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"No existe el archivo de audio: {file_path}")
    if _LIBROSA:
        try:
            y, s = _librosa.load(file_path, sr=sr, mono=True)
            return _np.asarray(y, dtype=_np.float32), int(s), "librosa"
        except Exception:
            pass
    if _SOUNDFILE:
        try:
            y, s = _sf.read(file_path, always_2d=False)
            y = _np.asarray(y, dtype=_np.float32)
            if y.ndim > 1:
                y = y.mean(axis=1)
            return y, int(s), "soundfile"
        except Exception:
            pass
    if file_path.lower().endswith(".wav"):
        y, s = _cargar_wav_estandar(file_path)
        return y, s, "wave"
    raise RuntimeError(
        "No hay decodificador para este formato (instala `librosa` o `soundfile`, "
        "o envía un WAV)."
    )


# ----------------------------- análisis espectral -----------------------------

def _analizar_ventana(frame: "_np.ndarray", sr: int, umbral_hz: float) -> Dict[str, Any]:
    """Centroide espectral, RMS, banda alta y planitud de UNA ventana."""
    frame = frame - float(_np.mean(frame))
    n = len(frame)
    if n == 0:
        return {"centroide_hz": 0.0, "rms": 0.0, "ratio_alta": 0.0, "flatness": 0.0}
    ventana = _np.hanning(n)
    spec = _np.abs(_np.fft.rfft(frame * ventana))
    freqs = _np.fft.rfftfreq(n, 1.0 / sr)
    total = float(_np.sum(spec)) + 1e-12
    centroide = float(_np.sum(freqs * spec) / total)
    rms = float(_np.sqrt(_np.mean(frame ** 2)))
    alta = float(_np.sum(spec[freqs >= umbral_hz]) / total)

    # Planitud (geometric mean / arithmetic mean) solo sobre bins con energía
    # relevante, para que los ceros del filtrado no la hundan artificialmente.
    pico = float(_np.max(spec)) if spec.size else 0.0
    mask = spec > (0.01 * pico) if pico > 0 else spec > 0
    if bool(_np.any(mask)):
        ps = spec[mask] ** 2 + 1e-12
        flatness = float(_np.exp(_np.mean(_np.log(ps))) / _np.mean(ps))
    else:
        flatness = 0.0
    return {
        "centroide_hz": round(centroide, 1),
        "rms": round(rms, 5),
        "ratio_alta": round(alta, 4),
        "flatness": round(min(max(flatness, 0.0), 1.0), 4),
    }


def _estado_texto(estado: str) -> str:
    return {
        "aire": "Aire en tubería (no hay agua circulando)",
        "flujo_normal": "Flujo normal (agua circulando)",
        "seco": "Silencio: sin flujo detectado (posible corte o toma cerrada)",
        "desconocido": "No se pudo determinar el estado hidráulico",
    }.get(estado, estado)


def analizar_espectro_grifo(file_path: str, ventana_seg: float = VENTANA_SEG_DEFECTO,
                            umbral_hz: float = UMBRAL_HZ_DEFECTO) -> Dict[str, Any]:
    """Analiza el sonido de un grifo/tubería y clasifica el estado hidráulico.

    Args:
        file_path: ruta local del audio (WAV, y con librosa/soundfile: ogg, mp3, m4a).
        ventana_seg: tamaño de ventana en segundos (por defecto 1.0).
        umbral_hz: frontera grave/agudo para separar agua de aire (por defecto 1500 Hz).

    Returns:
        dict con: ``archivo``, ``duracion_seg``, ``sr``, ``metodo``,
        ``grifo_detectado``, ``segundo_inicio``, ``confianza``, ``estado``
        (``aire`` | ``flujo_normal`` | ``seco`` | ``desconocido``),
        ``estado_inferido`` (texto), ``centroide_medio_hz``, ``ratio_alta_medio``,
        ``segmentos`` (lista) y ``errores`` (lista).
    """
    resultado: Dict[str, Any] = {
        "archivo": file_path, "duracion_seg": 0.0, "sr": 0, "metodo": None,
        "ventana_seg": ventana_seg, "umbral_hz": umbral_hz,
        "grifo_detectado": False, "segundo_inicio": 0, "confianza": 0.0,
        "estado": "desconocido", "estado_inferido": _estado_texto("desconocido"),
        "centroide_medio_hz": 0.0, "ratio_alta_medio": 0.0, "rms_medio": 0.0,
        "segmentos": [], "errores": [],
    }

    if not _NUMPY:
        resultado["errores"].append("numpy no está instalado; el análisis espectral requiere numpy.")
        return resultado

    try:
        y, sr, metodo = _cargar_audio(file_path)
    except Exception as exc:  # noqa: BLE001 - queremos cualquier fallo aquí
        resultado["errores"].append(str(exc))
        return resultado

    if y is None or len(y) == 0:
        resultado["errores"].append("Audio vacío.")
        return resultado

    resultado["sr"] = sr
    resultado["metodo"] = metodo
    resultado["duracion_seg"] = round(len(y) / float(sr), 2)

    win = max(1, int(ventana_seg * sr))
    hop = max(1, win // 2)  # 50% de solapamiento
    segmentos: List[Dict[str, Any]] = []
    idx = 0
    start = 0
    while start + win <= len(y):
        analisis = _analizar_ventana(y[start:start + win], sr, umbral_hz)
        analisis.update({
            "indice": idx,
            "inicio_seg": round(start / float(sr), 2),
            "es_aire": bool(analisis["ratio_alta"] >= RATIO_BANDA_ALTA_MIN and analisis["rms"] >= RMS_MINIMO),
        })
        segmentos.append(analisis)
        idx += 1
        start += hop

    if not segmentos:  # audio más corto que una ventana: analizamos todo el bloque
        analisis = _analizar_ventana(y, sr, umbral_hz)
        analisis.update({"indice": 0, "inicio_seg": 0.0,
                         "es_aire": bool(analisis["ratio_alta"] >= RATIO_BANDA_ALTA_MIN and analisis["rms"] >= RMS_MINIMO)})
        segmentos.append(analisis)

    activos = [s for s in segmentos if s["rms"] >= RMS_MINIMO]
    aire = [s for s in activos if s["es_aire"]]
    confianza = round(len(aire) / len(activos), 3) if activos else 0.0

    # Racha de aire más larga y su segundo de inicio.
    mejor_racha = 0
    racha = 0
    primer_segundo = 0
    for s in segmentos:
        if s["es_aire"]:
            if racha == 0:
                primer_segundo = int(s["inicio_seg"])
            racha += 1
            if racha > mejor_racha:
                mejor_racha = racha
        else:
            racha = 0

    grifo_detectado = mejor_racha >= MIN_VENTANAS_AIRE and confianza >= 0.40
    if grifo_detectado:
        estado = "aire"
    elif not activos:
        estado = "seco"
    else:
        estado = "flujo_normal"

    resultado.update({
        "grifo_detectado": bool(grifo_detectado),
        "segundo_inicio": int(primer_segundo if grifo_detectado else 0),
        "confianza": confianza,
        "estado": estado,
        "estado_inferido": _estado_texto(estado),
        "centroide_medio_hz": round(sum(s["centroide_hz"] for s in segmentos) / len(segmentos), 1),
        "ratio_alta_medio": round(sum(s["ratio_alta"] for s in segmentos) / len(segmentos), 4),
        "rms_medio": round(sum(s["rms"] for s in segmentos) / len(segmentos), 5),
        "segmentos": segmentos[:120],  # acotado para que la API no se sature
    })
    return resultado


# ----------------------------- generador de muestras -----------------------------

def _filtrar_banda(x: "_np.ndarray", sr: int, low: Optional[float] = None,
                   high: Optional[float] = None) -> "_np.ndarray":
    """Filtro pasa-banda elemental en el dominio de la frecuencia (determinista)."""
    X = _np.fft.rfft(x)
    f = _np.fft.rfftfreq(len(x), 1.0 / sr)
    if low is not None:
        X[f < low] = 0
    if high is not None:
        X[f > high] = 0
    return _np.fft.irfft(X, n=len(x))


def _normalizar_rms(x: "_np.ndarray", objetivo: float) -> "_np.ndarray":
    rms = float(_np.sqrt(_np.mean(x ** 2))) + 1e-12
    return x * (objetivo / rms)


def sintetizar_muestra(estado: str = "aire", segundos: float = 6.0, sr: int = SR_DEFECTO,
                       destino: Optional[str] = None) -> str:
    """Genera un WAV sintético y determinista que imita un estado hidráulico.

    Sirve para demostrar y evaluar el sistema sin necesidad de grabaciones
    reales. ``estado`` ∈ {``aire``, ``flujo_normal``, ``seco``}.
    """
    if not _NUMPY:
        raise RuntimeError("Se requiere numpy para sintetizar muestras.")
    n = int(segundos * sr)
    rng = _np.random.default_rng(20260117)  # semilla fija -> reproducible en evals
    t = _np.arange(n) / float(sr)
    ruido = rng.standard_normal(n).astype(_np.float32)

    if estado == "aire":
        # Siseo de banda ancha concentrado en agudos + leve modulación de presión.
        x = _filtrar_banda(ruido, sr, low=1600.0)
        x = _normalizar_rms(x, 0.20)
        x = x * (1.0 + 0.25 * _np.sin(2 * _np.pi * 3.0 * t))
    elif estado == "flujo_normal":
        # Rumor grave del agua en movimiento + armónico de baja frecuencia.
        x = _filtrar_banda(ruido, sr, high=600.0)
        x = _normalizar_rms(x, 0.18)
        x = x + 0.05 * _np.sin(2 * _np.pi * 110.0 * t)
    elif estado == "seco":
        # Prácticamente silencio (por debajo del umbral de energía).
        x = ruido * 0.002
    else:
        raise ValueError(f"Estado no soportado: {estado!r}. Usa 'aire', 'flujo_normal' o 'seco'.")
    x = _np.clip(x, -1.0, 1.0)

    if destino is None:
        dest_dir = os.path.join(tempfile.gettempdir(), "poseidon_audio")
        os.makedirs(dest_dir, exist_ok=True)
        destino = os.path.join(dest_dir, f"muestra_{estado}.wav")
    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)

    pcm = (_np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(destino, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return destino
