import { useState, useRef, useEffect } from "react";

export default function CreateETLOptions({
  importInputRef,
  onDescargar,
  onLimpiar,
  onCargarEjemplo,
}) {
  const [open, setOpen] = useState(false);
  const ref             = useRef(null);

  useEffect(() => {
    if (!open) return;
    const close = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const handle = (fn) => {
    fn();
    setOpen(false);
  };

  return (
    <div className="etl-options" ref={ref}>
      <button
        className="etl-clear-btn etl-options__trigger"
        onClick={() => setOpen((o) => !o)}
      >
        Opciones ▾
      </button>
      {open && (
        <div className="etl-options__dropdown">
          <button
            className="etl-options__item"
            onClick={() => { importInputRef.current?.click(); setOpen(false); }}
          >
            Importar
          </button>
          <button
            className="etl-options__item"
            onClick={() => handle(onDescargar)}
          >
            Descargar
          </button>
          <button
            className="etl-options__item"
            onClick={() => handle(onLimpiar)}
          >
            Limpiar
          </button>
          <button
            className="etl-options__item"
            onClick={() => handle(onCargarEjemplo)}
          >
            Cargar ejemplo
          </button>
        </div>
      )}
    </div>
  );
}
