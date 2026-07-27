import { describe, it, expect } from "vitest";
import { stagesArrayToMap, mergeProgressLogs } from "./progressLog";

describe("stagesArrayToMap", () => {
  it("mapea el array de status.stages a un dict por nombre", () => {
    const map = stagesArrayToMap([
      { nombre: "origen_stg", status: "done", data: { ktr: {} }, error: null },
      { nombre: "stg_dwh", status: "failed", data: null, error: "boom" },
    ]);
    expect(map.origen_stg).toEqual({ status: "done", data: { ktr: {} }, error: null });
    expect(map.stg_dwh).toEqual({ status: "failed", data: null, error: "boom" });
  });

  it("con array vacío o undefined, devuelve las 2 claves en null", () => {
    expect(stagesArrayToMap([])).toEqual({ origen_stg: null, stg_dwh: null });
    expect(stagesArrayToMap(undefined)).toEqual({ origen_stg: null, stg_dwh: null });
  });
});

describe("mergeProgressLogs", () => {
  const evt = (seq, level = "info", message = `m${seq}`) => ({ seq, level, message });

  it("mapea eventos nuevos a entradas de log con id/message/level/fading", () => {
    const merged = mergeProgressLogs([], [evt(0), evt(1)]);
    expect(merged).toEqual([
      { id: "p0", message: "m0", level: "info", fading: false },
      { id: "p1", message: "m1", level: "info", fading: false },
    ]);
  });

  it("marca fading en las entradas 'info' que exceden la ventana reciente (6)", () => {
    const nuevos = Array.from({ length: 8 }, (_, i) => evt(i));
    const merged = mergeProgressLogs([], nuevos);
    const fading = merged.filter(l => l.fading).map(l => l.id);
    expect(fading).toEqual(["p0", "p1"]); // las 2 más viejas de las 8 quedan afuera de la ventana de 6
  });

  it("warning y error nunca se marcan fading, aunque queden viejos", () => {
    const nuevos = [
      evt(0, "warning"),
      ...Array.from({ length: 7 }, (_, i) => evt(i + 1)),
    ];
    const merged = mergeProgressLogs([], nuevos);
    const warningEntry = merged.find(l => l.id === "p0");
    expect(warningEntry.fading).toBe(false);
  });

  it("acumula sobre logs previos y resetea su fading antes de recalcular", () => {
    const prev = [{ id: "p0", message: "m0", level: "info", fading: true }];
    const merged = mergeProgressLogs(prev, [evt(1)]);
    expect(merged.map(l => l.id)).toEqual(["p0", "p1"]);
    expect(merged.every(l => l.fading === false)).toBe(true);
  });
});
