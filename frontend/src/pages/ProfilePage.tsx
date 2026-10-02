import { useState, useEffect, type FormEvent } from "react";
import {
  User as UserIcon,
  Lock,
  Shield,
  ShieldCheck,
  Eye,
  EyeOff,
  Check,
  X,
  AlertCircle,
  CheckCircle2,
  Loader2,
  Calendar,
  Info,
  CheckSquare,
} from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { authApi } from "../services/api";
import { cn } from "../lib/utils";

function formatMemberSince(dateStr?: string): string {
  if (!dateStr) return "Unknown";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", {
      month: "long",
      year: "numeric",
    });
  } catch {
    return "Unknown";
  }
}

export function ProfilePage() {
  const { user, refreshUser } = useAuth();

  // Personal Information State
  const [nameInput, setNameInput] = useState(user?.full_name ?? "");
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [profileValidationError, setProfileValidationError] = useState<string | null>(null);
  const [profileSuccessMessage, setProfileSuccessMessage] = useState<string | null>(null);
  const [profileErrorMessage, setProfileErrorMessage] = useState<string | null>(null);

  // Change Password State
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [passwordSuccessMessage, setPasswordSuccessMessage] = useState<string | null>(null);
  const [passwordErrorMessage, setPasswordErrorMessage] = useState<string | null>(null);

  // Sync profile name whenever user data updates
  useEffect(() => {
    if (user?.full_name !== undefined) {
      setNameInput(user.full_name ?? "");
      setProfileValidationError(null);
    }
  }, [user?.full_name]);

  // Profile calculations
  const isProfileDirty = nameInput.trim() !== (user?.full_name ?? "");
  const canSaveProfile = isProfileDirty && nameInput.trim().length > 0 && nameInput.length <= 255;

  const handleProfileReset = () => {
    setNameInput(user?.full_name ?? "");
    setProfileValidationError(null);
    setProfileSuccessMessage(null);
    setProfileErrorMessage(null);
  };

  const handleProfileSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = nameInput.trim();

    if (!trimmed) {
      setProfileValidationError("Full name is required and cannot be empty.");
      return;
    }

    if (trimmed.length > 255) {
      setProfileValidationError("Full name cannot exceed 255 characters.");
      return;
    }

    setIsSavingProfile(true);
    setProfileValidationError(null);
    setProfileSuccessMessage(null);
    setProfileErrorMessage(null);

    try {
      await authApi.updateProfile({ full_name: trimmed });
      // Instantly refresh user in AuthContext so topbar and sidebar reflect new name
      await refreshUser();
      setProfileSuccessMessage("Profile information saved successfully.");
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        "Failed to update profile. Please try again.";
      setProfileErrorMessage(typeof detail === "string" ? detail : JSON.stringify(detail));
    } finally {
      setIsSavingProfile(false);
    }
  };

  // Password calculations
  const isMismatch = confirmPassword.length > 0 && newPassword !== confirmPassword;
  const isLengthValid = newPassword.length >= 8 && newPassword.length <= 128;
  const canSubmitPassword =
    currentPassword.length > 0 &&
    newPassword.length >= 8 &&
    newPassword.length <= 128 &&
    newPassword === confirmPassword;

  const handlePasswordSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (!currentPassword) {
      setPasswordErrorMessage("Current password is required.");
      return;
    }

    if (!isLengthValid) {
      setPasswordErrorMessage("New password must be between 8 and 128 characters.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setPasswordErrorMessage("New password and confirmation do not match.");
      return;
    }

    setIsChangingPassword(true);
    setPasswordSuccessMessage(null);
    setPasswordErrorMessage(null);

    try {
      await authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });

      // Clear password fields on successful response
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setShowCurrentPassword(false);
      setShowNewPassword(false);
      setShowConfirmPassword(false);
      setPasswordSuccessMessage("Password changed successfully.");
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        "Failed to change password. Please check your credentials.";
      setPasswordErrorMessage(typeof detail === "string" ? detail : JSON.stringify(detail));
    } finally {
      setIsChangingPassword(false);
    }
  };

  return (
    <div className="w-full bg-slate-50/50 min-h-screen py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-6xl mx-auto flex flex-col gap-6">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 pb-4 border-b border-slate-200">
          <div className="flex flex-col gap-1">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
              Profile &amp; Account Settings
            </h1>
            <p className="text-sm text-slate-500">
              Manage your personal information and account security.
            </p>
          </div>
          <div className="flex items-center gap-2 self-start sm:self-auto">
            <span className="px-3 py-1 rounded-full bg-slate-100 border border-slate-200 text-slate-600 text-xs font-medium flex items-center gap-1.5 shadow-2xs">
              <ShieldCheck className="w-4 h-4 text-indigo-600" />
              <span>Workspace Protected</span>
            </span>
          </div>
        </div>

        {/* Two-Column Responsive Layout */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
          {/* Card 1: Personal Information */}
          <div className="bg-white rounded-xl p-6 sm:p-7 shadow-xs border border-slate-200 flex flex-col gap-6">
            {/* Card Header */}
            <div className="flex items-center gap-3.5 pb-4 border-b border-slate-100">
              <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-100/80 flex items-center justify-center text-indigo-600 shrink-0">
                <UserIcon className="w-5 h-5 text-indigo-600" />
              </div>
              <div className="flex flex-col">
                <h2 className="text-base font-semibold text-slate-900">Personal Information</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Update your display name and view account details.
                </p>
              </div>
            </div>

            {/* Profile Feedback Notifications */}
            {profileSuccessMessage && (
              <div className="p-3.5 rounded-lg bg-emerald-50 border border-emerald-200 flex items-center justify-between text-emerald-800">
                <div className="flex items-center gap-2 text-xs sm:text-sm font-medium">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>{profileSuccessMessage}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setProfileSuccessMessage(null)}
                  className="text-emerald-500 hover:text-emerald-700 p-0.5 rounded-sm cursor-pointer"
                  aria-label="Dismiss notification"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            {profileErrorMessage && (
              <div className="p-3.5 rounded-lg bg-rose-50 border border-rose-200 flex items-center justify-between text-rose-800">
                <div className="flex items-center gap-2 text-xs sm:text-sm font-medium">
                  <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                  <span>{profileErrorMessage}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setProfileErrorMessage(null)}
                  className="text-rose-500 hover:text-rose-700 p-0.5 rounded-sm cursor-pointer"
                  aria-label="Dismiss notification"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            {/* Personal Information Form */}
            <form onSubmit={handleProfileSubmit} className="flex flex-col gap-5">
              {/* Full Name */}
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <label
                    htmlFor="profile-full-name"
                    className="text-xs font-semibold text-slate-700 flex items-center gap-1"
                  >
                    <span>Full Name</span>
                    <span className="text-rose-500">*</span>
                  </label>
                  <span
                    className={cn(
                      "text-xs transition-colors",
                      nameInput.length > 255 ? "text-rose-600 font-semibold" : "text-slate-400"
                    )}
                  >
                    {nameInput.length} / 255
                  </span>
                </div>

                <div className="relative flex items-center rounded-lg">
                  <input
                    id="profile-full-name"
                    type="text"
                    maxLength={255}
                    value={nameInput}
                    onChange={(e) => {
                      setNameInput(e.target.value);
                      if (profileValidationError) setProfileValidationError(null);
                      if (profileSuccessMessage) setProfileSuccessMessage(null);
                      if (profileErrorMessage) setProfileErrorMessage(null);
                    }}
                    disabled={isSavingProfile}
                    placeholder="Enter your full name"
                    className={cn(
                      "w-full px-3.5 py-2.5 rounded-lg bg-slate-50 border text-slate-900 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:bg-white transition-all",
                      profileValidationError
                        ? "border-rose-300 focus:ring-rose-500"
                        : "border-slate-200 focus:ring-indigo-500 focus:border-indigo-500"
                    )}
                  />
                  {nameInput.length > 0 && !isSavingProfile && (
                    <button
                      type="button"
                      onClick={() => {
                        setNameInput("");
                        document.getElementById("profile-full-name")?.focus();
                      }}
                      className="absolute right-3 p-1 text-slate-400 hover:text-slate-600 rounded-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
                      aria-label="Clear full name"
                      title="Clear full name"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>

                {profileValidationError && (
                  <span className="text-xs text-rose-600 font-medium flex items-center gap-1 pt-0.5">
                    <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                    <span>{profileValidationError}</span>
                  </span>
                )}
              </div>

              {/* Read-Only Email Address */}
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <label
                    htmlFor="profile-email"
                    className="text-xs font-semibold text-slate-700"
                  >
                    Email Address
                  </label>
                  <span className="text-xs text-slate-400 flex items-center gap-1">
                    <Lock className="w-3 h-3 text-slate-400" />
                    <span>Read-only</span>
                  </span>
                </div>

                <div className="relative flex items-center">
                  <input
                    id="profile-email"
                    type="email"
                    value={user?.email ?? ""}
                    readOnly
                    tabIndex={-1}
                    aria-describedby="email-explanation"
                    className="w-full pl-3.5 pr-10 py-2.5 rounded-lg bg-slate-100/70 border border-slate-200 text-slate-600 text-sm cursor-not-allowed select-none focus:outline-none"
                  />
                  <div className="absolute right-3 pointer-events-none text-slate-400">
                    <Lock className="w-4 h-4" />
                  </div>
                </div>

                <p id="email-explanation" className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
                  <Info className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <span>Email address cannot currently be changed.</span>
                </p>
              </div>

              {/* Account Metadata Box */}
              <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-xs text-slate-600">
                  <Calendar className="w-4 h-4 text-slate-400 shrink-0" />
                  <span>
                    Member Since:{" "}
                    <strong className="font-semibold text-slate-800">
                      {formatMemberSince(user?.created_at)}
                    </strong>
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-500">Status:</span>
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-50 border border-emerald-200/80 text-xs font-semibold text-emerald-700">
                    <span
                      className={cn(
                        "w-1.5 h-1.5 rounded-full",
                        user?.is_active ? "bg-emerald-500 animate-pulse" : "bg-slate-400"
                      )}
                    />
                    {user?.is_active ? "Active" : "Inactive"}
                  </span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={handleProfileReset}
                  disabled={!isProfileDirty || isSavingProfile}
                  className="px-4 py-2 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                >
                  Reset
                </button>
                <button
                  type="submit"
                  disabled={!canSaveProfile || isSavingProfile}
                  className="px-5 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 text-xs font-semibold flex items-center gap-2 shadow-xs transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                >
                  {isSavingProfile ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Check className="w-4 h-4" />
                  )}
                  <span>{isSavingProfile ? "Saving..." : "Save Changes"}</span>
                </button>
              </div>
            </form>
          </div>

          {/* Card 2: Change Password */}
          <div className="bg-white rounded-xl p-6 sm:p-7 shadow-xs border border-slate-200 flex flex-col gap-6">
            {/* Card Header */}
            <div className="flex items-center gap-3.5 pb-4 border-b border-slate-100">
              <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-100/80 flex items-center justify-center text-indigo-600 shrink-0">
                <Lock className="w-5 h-5 text-indigo-600" />
              </div>
              <div className="flex flex-col">
                <h2 className="text-base font-semibold text-slate-900">Change Password</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Update your password to keep your account secure.
                </p>
              </div>
            </div>

            {/* Password Hint Callout */}
            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200/80 flex items-start gap-2.5 text-slate-600">
              <Shield className="w-4 h-4 text-indigo-600 mt-0.5 shrink-0" />
              <span className="text-xs leading-relaxed">
                Your current password is required to authorize a change. Enter a strong, unique key below.
              </span>
            </div>

            {/* Password Feedback Notifications */}
            {passwordSuccessMessage && (
              <div className="p-3.5 rounded-lg bg-emerald-50 border border-emerald-200 flex items-center justify-between text-emerald-800">
                <div className="flex items-center gap-2 text-xs sm:text-sm font-medium">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>{passwordSuccessMessage}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setPasswordSuccessMessage(null)}
                  className="text-emerald-500 hover:text-emerald-700 p-0.5 rounded-sm cursor-pointer"
                  aria-label="Dismiss notification"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            {passwordErrorMessage && (
              <div className="p-3.5 rounded-lg bg-rose-50 border border-rose-200 flex items-center justify-between text-rose-800">
                <div className="flex items-center gap-2 text-xs sm:text-sm font-medium">
                  <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                  <span>{passwordErrorMessage}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setPasswordErrorMessage(null)}
                  className="text-rose-500 hover:text-rose-700 p-0.5 rounded-sm cursor-pointer"
                  aria-label="Dismiss notification"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            {/* Password Form */}
            <form onSubmit={handlePasswordSubmit} className="flex flex-col gap-5">
              {/* Current Password */}
              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="current-password"
                  className="text-xs font-semibold text-slate-700"
                >
                  Current Password
                </label>
                <div className="relative flex items-center">
                  <input
                    id="current-password"
                    type={showCurrentPassword ? "text" : "password"}
                    value={currentPassword}
                    onChange={(e) => {
                      setCurrentPassword(e.target.value);
                      if (passwordSuccessMessage) setPasswordSuccessMessage(null);
                      if (passwordErrorMessage) setPasswordErrorMessage(null);
                    }}
                    disabled={isChangingPassword}
                    placeholder="••••••••••••"
                    required
                    className="w-full pl-3.5 pr-10 py-2.5 rounded-lg bg-slate-50 border border-slate-200 text-slate-900 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowCurrentPassword((prev) => !prev)}
                    className="absolute right-3 p-1 text-slate-400 hover:text-slate-600 rounded-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
                    aria-label={showCurrentPassword ? "Hide current password" : "Show current password"}
                    title={showCurrentPassword ? "Hide password" : "Show password"}
                  >
                    {showCurrentPassword ? (
                      <EyeOff className="w-4 h-4" />
                    ) : (
                      <Eye className="w-4 h-4" />
                    )}
                  </button>
                </div>
              </div>

              {/* New Password */}
              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="new-password"
                  className="text-xs font-semibold text-slate-700"
                >
                  New Password
                </label>
                <div className="relative flex items-center">
                  <input
                    id="new-password"
                    type={showNewPassword ? "text" : "password"}
                    value={newPassword}
                    onChange={(e) => {
                      setNewPassword(e.target.value);
                      if (passwordSuccessMessage) setPasswordSuccessMessage(null);
                      if (passwordErrorMessage) setPasswordErrorMessage(null);
                    }}
                    disabled={isChangingPassword}
                    placeholder="Enter new password"
                    minLength={8}
                    maxLength={128}
                    required
                    className="w-full pl-3.5 pr-10 py-2.5 rounded-lg bg-slate-50 border border-slate-200 text-slate-900 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword((prev) => !prev)}
                    className="absolute right-3 p-1 text-slate-400 hover:text-slate-600 rounded-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
                    aria-label={showNewPassword ? "Hide new password" : "Show new password"}
                    title={showNewPassword ? "Hide password" : "Show password"}
                  >
                    {showNewPassword ? (
                      <EyeOff className="w-4 h-4" />
                    ) : (
                      <Eye className="w-4 h-4" />
                    )}
                  </button>
                </div>
                <p className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
                  <CheckSquare className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <span>Minimum 8 characters, maximum 128 characters.</span>
                </p>
              </div>

              {/* Confirm New Password */}
              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="confirm-password"
                  className="text-xs font-semibold text-slate-700"
                >
                  Confirm New Password
                </label>
                <div className="relative flex items-center">
                  <input
                    id="confirm-password"
                    type={showConfirmPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => {
                      setConfirmPassword(e.target.value);
                      if (passwordSuccessMessage) setPasswordSuccessMessage(null);
                      if (passwordErrorMessage) setPasswordErrorMessage(null);
                    }}
                    disabled={isChangingPassword}
                    placeholder="Re-enter new password"
                    required
                    className={cn(
                      "w-full pl-3.5 pr-10 py-2.5 rounded-lg bg-slate-50 border text-slate-900 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 transition-all",
                      isMismatch
                        ? "border-rose-300 focus:ring-rose-500 ring-1 ring-rose-200"
                        : "border-slate-200 focus:ring-indigo-500 focus:bg-white"
                    )}
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword((prev) => !prev)}
                    className="absolute right-3 p-1 text-slate-400 hover:text-slate-600 rounded-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
                    aria-label={showConfirmPassword ? "Hide confirmation password" : "Show confirmation password"}
                    title={showConfirmPassword ? "Hide password" : "Show password"}
                  >
                    {showConfirmPassword ? (
                      <EyeOff className="w-4 h-4" />
                    ) : (
                      <Eye className="w-4 h-4" />
                    )}
                  </button>
                </div>
                {isMismatch && (
                  <p className="text-xs text-rose-600 font-medium flex items-center gap-1 mt-0.5">
                    <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                    <span>Passwords do not match</span>
                  </p>
                )}
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
                <button
                  type="submit"
                  disabled={!canSubmitPassword || isChangingPassword}
                  className="px-5 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 text-xs font-semibold flex items-center gap-2 shadow-xs transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                >
                  {isChangingPassword ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Lock className="w-4 h-4" />
                  )}
                  <span>{isChangingPassword ? "Updating..." : "Change Password"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
