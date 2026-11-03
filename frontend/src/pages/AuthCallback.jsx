/**
 * OAuth Authentication Callback handler.
 * Processes Google and GitHub OAuth redirects, validates session token, and updates user auth state.
 */
import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import LoadingIndicator from '../components/LoadingIndicator.jsx'

export default function AuthCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { checkAuth } = useAuth()
  const token = searchParams.get('token')

  useEffect(() => {
    if (token) {
      localStorage.setItem('token', token)
      checkAuth().then(() => {
        navigate('/')
      })
    } else {
      navigate('/login')
    }
  }, [token, navigate, checkAuth])

  return (
    <div className="min-h-screen flex items-center justify-center bg-ink-950">
      <LoadingIndicator label="Signing in" description="Completing authentication..." />
    </div>
  )
}
