import { describe, it, expect } from "vitest";
import { readEtlArtifacts, buildZipEntries } from "./etlArtifacts";

const archivo = (filename) => ({ xml: `<xml>${filename}</xml>`, filename });

// Fixtures espejo de backend/tests/test_etl_generate_response_shape.py —
// mismas 4 combinaciones de D20-punto3, para que este test falle si el
// backend cambia el shape (D13: "test del contrato hacia la fase siguiente").

function etapaKtr(nombre, filename) {
  return { tipo: "ktr", nombre, archivo: archivo(filename), kjb: null, archivos: [] };
}

function etapaKjb(nombre, kjbFilename, archivoFilenames) {
  return {
    tipo: "kjb",
    nombre,
    archivo: null,
    kjb: archivo(kjbFilename),
    archivos: archivoFilenames.map(archivo),
  };
}

describe("readEtlArtifacts", () => {
  it("shape nuevo: 2 etapas simples + master -> ok", () => {
    const result = {
      etapas: [etapaKtr("origen_stg", "ktr1.ktr"), etapaKtr("stg_dwh", "ktr2.ktr")],
      kjb_master: archivo("proceso.kjb"),
    };
    const art = readEtlArtifacts(result);
    expect(art.status).toBe("ok");
    expect(art.etapas).toHaveLength(2);
    expect(art.splitEtapas).toHaveLength(0);
    expect(art.master.filename).toBe("proceso.kjb");
    expect(art.files.map(f => f.filename)).toEqual(["ktr1.ktr", "ktr2.ktr", "proceso.kjb"]);
  });

  it("shape nuevo: caso (b) una etapa kjb con N archivos -> split", () => {
    const result = {
      etapas: [
        etapaKtr("origen_stg", "ktr1.ktr"),
        etapaKjb("stg_dwh", "stg_dwh_sub.kjb", ["stg_dwh_1.ktr", "stg_dwh_2.ktr"]),
      ],
      kjb_master: archivo("proceso.kjb"),
    };
    const art = readEtlArtifacts(result);
    expect(art.status).toBe("ok");
    expect(art.splitEtapas).toHaveLength(1);
    const split = art.splitEtapas[0];
    expect(split.nombre).toBe("stg_dwh");
    expect(split.files.map(f => f.filename)).toEqual(["stg_dwh_1.ktr", "stg_dwh_2.ktr"]);
    expect(split.kjb.filename).toBe("stg_dwh_sub.kjb");
  });

  it("flujo monolítico: 1 etapa, sin kjb_master -> ok, master null", () => {
    const result = { etapas: [etapaKjb("proceso", "sub.kjb", ["a.ktr", "b.ktr"])], kjb_master: null };
    const art = readEtlArtifacts(result);
    expect(art.status).toBe("ok");
    expect(art.master).toBeNull();
    expect(art.etapas).toHaveLength(1);
  });

  it("shape viejo (ktr_xml/kjb_xml) -> legacy", () => {
    const art = readEtlArtifacts({ ktr_xml: "<xml/>", ktr_filename: "a.ktr", kjb_xml: "<xml/>" });
    expect(art.status).toBe("legacy");
    expect(art.message).toMatch(/formato anterior/i);
  });

  it("shape viejo con ktr_xml vacío (build fallido) -> legacy, no none", () => {
    // Detección por presencia de clave, no truthiness — un Boolean(ktr_xml)
    // confundiría este caso con "no generó nada" y el mensaje sería el equivocado.
    const art = readEtlArtifacts({ ktr_xml: "", ktr_filename: "" });
    expect(art.status).toBe("legacy");
  });

  it("result null -> none", () => {
    expect(readEtlArtifacts(null).status).toBe("none");
    expect(readEtlArtifacts(undefined).status).toBe("none");
  });

  it("result sin etapas ni claves viejas (build fallido nuevo) -> none", () => {
    const art = readEtlArtifacts({ proceso_etl: { nombre: "x" }, etapas: [] });
    expect(art.status).toBe("none");
    expect(art.message).toMatch(/no generó archivos/i);
  });

  it("etapa sin nombre -> fallback por índice, no 'undefined'", () => {
    const result = {
      etapas: [{ tipo: "ktr", archivo: archivo("a.ktr"), kjb: null, archivos: [] }],
      kjb_master: null,
    };
    const art = readEtlArtifacts(result);
    expect(art.etapas[0].nombre).toBe("etapa_1");
  });
});

describe("buildZipEntries", () => {
  it("caso (d) ninguna partida -> ZIP plano, ningún path con '/'", () => {
    const art = readEtlArtifacts({
      etapas: [etapaKtr("origen_stg", "ktr1.ktr"), etapaKtr("stg_dwh", "ktr2.ktr")],
      kjb_master: archivo("proceso.kjb"),
    });
    const entries = buildZipEntries(art);
    expect(entries.map(e => e.path)).toEqual(["ktr1.ktr", "ktr2.ktr", "proceso.kjb"]);
    expect(entries.every(e => !e.path.includes("/"))).toBe(true);
  });

  it("caso (b) solo origen_stg partida -> sus N .ktr y su .kjb, co-ubicados en la carpeta", () => {
    const art = readEtlArtifacts({
      etapas: [
        etapaKjb("origen_stg", "origen_stg_sub.kjb", ["a.ktr", "b.ktr"]),
        etapaKtr("stg_dwh", "ktr2.ktr"),
      ],
      kjb_master: archivo("proceso.kjb"),
    });
    const entries = buildZipEntries(art);
    expect(entries.map(e => e.path)).toEqual([
      "origen_stg/a.ktr",
      "origen_stg/b.ktr",
      "origen_stg/origen_stg_sub.kjb",
      "ktr2.ktr",
      "proceso.kjb",
    ]);
  });

  it("caso (a) ambas partidas -> dos carpetas, cada .kjb orquestador junto a sus .ktr, maestro en la raíz", () => {
    const art = readEtlArtifacts({
      etapas: [
        etapaKjb("origen_stg", "origen_stg_sub.kjb", ["a.ktr", "b.ktr"]),
        etapaKjb("stg_dwh", "stg_dwh_sub.kjb", ["c.ktr", "d.ktr"]),
      ],
      kjb_master: archivo("proceso.kjb"),
    });
    const entries = buildZipEntries(art);
    const paths = entries.map(e => e.path);
    expect(paths).toEqual([
      "origen_stg/a.ktr", "origen_stg/b.ktr", "origen_stg/origen_stg_sub.kjb",
      "stg_dwh/c.ktr", "stg_dwh/d.ktr", "stg_dwh/stg_dwh_sub.kjb",
      "proceso.kjb",
    ]);
    const kjbAtRoot = paths.filter(p => p.endsWith(".kjb") && !p.includes("/"));
    expect(kjbAtRoot).toHaveLength(1); // solo el maestro
  });

  it("sin paths duplicados y cada content mapea a su xml", () => {
    const art = readEtlArtifacts({
      etapas: [etapaKjb("stg_dwh", "sub.kjb", ["a.ktr", "b.ktr"])],
      kjb_master: null,
    });
    const entries = buildZipEntries(art);
    const paths = entries.map(e => e.path);
    expect(new Set(paths).size).toBe(paths.length);
    for (const e of entries) expect(e.content).toBe(`<xml>${e.path.split("/").pop()}</xml>`);
  });
});
