import { Routes, Route } from "react-router-dom";
import Login from "../views/Login";
import Register from "../views/Register";
import Home from "../views/Home";
import Profile from "../views/Profile";
import CreateETL from "../views/CreateETL";
import EtlDetail from "../views/EtlDetail";
import PrivateRoute from "../auth0/PrivateRoute";

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/home"       element={<PrivateRoute><Home /></PrivateRoute>} />
      <Route path="/profile"    element={<PrivateRoute><Profile /></PrivateRoute>} />
      <Route path="/etl-create" element={<PrivateRoute><CreateETL /></PrivateRoute>} />
      <Route path="/etl/:id"    element={<PrivateRoute><EtlDetail /></PrivateRoute>} />
    </Routes>
  );
}
