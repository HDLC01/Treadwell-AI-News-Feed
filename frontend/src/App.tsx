import { Routes, Route } from "react-router-dom";
import TopBar from "./components/TopBar";
import { useTheme } from "./lib/theme";
import FeedPage from "./pages/FeedPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import DigestsPage from "./pages/DigestsPage";
import AdminPage from "./pages/AdminPage";

export default function App() {
  const { theme, toggle } = useTheme();

  return (
    <div className="min-h-full bg-bg text-fg">
      <TopBar theme={theme} onToggleTheme={toggle} />
      <main className="mx-auto w-full max-w-screen-2xl px-4 py-5 sm:px-6 lg:px-8">
        <Routes>
          <Route path="/" element={<FeedPage />} />
          <Route path="/project/:id" element={<ProjectDetailPage />} />
          <Route path="/digests" element={<DigestsPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="*" element={<FeedPage />} />
        </Routes>
      </main>
    </div>
  );
}
