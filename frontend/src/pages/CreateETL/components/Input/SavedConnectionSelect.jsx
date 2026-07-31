import "../../css/shared.css";
import "../../css/inputConnection.css";

// Select de conexiones guardadas (metadata sin password), extraído de
// ConnectionForm para reusarlo tal cual en otras pantallas (ver ConnectionView
// en EtlDetail). Presentacional: el padre es dueño de la lista (`conns`) y
// decide qué hacer al elegir vía onSelect(conn|null) — reuso de id, precarga de
// campos, etc. No se renderiza si no hay conexiones guardadas.
//
// value: id de la conexión seleccionada ("" = ninguna / placeholder). Un padre
// que quiera "menú de acción" (elegir → precargar → volver al placeholder)
// pasa value="" fijo; uno que quiera selección pegajosa pasa el id elegido.
export default function SavedConnectionSelect({
  conns,
  value,
  onSelect,
  label = "Conexiones guardadas",
  emptyLabel = "— Nueva conexión —",
}) {
  if (!conns.length) return null;
  return (
    <div className="form-grid form-grid--mb">
      <div className="form-field">
        <label>{label}</label>
        <select
          value={value ?? ""}
          onChange={e => {
            const id = e.target.value;
            onSelect(id ? conns.find(c => String(c.id) === String(id)) ?? null : null);
          }}
        >
          <option value="">{emptyLabel}</option>
          {conns.map(c => (
            <option key={c.id} value={c.id}>
              {c.name} · {c.host}:{c.port}/{c.database} ({c.db_type})
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
