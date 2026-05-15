"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { ErrorBanner } from "@/components/ErrorBanner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import { useProject } from "@/context/ProjectContext";
import type { User } from "@/types";

export default function ProfilePage() {
  const router = useRouter();
  const { currentUser, refresh } = useProject();

  // Profile fields
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSuccess, setProfileSuccess] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);

  // Password fields
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState(false);
  const [passwordLoading, setPasswordLoading] = useState(false);

  useEffect(() => {
    if (currentUser) {
      setName(currentUser.name ?? "");
      setEmail(currentUser.email ?? "");
    }
  }, [currentUser]);

  function handleLogout() {
    void fetch("/api/auth/logout", { method: "POST" }).finally(() => {
      router.push("/login");
    });
  }

  async function handleProfileSave(e: React.FormEvent) {
    e.preventDefault();
    setProfileError(null);
    setProfileSuccess(false);
    setProfileLoading(true);
    try {
      await apiFetch<User>("/api/auth/me", {
        method: "PATCH",
        body: JSON.stringify({ name: name || null, email: email || null }),
      });
      await refresh();
      setProfileSuccess(true);
      setTimeout(() => setProfileSuccess(false), 3000);
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : "Failed to update profile");
    } finally {
      setProfileLoading(false);
    }
  }

  async function handlePasswordSave(e: React.FormEvent) {
    e.preventDefault();
    setPasswordError(null);
    setPasswordSuccess(false);

    if (newPassword !== confirmPassword) {
      setPasswordError("New passwords do not match.");
      return;
    }
    if (newPassword.length < 8) {
      setPasswordError("New password must be at least 8 characters.");
      return;
    }

    setPasswordLoading(true);
    try {
      await apiFetch<User>("/api/auth/me", {
        method: "PATCH",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordSuccess(true);
      setTimeout(() => setPasswordSuccess(false), 3000);
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : "Failed to update password");
    } finally {
      setPasswordLoading(false);
    }
  }

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar onLogout={handleLogout} />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="space-y-6">
          <div>
            <h1 className="text-xl font-semibold">Profile</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Manage your account details and password.
            </p>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* Profile info */}
          <section className="xl:col-span-2 rounded-lg border border-border bg-card p-6 space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
              Account Info
            </h2>
            <div className="text-sm text-muted-foreground">
              Username:{" "}
              <span className="text-foreground font-medium">
                {currentUser?.username ?? "—"}
              </span>
            </div>
            {profileError && <ErrorBanner message={profileError} />}
            {profileSuccess && (
              <p className="text-sm text-green-500">Profile updated successfully.</p>
            )}
            <form onSubmit={handleProfileSave} className="space-y-4">
              <div className="space-y-1">
                <label className="text-sm font-medium" htmlFor="name">
                  Name
                </label>
                <Input
                  id="name"
                  placeholder="Your full name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium" htmlFor="email">
                  Email
                </label>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <Button type="submit" disabled={profileLoading}>
                {profileLoading ? "Saving…" : "Save Changes"}
              </Button>
            </form>
          </section>

          {/* Change password */}
          <section className="rounded-lg border border-border bg-card p-6 space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
              Change Password
            </h2>
            {passwordError && <ErrorBanner message={passwordError} />}
            {passwordSuccess && (
              <p className="text-sm text-green-500">Password updated successfully.</p>
            )}
            <form onSubmit={handlePasswordSave} className="space-y-4">
              <div className="space-y-1">
                <label className="text-sm font-medium" htmlFor="current-password">
                  Current Password
                </label>
                <Input
                  id="current-password"
                  type="password"
                  placeholder="••••••••"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium" htmlFor="new-password">
                  New Password
                </label>
                <Input
                  id="new-password"
                  type="password"
                  placeholder="••••••••"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium" htmlFor="confirm-password">
                  Confirm New Password
                </label>
                <Input
                  id="confirm-password"
                  type="password"
                  placeholder="••••••••"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                />
              </div>
              <Button type="submit" disabled={passwordLoading}>
                {passwordLoading ? "Updating…" : "Update Password"}
              </Button>
            </form>
          </section>
          </div>
        </div>
      </main>
    </div>
  );
}
