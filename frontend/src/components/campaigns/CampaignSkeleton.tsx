import React from "react";

export const CampaignSkeleton: React.FC = () => {
  return (
    <div className="w-full min-w-0">
      {/* Desktop Table Skeleton (md and above) */}
      <div className="hidden md:block w-full overflow-x-auto min-w-0 rounded-xl border border-slate-200/80 bg-white shadow-2xs">
        <table className="w-full text-left border-collapse text-sm min-w-[760px]">
          <thead>
            <tr className="bg-white text-slate-400 text-[11px] uppercase font-semibold tracking-wider border-b border-slate-100 select-none">
              <th className="py-3 px-4 w-[32%] min-w-[200px] font-medium">Campaign &amp; Subject</th>
              <th className="py-3 px-4 w-[20%] min-w-[150px] font-medium">Sender</th>
              <th className="py-3 px-4 w-[14%] min-w-[120px] font-medium">Target Size</th>
              <th className="py-3 px-4 w-[12%] min-w-[100px] font-medium">Status</th>
              <th className="py-3 px-4 w-[11%] min-w-[100px] font-medium">Scheduled Date</th>
              <th className="py-3 px-4 w-[11%] min-w-[110px] font-medium">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100/90">
            {[1, 2, 3, 4, 5].map((i) => (
              <tr key={i} className="animate-pulse">
                <td className="py-3 px-4">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-slate-100 shrink-0" />
                    <div className="flex flex-col gap-2 min-w-0">
                      <div className="h-3.5 w-40 bg-slate-200 rounded" />
                      <div className="h-2.5 w-52 bg-slate-100 rounded" />
                    </div>
                  </div>
                </td>
                <td className="py-3 px-4">
                  <div className="flex flex-col gap-1.5">
                    <div className="h-3 w-28 bg-slate-200 rounded" />
                    <div className="h-2.5 w-36 bg-slate-100 rounded" />
                  </div>
                </td>
                <td className="py-3 px-4">
                  <div className="h-6 w-24 bg-slate-100 rounded-full" />
                </td>
                <td className="py-3 px-4">
                  <div className="h-6 w-20 bg-slate-100 rounded-full" />
                </td>
                <td className="py-3 px-4">
                  <div className="flex flex-col gap-1.5">
                    <div className="h-3 w-20 bg-slate-100 rounded" />
                    <div className="h-2.5 w-14 bg-slate-50 rounded" />
                  </div>
                </td>
                <td className="py-3 px-4">
                  <div className="flex flex-col gap-1.5">
                    <div className="h-3 w-16 bg-slate-100 rounded" />
                    <div className="h-2.5 w-12 bg-slate-50 rounded" />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Card Skeletons (< md) */}
      <div className="md:hidden flex flex-col gap-3">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="bg-white p-4.5 rounded-xl border border-slate-200/80 shadow-2xs flex flex-col gap-3 animate-pulse"
          >
            <div className="flex items-start justify-between">
              <div className="flex flex-col gap-2">
                <div className="h-4 w-36 bg-slate-200 rounded" />
                <div className="h-3 w-48 bg-slate-100 rounded" />
              </div>
              <div className="h-5 w-5 bg-slate-100 rounded" />
            </div>
            <div className="flex gap-2">
              <div className="h-5 w-20 bg-slate-100 rounded-full" />
              <div className="h-5 w-24 bg-slate-100 rounded-full" />
            </div>
            <div className="h-3 w-40 bg-slate-100 rounded" />
          </div>
        ))}
      </div>
    </div>
  );
};
