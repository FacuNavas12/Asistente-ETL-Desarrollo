import UserOptions from "../components/UserOptions";
import "../css/home.css";

export default function EtlCreate() {
  return (
    <div className="home-container">
      <div className="home-header">
        <UserOptions />
      </div>
      <div className="home-content">
        <h1 className="home-title">ETL Create</h1>
      </div>
    </div>
  );
}
