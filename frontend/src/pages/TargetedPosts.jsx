import { useEffect, useState } from "react";
import axiosClient from "../api/axiosClient";
import { Folder } from "lucide-react";

export default function TargetedPost() {
  const [groups, setGroups] = useState({});

  useEffect(() => {
    async function load() {
      const res = await axiosClient.get("/candidates");

      const grouped = {};

      res.data.forEach((c) => {
        const folder = c.folder || "Autres";

        if (!grouped[folder]) grouped[folder] = [];

        grouped[folder].push(c);
      });

      setGroups(grouped);
    }

    load();
  }, []);

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold">📁 Post Ciblé</h1>

      {Object.entries(groups).map(([folder, candidates]) => (
        <div key={folder} className="bg-white border rounded-2xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Folder size={18} className="text-indigo-500" />
            <h2 className="font-semibold">{folder}</h2>
            <span className="text-xs text-gray-400">
              ({candidates.length})
            </span>
          </div>

          <div className="grid md:grid-cols-2 gap-3">
            {candidates.map((c) => (
              <div key={c.id} className="border rounded-xl p-3">
                <p className="font-medium">{c.full_name}</p>
                <p className="text-xs text-gray-500">
                  {c.current_position}
                </p>

                <div className="flex flex-wrap gap-1 mt-2">
                  {(c.skills || []).slice(0, 5).map((s) => (
                    <span
                      key={s}
                      className="text-xs bg-gray-100 px-2 py-1 rounded"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}