import UserOptions from "./UserOptions";
import "../css/layout.css";

export default function Layout({ children, onProfilePage = false }) {
  return (
    <div className="layout">
      <div className="layout-user-options">
        <UserOptions onProfilePage={onProfilePage} />
      </div>
      {children}
    </div>
  );
}
