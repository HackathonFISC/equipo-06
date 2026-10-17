# Inventario técnico — HIDRA — Reto 01 (HIDRO360)

> **Propósito.** Dejar constancia, **antes de tocar nada**, de qué hay en el repositorio, qué se conserva, qué se retira del control de versiones y con qué evidencia. Regla: **nada se borra del disco sin confirmación humana**; ninguna afirmación sin referencia verificada.
>
> Fecha de la revisión: **2026-10-17**. Base: `git ls-files` (archivos versionados) y `rg` (referencias en código y docs).

## Resumen

- **1720** archivos versionados en total.
- **1499** (≈ 97.4 MB) están en `.tools/pgnode/` — `node_modules` del paquete npm `embedded-postgres`, que `.gitignore` ya ignora (línea 95: `.tools/`). Se versionaron por error.
- **45** en `IMPLEMENTACIONES_EJEMPLO/` (laboratorio de IA, no producto).
- **2** en `proyecto_info/` (documentos de origen del reto).
- El resto (interfaz, servicios, pruebas, docs, firmware, despliegue) está en orden.

## Tabla de decisiones

| Ruta | Función | Referencias | Reemplazo | Decisión | Evidencia |
|---|---|---|---|---|---|
| `.tools/pgnode/` (1499 archivos, ≈ 97.4 MB) | `node_modules` del paquete npm `embedded-postgres` (PostgreSQL portátil para pruebas) | `scripts/postgres_prueba.py` (líneas 5–8, 52, 61) y `docs/BASE_DE_DATOS.md` (líneas 107–109) lo describen como **carpeta git-ignorada** que el usuario instala con `npm install embedded-postgres --prefix .tools/pgnode` | Ninguno: la carpeta se **reinstala** con ese comando. No hay código que dependa de que esté versionada | **Retirar del control de versiones** con `git rm -r --cached .tools` y **conservar en disco**. `.gitignore` línea 95 ya la excluye | `.gitignore:95` = `.tools/`; `git ls-files ".tools/*"` era 1499. **Ejecutado en esta revisión** (autorizado por el usuario): cambio **preparado (staged)**, sin commit ni push |
| `IMPLEMENTACIONES_EJEMPLO/` (45 archivos) | Laboratorio de IA generado a partir de la idea original (paquete `agua-clara-ai`) | `README.md` (sección Documentación, actualizada), `docs/IMPLEMENTACIONES_EJEMPLO.md` | Se **conserva** como evidencia del proceso; **no** se integra al producto | **Conservar y documentar** (no integrar). Ver `docs/IMPLEMENTACIONES_EJEMPLO.md` | Comparación por módulo en `docs/IMPLEMENTACIONES_EJEMPLO.md`; cubierto por `services/`, `evals/` propios |
| `proyecto_info/` (2 PDF) | Documentos de origen del reto (`Agua_Clara_AI_Guia_de_Programacion.pdf`, `..._Propuesta.pdf`) | Material de referencia, no código | — | **Conservar** | `git ls-files "proyecto_info/*"` = 2 |
| `docs/AUDITORIA_TECNICA.md` | Auditoría inicial (2026-10-16), estado previo a la evolución | Nada lo importa | `docs/INVENTARIO_TECNICO.md` (este) + `docs/ARQUITECTURA.md` | **Conservar como histórico** (ya lleva nota de histórico) | Nota «documento histórico» en el propio archivo |
| `docs/INVENTARIO_ARCHIVOS.md` | Inventario de la migración a Flet + Gemini (2026-10-16) | Nada lo importa | Este documento | **Conservar como histórico** | Nota «documento histórico»; cita rutas ya inexistentes (`interface/flet_app/pages/`) |
| `docs/GUION_VIDEO.md` | Guion del video de demo (no grabado) | `README.md` (Demostración) | `docs/GUIA_DEMO_EN_VIVO.md` para demo en vivo | **Conservar** (se mantiene para el video) | — |
| `.venv/` | Entorno virtual local de pruebas | — | — | **No versionado** (`.gitignore`) | `git check-ignore .venv` lo excluye |

## Referencias obsoletas a carpetas inexistentes (corregir texto, no borrar archivos)

Estas carpetas **no existen** en el árbol de trabajo (verificado con `Get-ChildItem`): `LOGO/`, `PROTOTIPO/`, `INFO DEL PROYECTO/`. Su contenido real vive en `assets/` (logo), `proyecto_info/` (PDF) y el prototipo no está en el repositorio.

| Archivo | Línea | Texto obsoleto | Corrección |
|---|---|---|---|
| `README.md` | Mapa del repositorio | «`LOGO/` logo original y `PROTOTIPO/` referencia visual» | Corregido en esta revisión |
| `AGENTS.md` | §2 | «original en `LOGO/` … `PROTOTIPO/` referencia visual HTML» | Corregido en esta revisión |
| `docs/DISENO_UI.md` | 3, 5, 9 | Afirmaba que `PROTOTIPO/` se restauró desde el respaldo | Corregido en esta revisión: el prototipo **no está** en el repositorio |
| `docs/DECISIONES.md` | 14 | Citaba `INFO DEL PROYECTO/` (ruta inexistente) | Corregido a `proyecto_info/` en esta revisión |
| `docs/API.md` | 10–11 | Presentaba `AGUA_CLARA_*` como nombre principal de los tokens | Corregido en esta revisión a `HIDRO360_*` (alias obsoleto) |
| `docs/HARDWARE.md` | 143 | Decía `AGUA_CLARA_API_TOKEN`/`AGUA_CLARA_DEVICE_TOKEN` | Corregido en esta revisión a `HIDRO360_*` |
| `docs/AUDITORIA_TECNICA.md`, `docs/INVENTARIO_ARCHIVOS.md` | varias | Citan `INFO DEL PROYECTO/`, `LOGO/`, `PROTOTIPO/` | **Conservar**: son documentos **históricos** (llevan su nota) |

> **Nota:** la corrección es de **texto**. No se elimina ni restaura ninguna carpeta: no hay evidencia en el repositorio de que `PROTOTIPO/` deba existir.

## Duplicaciones documentales (consolidar, no borrar)

| Tema | Documentos que lo repiten | Acción propuesta |
|---|---|---|
| Reparto Supabase + Vercel + UI Flet | `docs/ARQUITECTURA.md`, `docs/DESPLIEGUE.md` | El detalle vive en `DESPLIEGUE.md`; `ARQUITECTURA.md` solo lo resume |
| Procedimiento Raspberry Pi | `docs/INSTALACION.md` §9, `docs/HARDWARE.md` §9, `README.md` | Detalle en `INSTALACION.md` §9 |
| Tabla de variables de entorno | `docs/INSTALACION.md`, `docs/DESPLIEGUE.md`, `README.md` | La autoritativa es `.env.example` |

## Estado de la limpieza

1. **`git rm -r --cached .tools`** — **ejecutado** (autorizado por el usuario): retira 1499 archivos del índice de Git y los conserva en disco (`.tools/pgnode/node_modules` sigue existiendo). Cambio **preparado (staged)**, sin commit ni push.
2. Borrar archivos del disco — **ninguno**.
3. `git commit`, `git push`, despliegue, migración remota o tag — **ninguno** (pendiente de confirmación).

## Cómo verificar este inventario

```bash
git ls-files | wc -l                                   # total versionado
git ls-files ".tools/*" | wc -l                        # 1499
git ls-files "IMPLEMENTACIONES_EJEMPLO/*" | wc -l      # 45
git check-ignore -v .tools/pgnode/x.txt                # confirma .gitignore:95
```
