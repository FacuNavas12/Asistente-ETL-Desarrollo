import { useTheme } from "@/context/ThemeContext";
import { useEtl } from "@/context/EtlContext";
import Layout from "@/components/layout/Layout";
import "./Settings.css";

function SettingsRow({ label, desc, children }) {
  return (
    <div className="settings-row">
      <div className="settings-row__info">
        <span className="settings-row__label">{label}</span>
        {desc && <span className="settings-row__desc">{desc}</span>}
      </div>
      {children}
    </div>
  );
}

function ThemeToggle({ dark, onToggle }) {
  return (
    <button
      className={`settings-toggle${dark ? " settings-toggle--on" : ""}`}
      onClick={onToggle}
    >
      <span className="settings-toggle__track">
        <span className="settings-toggle__thumb" />
      </span>
      <span className="settings-toggle__label">{dark ? "Oscuro" : "Claro"}</span>
    </button>
  );
}

export default function Settings() {
  const { dark, toggle } = useTheme();
  const { etls } = useEtl();

  return (
    <Layout>
      <div className="settings-page">
        <h1 className="settings-title">Configuración</h1>

        <div className="settings-section">
          <h2 className="settings-section__title">Apariencia</h2>
          <SettingsRow
            label="Tema de la interfaz"
            desc={dark ? "Modo oscuro activo" : "Modo claro activo"}
          >
            <ThemeToggle dark={dark} onToggle={toggle} />
          </SettingsRow>
        </div>

        <div className="settings-section">
          <h2 className="settings-section__title">Datos</h2>
          <SettingsRow
            label="ETLs guardados"
            desc="Almacenados en el navegador (localStorage)"
          >
            <span className="settings-badge">{etls.length}</span>
          </SettingsRow>
          <SettingsRow
            label="Borradores"
            desc="Se conservan 2 horas en la sesión activa"
          >
            <span className="settings-badge settings-badge--muted">sessionStorage</span>
          </SettingsRow>
        </div>

        <div className="settings-section">
          <h2 className="settings-section__title">Sobre la aplicación</h2>
          <SettingsRow
            label="Asistente ETL"
            desc="Generador de procesos ETL asistido por IA"
          >
            <span className="settings-version">v1.0</span>
          </SettingsRow>
          <SettingsRow
            label="Backend"
            desc="FastAPI + Google Gemini"
          />
          <SettingsRow
            label="Frontend"
            desc="React 19 + Vite + Auth0"
          />
        </div>
      </div>
    </Layout>
  );
}
