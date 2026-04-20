import { useAuth0 } from "@auth0/auth0-react";

export default function UserInfo() {
  const { user } = useAuth0();

  return (
    <>
      <h1>Hola, {user?.name}</h1>
      <h2>Información del usuario</h2>
      <pre className="user-data">
        {JSON.stringify(user, null, 2)}
      </pre>
    </>
  );
}
