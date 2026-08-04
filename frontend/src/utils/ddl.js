// El DDL a veces llega con los saltos de línea escapados como "\n" literal
// (según cómo lo serialice el backend). Los convertimos a saltos reales antes
// de renderizar/copiar/parsear — sin esto el DDL copiado no es SQL ejecutable.
export function unescapeDdl(ddl) {
  return (ddl ?? "").replace(/\\r\\n/g, "\n").replace(/\\n/g, "\n").replace(/\\t/g, "\t");
}
