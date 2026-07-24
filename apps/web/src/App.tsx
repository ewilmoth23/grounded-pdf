import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router';
import { Skeleton } from './components/Skeleton';
import { AppLayout } from './layouts/AppLayout';
import { ChatPage } from './pages/ChatPage';
import { DocumentsPage } from './pages/DocumentsPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { SettingsPage } from './pages/SettingsPage';

const PdfViewerPage = lazy(() =>
  import('./pages/PdfViewerPage').then((module) => ({ default: module.PdfViewerPage })),
);

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/documents" replace />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route
          path="documents/:documentId/view"
          element={
            <Suspense
              fallback={
                <div className="flex min-h-dvh flex-col gap-4 bg-ink-100 p-6 dark:bg-ink-950">
                  <Skeleton className="h-12 w-full" label="Loading viewer" />
                  <Skeleton className="mx-auto h-[70vh] w-full max-w-3xl" />
                </div>
              }
            >
              <PdfViewerPage />
            </Suspense>
          }
        />
        <Route path="chat" element={<ChatPage />} />
        <Route path="chat/:conversationId" element={<ChatPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
