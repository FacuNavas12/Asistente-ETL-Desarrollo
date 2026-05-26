import Navbar from "./Navbar";
import "./layout.css";

export default function Layout({ children }) {
  return (
    <div className="layout">
      <Navbar />
      <div className="layout__content">
        {children}
      </div>
    </div>
  );
}
