import { useAuth0 } from "@auth0/auth0-react";
import UserOptions from "../components/UserOptions";
import "../css/home.css";
import "../css/profile.css";

export default function Profile() {
  const { user } = useAuth0();

  const provider = user?.sub?.split("|")[0] || "—";

  const fields = [
    { label: "Nombre completo", value: user?.name },
    { label: "Apodo",           value: user?.nickname },
    { label: "Email",           value: user?.email },
    { label: "Email verificado", value: user?.email_verified ? "✅ Sí" : "❌ No" },
    { label: "Proveedor",       value: provider },
    { label: "ID",              value: user?.sub },
  ];

  return (
    <div className="home-container">
      <div className="home-header">
        <UserOptions onProfilePage />
      </div>
      <div className="profile-card">
        {user?.picture && (
          <img src={user.picture} alt="avatar" className="profile-avatar" />
        )}
        <h1 className="profile-name">{user?.name}</h1>
        <div className="profile-fields">
          {fields.map(({ label, value }) => (
            <div className="profile-field" key={label}>
              <span className="profile-field__label">{label}</span>
              <span className="profile-field__value">{value || "—"}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
