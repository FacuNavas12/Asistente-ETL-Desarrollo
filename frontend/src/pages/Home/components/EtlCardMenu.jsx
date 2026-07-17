import { useState, useRef, useEffect } from "react";
import { downloadKtrFromEtl, downloadAll } from "@/utils/etlCardActions";
import { exportEtlToSuperset } from "@/utils/supersetExport";

export default function EtlCardMenu({ etl, onDeletePermanent }) {
  const [open, setOpen]               = useState(false);
  const [supersetBusy, setSupersetBusy] = useState(false);
  const ref                           = useRef(null);

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

  const handleExportSuperset = async (e) => {
    e.stopPropagation();
    setSupersetBusy(true);
    try {
      await exportEtlToSuperset(etl);
      setOpen(false);
    } catch (err) {
      alert(err?.message ?? "No se pudo importar el dashboard en Superset.");
    } finally {
      setSupersetBusy(false);
    }
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
            disabled={!hasKtr || supersetBusy}
            onClick={handleExportSuperset}
          >
            {supersetBusy ? "Abriendo en Superset..." : "Abrir en Superset"}
          </button>
          <button
            className="etl-card-menu__item etl-card-menu__item--danger"
            onClick={(e) => handle(e, onDeletePermanent)}
          >
            Eliminar definitivamente
          </button>
        </div>
      )}
    </div>
  );
}
