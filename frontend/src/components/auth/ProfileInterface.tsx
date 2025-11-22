import React from 'react'
import { useAuthStore } from '../../store/authStore'
import { API_BASE_URL } from '../../lib/api'

const ProfileInterface: React.FC = () => {
  const { user, logout } = useAuthStore()

  if (!user) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">You are not signed in.</p>
      </div>
    )
  }

  const handleReconnectGmail = () => {
    const url = `${API_BASE_URL}/auth/google/login?redirect_path=/`
    window.location.href = url
  }

  return (
    <div className="h-full w-full flex items-center justify-center bg-background">
      <div className="max-w-lg w-full mx-4 border border-border rounded-xl bg-card p-6 shadow-sm">
        <h2 className="text-lg font-semibold mb-4 text-foreground">Account</h2>
        <div className="flex items-center gap-4 mb-6">
          {user.picture_url ? (
            <img
              src={user.picture_url}
              alt={user.name}
              className="h-14 w-14 rounded-full border border-border object-cover"
            />
          ) : (
            <div className="h-14 w-14 rounded-full border border-border flex items-center justify-center text-lg font-semibold bg-background">
              {user.name?.charAt(0).toUpperCase() || user.email.charAt(0).toUpperCase()}
            </div>
          )}
          <div>
            <p className="text-sm font-medium text-foreground">{user.name}</p>
            <p className="text-xs text-muted-foreground">{user.email}</p>
          </div>
        </div>

        <div className="space-y-3 mb-6 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Gmail connection</span>
            <span className="text-xs font-medium px-2 py-0.5 rounded-full border border-border bg-background">
              {user.has_gmail_access ? 'Connected' : 'Not connected'}
            </span>
          </div>
          {!user.has_gmail_access && (
            <p className="text-xs text-muted-foreground">
              Connect Gmail to enable email pipelines and Gmail-powered project tracking.
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleReconnectGmail}
              className="inline-flex items-center justify-center rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted"
            >
              {user.has_gmail_access ? 'Refresh Google permissions' : 'Connect Gmail'}
            </button>
          </div>
        </div>

        <div className="border-t border-border pt-4 flex justify-between items-center">
          <p className="text-xs text-muted-foreground">
            Signed in with Google. Closing the browser tab does not fully sign you out.
          </p>
          <button
            type="button"
            onClick={logout}
            className="inline-flex items-center justify-center rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
          >
            Log out
          </button>
        </div>
      </div>
    </div>
  )
}

export default ProfileInterface
