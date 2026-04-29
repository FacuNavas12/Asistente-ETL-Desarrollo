import Navbar from "./Navbar";
import "../css/layout.css";

export default function Layout({ children, onHomeClick }) {
  return (
    <div className="layout">
      <Navbar onHomeClick={onHomeClick} />
      {children}
    </div>
  );
}
