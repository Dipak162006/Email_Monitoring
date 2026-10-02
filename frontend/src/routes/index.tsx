import { Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "../layouts/AppLayout";
import { AuthLayout } from "../layouts/AuthLayout";
import { ProtectedRoute } from "./ProtectedRoute";

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

      {/* Authenticated Application Routes */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/mailbox" element={<MailboxPage />} />
          <Route path="/emails/:emailId" element={<EmailDetailPage />} />
          <Route path="/compose" element={<ComposePage />} />
          <Route path="/email-accounts" element={<EmailAccountsPage />} />
          <Route path="/templates" element={<TemplatesPage />} />
          <Route path="/templates/new" element={<TemplateEditorPage />} />
          <Route path="/templates/:templateId/edit" element={<TemplateEditorPage />} />
          <Route path="/signatures" element={<SignaturesPage />} />
          <Route path="/team" element={<TeamPage />} />
          <Route path="/diagnostics" element={<DiagnosticsPage />} />
        </Route>
      </Route>

      {/* 404 Not Found Catch-All */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
