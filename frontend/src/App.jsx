import { Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./store/authStore";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import CandidateList from "./pages/CandidateList";
import CandidateDetail from "./pages/CandidateDetail";
import JobList from "./pages/JobList";

function ProtectedRoute({ children }) {
  const token = useAuthStore((s) => s.token);
  return token ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="candidates" element={<CandidateList />} />
        <Route path="candidates/:id" element={<CandidateDetail />} />
        <Route path="jobs" element={<JobList />} />
      </Route>
    </Routes>
  );
}