import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { API_BASE_URL } from '../lib/api.js'

const AuthContext = createContext(null)

/** FastAPI returns `detail` as a string or a list of validation errors. */
function errorMessage(payload, fallback) {
  const detail = payload?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    return detail[0]?.msg ?? fallback
  }
  return fallback
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const checkAuth = useCallback(async () => {
    try {
      const token = localStorage.getItem('token')
      const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        credentials: 'include',
      })
      if (response.ok) {
        const userData = await response.json()
        setUser(userData)
      } else {
        setUser(null)
        localStorage.removeItem('token')
      }
    } catch (error) {
      console.error('Auth check failed:', error)
      setUser(null)
      localStorage.removeItem('token')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void checkAuth()
  }, [checkAuth])

  const login = async (email, password, rememberMe = false) => {
    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email, password, remember_me: rememberMe }),
    })
    if (!response.ok) {
      const error = await response.json().catch(() => null)
      throw new Error(errorMessage(error, 'Login failed'))
    }
    const data = await response.json()
    if (data.access_token) {
      localStorage.setItem('token', data.access_token)
    }
    setUser(data.user)
    return data
  }

  const register = async (fullName, email, password, confirmPassword, termsAccepted) => {
    const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        full_name: fullName,
        email,
        password,
        confirm_password: confirmPassword,
        terms_accepted: termsAccepted,
      }),
    })
    if (!response.ok) {
      const error = await response.json().catch(() => null)
      throw new Error(errorMessage(error, 'Registration failed'))
    }
    const data = await response.json()
    if (data.access_token) {
      localStorage.setItem('token', data.access_token)
    }
    setUser(data.user)
    return data
  }

  const logout = async () => {
    try {
      await fetch(`${API_BASE_URL}/api/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      })
    } catch (error) {
      console.error('Logout failed:', error)
    }
    localStorage.removeItem('token')
    setUser(null)
  }

  const value = {
    user,
    loading,
    login,
    register,
    logout,
    checkAuth,
    isAuthenticated: !!user,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
