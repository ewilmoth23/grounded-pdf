import type { ApiError } from '../api/client';

declare module '@tanstack/react-query' {
  interface Register {
    defaultError: ApiError;
  }
}
