"""Orquestador — el grafo de estado que conecta los agentes.

Flujo:
  Reporte ciudadano
    -> A1 Ingesta           (LLM + guardrails)      -> Report validado
    -> A2 Geo + Dedup       (catálogo + similitud)  -> sector y duplicados
    -> [se guarda en SQLite — herramienta que actúa]
  Al pedir plan:
    -> A3 Estimador         (posterior por sector)  -> p_cut
    -> A4 Prioridad         (pesos visibles)        -> orden
    -> A5 Planificador      (solver determinista)   -> Plan
  Al aprobar:
    -> A8 Supervisión       (humano)                -> decisión + auditoría
    -> A7 Comunicación      (solo si se aprueba)    -> aviso enviado/outbox

Cada paso registra una traza (run_id, agente, herramientas, decisión).
"""
from __future__ import annotations

from services import catalog, memory, storage
from services.traces import log_step, new_run_id
from schemas import DeliveryEvidence, Report
from agents import (communication, consensus, estimator, geolocation, intake, location_resolver,
                    planner, prioritization, supervisor, typo_normalizer, verification,
                    whatsapp_gateway)
from services.metrics import gini, deprivation


def process_report(raw_text: str, channel: str = "texto", sender: str | None = None,
                   media_path: str | None = None, media_base64: str | None = None,
                   media_mime: str | None = None, media_name: str | None = None,
                   media_kind: str | None = None, gps: dict | None = None,
                   run_id: str | None = None, **kw) -> dict:
    run_id = run_id or new_run_id()

    # A1b · Normalizador de escritura y jerga panameña
    norm = typo_normalizer.normalize(raw_text or "", run_id)
    text_for_parse = norm["text"] or (raw_text or "")

    # A1 · Ingesta (incluye enriquecimiento multimodal: imagen/audio/vídeo)
    report: Report = intake.parse(
        text_for_parse,
        channel=channel,
        sender=sender,
        run_id=run_id,
        media_path=media_path,
        media_base64=media_base64,
        media_mime=media_mime,
        **kw,
    )

    # Metadatos de la capa de agentes nuevos
    report.meta.update({
        "channel": channel,
        "original_text": raw_text,
        "normalizacion": {
            "correcciones": norm["corrections"],
            "calidad_texto": norm["quality"],
            "sospechoso": norm["suspicious"],
            "jerga": norm["slang"],
        },
    })
    if media_kind or media_path:
        report.meta["media"] = {"kind": media_kind, "mime": media_mime, "name": media_name}
    if gps:
        report.meta["gps"] = gps

    # Si el tipo quedó en "otro" pero la jerga dice otra cosa, la jerga manda.
    from schemas import IncidentType
    if norm["slang"] and report.incident_type == IncidentType.OTRO:
        try:
            report.incident_type = IncidentType(norm["slang"][0]["intent"])
        except ValueError:
            pass

    # A2b · Ubicación (incluye A2 y GPS) + A2 dedup + A9 consenso
    if not report.out_of_scope:
        report = location_resolver.resolve(report, run_id)
        report = geolocation.deduplicate(report, storage.list_reports(), run_id)
        consensus.index_report(report, storage.list_reports(), run_id)

    # Persistencia (herramienta que actúa)
    storage.insert_report(report.model_dump(mode="json"))
    storage.audit("sistema", "reporte_registrado",
                  {"id": report.id, "sector_id": report.sector_id, "status": report.status,
                   "channel": channel})
    log_step(run_id, "Orquestador", "reporte_guardado", {"id": report.id}, {"status": report.status},
             tools=["sqlite_insert"])
    return {"run_id": run_id, "report": report.model_dump(mode="json")}


def process_whatsapp(payload: dict, run_id: str | None = None) -> dict:
    """A0 -> pipeline completo. Procesa cada mensaje del webhook de WhatsApp."""
    run_id = run_id or new_run_id()
    incoming = whatsapp_gateway.parse_webhook(payload, run_id)
    resultados = []
    for msg in incoming:
        media = [whatsapp_gateway.download_media(m) for m in msg.media]
        first = media[0] if media else None
        res = process_report(
            msg.text, channel="whatsapp", sender=msg.sender, run_id=run_id,
            media_path=(first.url if first and first.downloaded else None),
            media_mime=(first.mime if first else None),
            media_name=(first.name if first else None),
            media_kind=(first.kind if first else None),
            gps=msg.location,
        )
        rpt = res["report"]
        # Cierre conversacional: si falta la ubicación, se pregunta de vuelta.
        reply_id = None
        q = (rpt.get("meta") or {}).get("clarify_question")
        if (rpt.get("meta") or {}).get("needs_clarification") and q:
            reply_id = whatsapp_gateway.queue_reply(msg.sender, q)
        resultados.append({
            "message": msg.model_dump(mode="json"),
            "media": [m.model_dump(mode="json") for m in media],
            "report": rpt,
            "reply_id": reply_id,
            "reply": q if reply_id else None,
        })
    return {"run_id": run_id, "mensajes": len(incoming), "resultados": resultados}


