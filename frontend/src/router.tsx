import type { RouteObject } from 'react-router';
import { AppShell } from './components/AppShell';
import { RouteError } from './components/RouteError';
import { ClientSelectPage } from './pages/ClientSelectPage';
import { NotFound } from './pages/NotFound';

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <ClientSelectPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
];
