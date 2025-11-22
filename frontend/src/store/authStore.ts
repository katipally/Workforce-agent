import { create } from 'zustand'
import { API_BASE_URL } from '../lib/api'
import { useChatStore } from './chatStore'

export interface AuthUser {
  id: string
  email: string
  name: string
  picture_url?: string | null
  has_gmail_access: boolean
}

interface AuthState {
  user: AuthUser | null
  loading: boolean
  error: string | null
  fetchMe: () => Promise<void>
  logout: () => Promise<void>
  setUser: (user: AuthUser | null) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,
  error: null,
  async fetchMe() {
    try {
      set({ loading: true, error: null })
      const res = await fetch(`${API_BASE_URL}/auth/me`, {
        credentials: 'include',
      })
      if (!res.ok) {
        set({ user: null, loading: false })
        return
      }
      const data = (await res.json()) as AuthUser
      set({ user: data, loading: false })
    } catch (e) {
      console.error('Failed to load auth/me', e)
      set({ user: null, loading: false, error: 'auth_failed' })
    }
  },
  async logout() {
    try {
      await fetch(`${API_BASE_URL}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      })
    } catch (e) {
      console.error('Logout failed', e)
    }
    // Clear user and reset chat state when logging out
    useChatStore.getState().resetStore()
    set({ user: null })
  },
  setUser(user) {
    set((prev) => {
      const prevId = prev.user?.id
      const nextId = user?.id

      // If the logged-in user has changed, reset chat state so history
      // isn't shared between accounts.
      if (prevId && nextId && prevId !== nextId) {
        useChatStore.getState().resetStore()
      }

      // Also reset when transitioning from logged-out to logged-in.
      if (!prevId && nextId) {
        useChatStore.getState().resetStore()
      }

      return { user }
    })
  },
}))
