import { Users, Briefcase, TrendingUp, CheckCircle } from "lucide-react";
import { useCandidates } from "../hooks/useCandidates";
import { useJobs } from "../hooks/useJobs";
import KanbanBoard from "../components/KanbanBoard";

function StatCard({ label, value, icon: Icon, color }) {
  return (
    <div className="card p-5 flex items-center gap-4">
      <div className={`p-3 rounded-lg ${color}`}>
        <Icon size={22} className="text-white" />
      </div>
      <div>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        <p className="text-sm text-gray-500">{label}</p>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { data: candidates = [] } = useCandidates();
  const { data: jobs = [] } = useJobs();

  const stats = {
    total: candidates.length,
    inProgress: candidates.filter((c) =>
      ["screening", "interview", "offer"].includes(c.status)
    ).length,
    hired: candidates.filter((c) => c.status === "hired").length,
    activeJobs: jobs.length,
  };

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 text-sm mt-1">Vue d'ensemble du pipeline de recrutement</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard label="Total candidats"   value={stats.total}      icon={Users}       color="bg-blue-500" />
        <StatCard label="En cours"          value={stats.inProgress} icon={TrendingUp}  color="bg-yellow-500" />
        <StatCard label="Embauchés"         value={stats.hired}      icon={CheckCircle} color="bg-green-500" />
        <StatCard label="Postes actifs"     value={stats.activeJobs} icon={Briefcase}   color="bg-purple-500" />
      </div>

      <div className="card p-6">
        <h2 className="text-base font-semibold text-gray-900 mb-5">Pipeline Kanban</h2>
        <KanbanBoard candidates={candidates} />
      </div>
    </div>
  );
}