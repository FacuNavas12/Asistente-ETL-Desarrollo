import { useAuth0 } from "@auth0/auth0-react";
import AppRouter from "./routes/AppRouter";
import "./css/global.css";

export default function App() {
  const { isLoading, error } = useAuth0();

  if (isLoading) return <p>Cargando autenticación...</p>;

  return (
    <>
      {error && <p>Error: {error.message}</p>}
      <AppRouter />
    </>
  );
}