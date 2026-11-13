import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Loading } from './components/States'
import AnalyticsPage from './app/analytics/page'
import InboxPage from './app/inbox/page'
import JobDetailPage from './app/jobs/[id]/page'
import LoginPage from './app/login/page'
import MessagesPage from './app/messages/page'
import OnboardingPage from './app/onboarding/page'
import PipelinePage from './app/pipeline/page'
import RunViewerPage from './app/runs/[id]/page'
import RunsPage from './app/runs/page'
import SettingsPage from './app/settings/page'
import StudioPage from './app/studio/[id]/page'
import { useAuth } from './lib/auth'

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <Loading label="Checking your session…" />
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  const { user } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/onboarding" element={<Protected><OnboardingPage /></Protected>} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/jobs/:id" element={<JobDetailPage />} />
        <Route path="/studio/:id" element={<StudioPage />} />
        <Route path="/pipeline" element={<PipelinePage />} />
        <Route path="/messages" element={<MessagesPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:id" element={<RunViewerPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to={user ? (user.onboarded ? '/inbox' : '/onboarding') : '/login'} replace />} />
    </Routes>
  )
}
