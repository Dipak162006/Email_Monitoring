import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { WorkspaceProvider } from "./context/WorkspaceContext";
import { NotificationProvider } from "./context/NotificationContext";
import { AppRoutes } from "./routes";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <WorkspaceProvider>
          <NotificationProvider>
            <AppRoutes />
          </NotificationProvider>
        </WorkspaceProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
