import { useState, useRef, useEffect } from "react";
import { downloadKtrFromEtl, downloadAll } from "@/utils/etlCardActions";
import { readEtlArtifacts } from "@/utils/etlArtifacts";
import { exportEtlToSuperset } from "@/utils/supersetExport";
import { useToast } from "@/components/ui/Toast";

export default function EtlCardMenu({ etl, onDeletePermanent }) {
  const [open, setOpen]                 = useState(false);
  const [supersetBusy, setSupersetBusy] = useState(false);
  const ref                             = useRef(null);
  const { addToast }                    = useToast();

  useEffect(() => {
    if (!open) return;
    const close = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const art = readEtlArtifacts(etl.result);

  const handle = (e, fn) => {
    e.stopPropagation();
    fn();
    setOpen(false);
  };

  const handleDownloadAll = async (e) => {
    e.stopPropagation();
    const message = await downloadAll(etl);
    if (message) addToast(message);
    setOpen(false);
  };

  const handleDownloadKtr = (e) => {
    e.stopPropagation();
    try {
      downloadKtrFromEtl(etl);
    } catch (err) {
      addToast(err.message);
    }
    setOpen(false);
  };

  const handleExportSuperset = async (e) => {
    e.stopPropagation();
    setSupersetBusy(true);
    try {
      await exportEtlToSuperset(etl);
      setOpen(false);
    } catch (err) {
      addToast(err?.message ?? "No se pudo importar el dashboard en Superset.");
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
            onClick={handleDownloadAll}
          >
            Descargar todo
          </button>
          <button
            className="etl-card-menu__item"
            disabled={art.status !== "ok"}
            title={art.status !== "ok" ? art.message : undefined}
            onClick={handleDownloadKtr}
          >
            Descargar .ktr
          </button>
          <button
            className="etl-card-menu__item"
            disabled={supersetBusy}
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
