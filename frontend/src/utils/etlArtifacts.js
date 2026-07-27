/**
 * Normaliza `etl.result` al contrato D20 (`etapas`/`kjb_master`, sin los
 * slots viejos `ktr_xml`/`ktr2_xml`/`kjb_xml` — ver docs/refactor/02-decisiones.md).
 * Único punto de lectura de esas claves en el frontend; todo consumidor
 * (etlCardActions, EtlDetail, EtlCardMenu, etlImport) pasa por acá en vez de
 * leer `result` a mano.
 *
 * Sin dependencias de React ni JSZip — testeable en Node puro.
 */

function safeSlug(name) {
  return (name ?? "etapa").replace(/[^a-z0-9_-]/gi, "_").toLowerCase();
}

/**
 * @param {object|null|undefined} result
 * @returns {
 *   { status: "ok", etapas: Array<{nombre:string, tipo:"ktr"|"kjb", split:boolean, kjb:object|null, files:object[]}>,
 *     master: object|null, files: object[], splitEtapas: object[], message: null }
 *   | { status: "legacy"|"none", etapas: [], master: null, files: [], splitEtapas: [], message: string }
 * }
 */
export function readEtlArtifacts(result) {
  const empty = { etapas: [], master: null, files: [], splitEtapas: [] };

  if (result == null) {
    return { status: "none", ...empty, message: "El proceso no generó archivos .ktr — revisar el resultado." };
  }

  if (Array.isArray(result.etapas) && result.etapas.length > 0) {
    const seenNombres = new Map();
    const etapas = result.etapas.map((etapa, i) => {
      let nombre = etapa.nombre || `etapa_${i + 1}`;
      const count = seenNombres.get(nombre) ?? 0;
      seenNombres.set(nombre, count + 1);
      if (count > 0) nombre = `${nombre}-${count + 1}`;

      const split = etapa.tipo === "kjb";
      return {
        nombre,
        tipo: etapa.tipo,
        split,
        kjb: split ? (etapa.kjb ?? null) : null,
        files: split ? (etapa.archivos ?? []) : (etapa.archivo ? [etapa.archivo] : []),
      };
    });

    const master = result.kjb_master ?? null;
    const files = [
      ...etapas.flatMap(e => (e.split ? [...e.files, e.kjb] : e.files)),
      ...(master ? [master] : []),
    ].filter(Boolean);

    return {
      status: "ok",
      etapas,
      master,
      files,
      splitEtapas: etapas.filter(e => e.split),
      message: null,
    };
  }

  // Shape viejo: presencia de clave, no truthiness — un build fallido viejo
  // trae ktr_xml:"" y con Boolean() se confunde con "no generó nada".
  if ("ktr_xml" in result || "ktr2_xml" in result || "kjb_xml" in result) {
    return {
      status: "legacy",
      ...empty,
      message: "Este ETL se generó con un formato anterior. Volvé a generarlo para poder descargar los archivos.",
    };
  }

  return { status: "none", ...empty, message: "El proceso no generó archivos .ktr — revisar el resultado." };
}

/**
 * Aplana un resultado "ok" a entradas de ZIP {path, content} — D20-punto4:
 * etapa simple -> archivo suelto en la raíz; etapa partida -> sus N archivos
 * en una carpeta nombrada por la etapa, su .kjb intermedio expuesto en la
 * raíz junto al maestro. Sin ninguna etapa partida, todos los paths quedan
 * sin "/" (ZIP plano, UX idéntica a antes de F3).
 *
 * @param {ReturnType<typeof readEtlArtifacts>} art
 * @returns {Array<{path:string, content:string}>}
 */
export function buildZipEntries(art) {
  const entries = [];
  for (const etapa of art.etapas) {
    if (etapa.split) {
      const folder = safeSlug(etapa.nombre);
      for (const f of etapa.files) entries.push({ path: `${folder}/${f.filename}`, content: f.xml });
      if (etapa.kjb) entries.push({ path: etapa.kjb.filename, content: etapa.kjb.xml });
    } else {
      for (const f of etapa.files) entries.push({ path: f.filename, content: f.xml });
    }
  }
  if (art.master) entries.push({ path: art.master.filename, content: art.master.xml });
  return entries;
}
