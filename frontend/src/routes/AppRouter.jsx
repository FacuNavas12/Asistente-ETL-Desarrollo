import { Routes, Route } from "react-router-dom";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Home from "@/pages/Home";
import Profile from "@/pages/Profile";
import Settings from "@/pages/Settings";
import CreateETL from "@/pages/CreateETL";
import EtlDetail from "@/pages/EtlDetail";
import PrivateRoute from "../auth0/PrivateRoute";

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/home"       element={<PrivateRoute><Home /></PrivateRoute>} />
      <Route path="/profile"    element={<PrivateRoute><Profile /></PrivateRoute>} />
      <Route path="/settings"   element={<PrivateRoute><Settings /></PrivateRoute>} />
      <Route path="/etl-create" element={<PrivateRoute><CreateETL /></PrivateRoute>} />
      <Route path="/etl/:id"    element={<PrivateRoute><EtlDetail /></PrivateRoute>} />
    </Routes>
  );
}
