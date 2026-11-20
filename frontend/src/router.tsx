import type { ComponentType } from 'react';
import { type RouteObject, useParams } from 'react-router';
import { AppShell } from './components/AppShell';
import { RouteError } from './components/RouteError';
import { ClientSelectPage } from './pages/ClientSelectPage';
import { FeedbackPage } from './pages/FeedbackPage';
import { InterviewPage } from './pages/InterviewPage';
import { NotFound } from './pages/NotFound';
import { WrapUpPage } from './pages/WrapUpPage';

/** Gives a session page its id, and a fresh state for each session (keyed by the id). */
function SessionRoute({ page: Page }: { page: ComponentType<{ sessionId: string }> }) {
  const { sessionId = '' } = useParams();
  return <Page key={sessionId} sessionId={sessionId} />;
}

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <ClientSelectPage /> },
      { path: 'interview/:sessionId', element: <SessionRoute page={InterviewPage} /> },
      { path: 'wrapup/:sessionId', element: <SessionRoute page={WrapUpPage} /> },
      { path: 'feedback/:sessionId', element: <SessionRoute page={FeedbackPage} /> },
      { path: '*', element: <NotFound /> },
    ],
  },
];
