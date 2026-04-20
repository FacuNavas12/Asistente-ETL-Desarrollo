import { useAuth0 } from "@auth0/auth0-react";
import UserInfo from "../components/UserInfo";
import LogoutButton from "../components/LogoutButton";
import "../css/home.css";

export default function Home() {
  const { user, isAuthenticated } = useAuth0();
  console.log("HOME:", { isAuthenticated, user });

  return (
    <div className="home-container">
      <div className="profile-box">
        <UserInfo />
        <LogoutButton />
      </div>
    </div>
  );
}