def confirm_report(report_id: str, **fields) -> dict:
    """Confirma un reporte y APRENDE de la corrección (memoria de los agentes)."""
    report = storage.get_report(report_id)
    storage.update_report(report_id, status="confirmado", **{k: v for k, v in fields.items() if v is not None})
    storage.audit("operador", "reporte_confirmado", {"id": report_id, "fields": fields})

    # Entrenamiento continuo: el texto/hint que causaba ambigüedad ahora resuelve.
    if report:
        sector_id = fields.get("sector_id") or report.get("sector_id")
        hint = (report.get("sector_hint") or report.get("raw_text") or "").strip()
        if sector_id and hint and report.get("status") == "pendiente_confirmacion":
            memory.learn_resolution(hint[:140], sector_id, origin="confirmacion_humana")
            storage.audit("sistema", "aprendizaje_alias", {"sector_id": sector_id, "hint": hint[:140]})
    return storage.get_report(report_id)


def build_plan(method: str = "social") -> dict:
    run_id = new_run_id()
    sectors = catalog.sectors()
    reports = storage.list_reports(limit=500)

    estimates = estimator.estimate(sectors, reports, run_id)
    priorities = prioritization.rank(sectors, estimates, run_id)
    plan = planner.build(priorities, method=method, run_id=run_id)

    # Métricas de equidad calculadas sobre lo que el plan REALMENTE atiende:
    # un sector bien cubierto sale del conteo de privación; uno postergado acumula
    # más horas (horizonte de otro turno). Así los métodos se diferencian de verdad.
    served_liters: dict[str, int] = {}
    for a in plan.assignments:
        served_liters[a.sector_id] = served_liters.get(a.sector_id, 0) + a.liters

    from services.metrics import SPHERE_MIN_LITERS_PER_PERSON as SPHERE_MIN
    horizon_hours = 6.0
    hours_after, pops_after = [], []
    for s in sectors:
        demand = s.population * SPHERE_MIN
        coverage = min(1.0, served_liters.get(s.id, 0) / demand) if demand > 0 else 1.0
        h = (s.hours_without_water + horizon_hours) * (1 - coverage)
        hours_after.append(h)
        pops_after.append(s.population)

    plan.metrics["gini_hours_without_water"] = round(gini(hours_after, pops_after), 4)
    plan.metrics["deprivation_total"] = round(
        sum(deprivation(h, s.population, s.vulnerability, s.hourly_deprivation_weight)
            for h, s in zip(hours_after, sectors)), 1)
    plan.metrics["mean_hours_after"] = round(sum(hours_after) / len(hours_after), 2)

    storage.insert_plan(plan.model_dump(mode="json"))
    storage.audit("sistema", "plan_propuesto", {"plan_id": plan.id, "method": method, "metrics": plan.metrics})
    return {"run_id": run_id, "plan": plan.model_dump(mode="json"),
            "priorities": [p.model_dump(mode="json") for p in priorities],
            "sampling": estimator.sampling_targets(sectors, estimates)}


def compare_methods() -> dict:
    """Compara el método social con la línea base 'por número de quejas'."""
    social = build_plan("social")["plan"]
    baseline = build_plan("quejas")["plan"]
    return {
        "social": {"metrics": social["metrics"], "explanation": social["explanation"]},
        "baseline_quejas": {"metrics": baseline["metrics"], "explanation": baseline["explanation"]},
    }


def decide_plan(payload: dict) -> dict:
    from schemas import Assignment, Decision
    decision = Decision(
        plan_id=payload["plan_id"], action=payload["action"], operator=payload.get("operator", "coordinador"),
        reason=payload.get("reason", ""),
        changes=[Assignment(**c) for c in payload.get("changes", [])],
    )
    result = supervisor.decide(decision)
    if result.get("ok") and decision.action in ("aprobar", "editar"):
        plan = storage.get_plan(decision.plan_id)
        if plan:
            sent = []
            for a in plan["assignments"]:
                body = communication.draft(a["sector_name"], a["liters"], a.get("eta_minutes"))
                sent.append(communication.send("outbox", a["sector_id"], body))
            result["notices"] = len(sent)
    return result


def simulate_delivery(payload: dict) -> dict:
    ev = DeliveryEvidence(**payload)
    verdict = verification.verify(ev)
    storage.insert_delivery({"plan_id": payload.get("plan_id"), "sector_id": ev.sector_id,
                             "tanker_id": ev.tanker_id, "status": verdict.status, "checks": verdict.checks})
    if verdict.status != "confirmada":
        storage.audit("sistema", "entrega_con_evidencia", {"sector_id": ev.sector_id,
                                                           "status": verdict.status, "reasons": verdict.reasons})
    return verdict.model_dump(mode="json")
