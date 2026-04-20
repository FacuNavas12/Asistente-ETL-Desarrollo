import { Routes, Route } from "react-router-dom";
import Login from "../views/Login";
import Register from "../views/Register";
import Home from "../views/Home";
import PrivateRoute from "../auth0/PrivateRoute";

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route
        path="/home"
        element={
          <PrivateRoute>
            <Home />
          </PrivateRoute>
        }
      />
    </Routes>
  );
}