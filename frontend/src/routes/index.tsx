import { Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "../layouts/AppLayout";
import { AuthLayout } from "../layouts/AuthLayout";
import { ProtectedRoute } from "./ProtectedRoute";
import { WorkspaceRequiredRoute } from "./WorkspaceRequiredRoute";
import { RoleRequiredRoute } from "./RoleRequiredRoute";

import { LoginPage } from "../pages/LoginPage";
import { RegisterPage } from "../pages/RegisterPage";
import { OnboardingPage } from "../pages/OnboardingPage";
import { DashboardPage } from "../pages/DashboardPage";
import { MailboxPage } from "../pages/MailboxPage";
import { EmailDetailPage } from "../pages/EmailDetailPage";
import { ComposePage } from "../pages/ComposePage";
import { EmailAccountsPage } from "../pages/EmailAccountsPage";
import { TemplatesPage } from "../pages/TemplatesPage";
import { TemplateEditorPage } from "../pages/TemplateEditorPage";
import { SignaturesPage } from "../pages/SignaturesPage";
import { TeamPage } from "../pages/TeamPage";
import { DiagnosticsPage } from "../pages/DiagnosticsPage";
import { SettingsPage } from "../pages/SettingsPage";
import { ProfilePage } from "../pages/ProfilePage";
import { DomainsPage } from "../pages/DomainsPage";
import { CampaignsPage } from "../pages/CampaignsPage";
import { CreateCampaignPage } from "../pages/CreateCampaignPage";
import { CampaignDetailPage } from "../pages/CampaignDetailPage";
import { CampaignRecipientsPage } from "../pages/CampaignRecipientsPage";
import { NotFoundPage } from "../pages/NotFoundPage";

export function AppRoutes() {
  return (
    <Routes>
      {/* Public Auth Routes */}
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      {/* Authenticated Workspace Onboarding Route */}
      <Route element={<ProtectedRoute />}>
        <Route path="/onboarding" element={<OnboardingPage />} />
      </Route>

      {/* Authenticated Application Routes (Workspace Required) */}
      <Route element={<ProtectedRoute />}>
        <Route element={<WorkspaceRequiredRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/mailbox" element={<MailboxPage />} />
            <Route path="/emails/:emailId" element={<EmailDetailPage />} />
            <Route path="/compose" element={<ComposePage />} />
            <Route path="/campaigns" element={<CampaignsPage />} />
            <Route path="/campaigns/new" element={<CreateCampaignPage />} />
            <Route path="/campaigns/:campaignId" element={<CampaignDetailPage />} />
            <Route path="/campaigns/:campaignId/edit" element={<CreateCampaignPage />} />
            <Route path="/campaigns/:campaignId/recipients" element={<CampaignRecipientsPage />} />

            {/* Role-Protected Admin / Owner Routes */}
            <Route element={<RoleRequiredRoute allowedRoles={["OWNER", "ADMIN"]} />}>
              <Route path="/email-accounts" element={<EmailAccountsPage />} />
              <Route path="/team" element={<TeamPage />} />
              <Route path="/diagnostics" element={<DiagnosticsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>

            {/* Routes Accessible to All Active Workspace Members */}
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/domains" element={<DomainsPage />} />
            <Route path="/templates" element={<TemplatesPage />} />
            <Route path="/templates/new" element={<TemplateEditorPage />} />
            <Route path="/templates/:templateId/edit" element={<TemplateEditorPage />} />
            <Route path="/signatures" element={<SignaturesPage />} />
          </Route>
        </Route>
      </Route>

      {/* 404 Not Found Catch-All */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
