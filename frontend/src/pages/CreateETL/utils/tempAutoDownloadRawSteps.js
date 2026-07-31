/**
 * TEMPORAL — descarga automática de los steps YA REPARADOS (post
 * normalize_step_configs/repair_ktr_steps/repair_integrity_gaps, ver
 * etl_generator.py:_stage_pipeline) apenas ambas etapas llegan del backend
 * durante el polling de /status. Objetivo: juntar corpus para comparar
 * corridas y reusar vía reuse_stage_1 (D31) sin gastar tokens del modelo.
 *
 * No agrega persistencia nueva (ni backend ni DB): reusa el mismo
 * downloadLlmRaw() que ya dispara el botón manual del drawer (D33,
 * docs/refactor/02-decisiones.md). El único estado propio es
 * downloadedJobIdsRef, para no re-disparar la descarga en cada tick del
 * poll una vez que ya bajó el archivo de ese job.
 *
 * Para sacar esta feature: borrar este archivo y las 2 referencias a
 * "tempAutoDownloadRawSteps" en CreateETL.jsx (el useRef y la llamada en
 * _pollJobStatus). No toca nada más.
 */
import { downloadLlmRaw } from "@/utils/etlExport";

export function tryAutoDownloadRawSteps({ stagesMap, jobId, etlName, downloadedJobIdsRef }) {
  const data1 = stagesMap?.origen_stg?.data;
  const data2 = stagesMap?.stg_dwh?.data;
  if (!data1 || !data2) return;
  if (!jobId || downloadedJobIdsRef.current.has(jobId)) return;

  downloadedJobIdsRef.current.add(jobId);
  downloadLlmRaw({ ktr_1: data1, ktr_2: data2 }, etlName);
}
