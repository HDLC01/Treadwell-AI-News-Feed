import { Routes, Route } from "react-router-dom";
import TopBar from "./components/TopBar";
import { useTheme } from "./lib/theme";
import { AuthProvider, RequireAuth, RequireAdmin } from "./lib/auth";
import LoginPage from "./pages/LoginPage";
import FeedPage from "./pages/FeedPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import PipelinePage from "./pages/PipelinePage";
import MapPage from "./pages/MapPage";
import DigestsPage from "./pages/DigestsPage";
import AdminPage from "./pages/AdminPage";

// The authenticated app shell (chrome + routes). Only rendered for signed-in
// @wetreadwell.com users; /admin additionally requires the admin role.
function Shell() {
  const { theme, toggle } = useTheme();
  return (
    <div className="min-h-full bg-bg text-fg">
      <TopBar theme={theme} onToggleTheme={toggle} />
      <main className="mx-auto w-full max-w-screen-2xl px-4 py-5 sm:px-6 lg:px-8">
        <Routes>
          <Route path="/" element={<FeedPage />} />
          <Route path="/pipeline" element={<PipelinePage />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="/project/:id" element={<ProjectDetailPage />} />
          <Route path="/digests" element={<DigestsPage />} />
          <Route path="/admin" element={<RequireAdmin><AdminPage /></RequireAdmin>} />
          <Route path="*" element={<FeedPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/*" element={<RequireAuth><Shell /></RequireAuth>} />
      </Routes>
    </AuthProvider>
  );
}
