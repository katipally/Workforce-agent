import React from 'react'
import { API_BASE_URL } from '../../lib/api'

const SignInView: React.FC = () => {
  const handleSignIn = () => {
    const redirectPath = window.location.pathname + window.location.search
    const url = `${API_BASE_URL}/auth/google/login?redirect_path=${encodeURIComponent(redirectPath || '/')}`
    window.location.href = url
  }

  return (
    <div className="h-screen w-full flex items-center justify-center bg-background">
      <div className="max-w-md w-full px-6 py-8 border border-border rounded-xl bg-card shadow-sm">
        <h1 className="text-xl font-semibold mb-2 text-foreground text-center">Workforce AI Agent</h1>
        <p className="text-sm text-muted-foreground mb-6 text-center">
          Sign in with Google to use chat, pipelines, projects, and workflows.
        </p>
        <button
          type="button"
          onClick={handleSignIn}
          className="w-full inline-flex items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700"
        >
          <span>Continue with Google</span>
        </button>
      </div>
    </div>
  )
}

export default SignInView
