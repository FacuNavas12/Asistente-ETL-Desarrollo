import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { downloadKtrFromEtl, downloadAll } from "@/utils/etlCardActions";

export default function EtlCardMenu({ etl }) {
  const [open, setOpen] = useState(false);
  const ref             = useRef(null);
  const navigate        = useNavigate();

  useEffect(() => {
    if (!open) return;
    const close = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const hasKtr = Boolean(etl.result?.ktr_xml);

  const handle = (e, fn) => {
    e.stopPropagation();
    fn();
    setOpen(false);
  };

  return (
    <div className="etl-card-menu" ref={ref}>
      <button
        className="etl-card-menu__trigger"
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        title="Opciones"
      >
        •••
      </button>
      {open && (
        <div className="etl-card-menu__dropdown">
          <button
            className="etl-card-menu__item"
            onClick={(e) => handle(e, () => downloadAll(etl))}
          >
            Descargar todo
          </button>
          <button
            className="etl-card-menu__item"
            disabled={!hasKtr}
            onClick={(e) => handle(e, () => downloadKtrFromEtl(etl))}
          >
            Descargar .ktr
          </button>
          <button
            className="etl-card-menu__item"
            onClick={(e) => handle(e, () => navigate("/superset"))}
          >
            Abrir en Superset
          </button>
        </div>
      )}
    </div>
  );
}
