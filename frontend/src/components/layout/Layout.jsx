import Navbar from "./Navbar";
import "./layout.css";

export default function Layout({ children, guardNavigation }) {
  return (
    <div className="layout">
      <Navbar guardNavigation={guardNavigation} />
      <div className="layout__content">
        {children}
      </div>
    </div>
  );
}
