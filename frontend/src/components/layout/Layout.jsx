import Navbar from "./Navbar";
import { useEtl } from "../../context/EtlContext";
import "./layout.css";

export default function Layout({ children, guardNavigation }) {
  const { backendDown } = useEtl();
  return (
    <div className="layout">
      {backendDown && (
        <div className="layout__backend-banner" role="status">
          No se pudo conectar con el servidor. Reintentando…
        </div>
      )}
      <Navbar guardNavigation={guardNavigation} />
      <div className="layout__content">
        {children}
      </div>
    </div>
  );
}
