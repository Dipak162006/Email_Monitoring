import React, { useState } from "react";
import type { Campaign } from "../../types/campaign";
import type { AuthorizedEmailAccount } from "../../types/emails";
import { CampaignTableRow } from "./CampaignTableRow";
import { CampaignMobileCard } from "./CampaignMobileCard";

interface CampaignTableProps {
  campaigns: Campaign[];
  emailAccounts: AuthorizedEmailAccount[];
  onViewCampaign: (campaign: Campaign) => void;
  onEditCampaign?: (campaign: Campaign) => void;
  onManageRecipients?: (campaign: Campaign) => void;
  onSendNowCampaign?: (campaign: Campaign) => void;
  onPauseCampaign?: (campaign: Campaign) => void;
  onResumeCampaign?: (campaign: Campaign) => void;
  onCancelCampaign?: (campaign: Campaign) => void;
  onDeleteCampaign?: (campaign: Campaign) => void;
  mutatingCampaignId?: number | null;
}

export const CampaignTable: React.FC<CampaignTableProps> = ({
  campaigns,
  emailAccounts,
  onViewCampaign,
  onEditCampaign,
  onManageRecipients,
  onSendNowCampaign,
  onPauseCampaign,
  onResumeCampaign,
  onCancelCampaign,
  onDeleteCampaign,
  mutatingCampaignId,
}) => {
  // Mobile menu open key
  const [openMenuKey, setOpenMenuKey] = useState<string | null>(null);

  React.useEffect(() => {
    setOpenMenuKey(null);
  }, [campaigns]);

  // Map email accounts for O(1) lookup
  const accountMap = React.useMemo(() => {
    const map = new Map<number, AuthorizedEmailAccount>();
    emailAccounts.forEach((acc) => map.set(acc.id, acc));
    return map;
  }, [emailAccounts]);

  const handleToggleMenu = (e: React.MouseEvent, menuKey: string) => {
    e.stopPropagation();
    setOpenMenuKey((prev) => (prev === menuKey ? null : menuKey));
  };

  const handleCloseMenu = () => {
    setOpenMenuKey(null);
  };

  return (
    <div className="w-full min-w-0">
      {/* Desktop Table (md and above) - 6 information columns, no dedicated Actions header */}
      <div className="hidden md:block w-full overflow-x-auto min-w-0">
        <table className="w-full text-left border-collapse text-sm min-w-[760px]">
          <thead>
            <tr className="bg-white text-slate-400 text-[11px] uppercase font-semibold tracking-wider border-b border-slate-100 select-none">
              <th scope="col" className="py-3 px-4 w-[32%] min-w-[200px] font-medium">
                Campaign &amp; Subject
              </th>
              <th scope="col" className="py-3 px-4 w-[20%] min-w-[150px] font-medium">
                Sender
              </th>
              <th scope="col" className="py-3 px-4 w-[14%] min-w-[120px] font-medium">
                Target Size
              </th>
              <th scope="col" className="py-3 px-4 w-[12%] min-w-[100px] font-medium">
                Status
              </th>
              <th scope="col" className="py-3 px-4 w-[11%] min-w-[100px] font-medium">
                Scheduled Date
              </th>
              <th scope="col" className="py-3 px-4 w-[11%] min-w-[110px] font-medium">
                Created
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100/90 text-slate-800">
            {campaigns.map((campaign) => (
              <CampaignTableRow
                key={campaign.id}
                campaign={campaign}
                senderAccount={accountMap.get(campaign.email_account_id)}
                onView={onViewCampaign}
                onEdit={onEditCampaign}
                onManageRecipients={onManageRecipients}
                onSendNow={onSendNowCampaign}
                onPause={onPauseCampaign}
                onResume={onResumeCampaign}
                onCancel={onCancelCampaign}
                onDelete={onDeleteCampaign}
                isMutating={mutatingCampaignId === campaign.id}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Campaign Cards (< md) */}
      <div className="md:hidden flex flex-col gap-3 p-3 sm:p-4">
        {campaigns.map((campaign) => (
          <CampaignMobileCard
            key={campaign.id}
            campaign={campaign}
            senderAccount={accountMap.get(campaign.email_account_id)}
            isMenuOpen={openMenuKey === `mobile-${campaign.id}`}
            onToggleMenu={(e) => handleToggleMenu(e, `mobile-${campaign.id}`)}
            onCloseMenu={handleCloseMenu}
            onView={onViewCampaign}
            onEdit={onEditCampaign}
            onManageRecipients={onManageRecipients}
            onSendNow={onSendNowCampaign}
            onPause={onPauseCampaign}
            onResume={onResumeCampaign}
            onCancel={onCancelCampaign}
            onDelete={onDeleteCampaign}
            isMutating={mutatingCampaignId === campaign.id}
          />
        ))}
      </div>
    </div>
  );
};
