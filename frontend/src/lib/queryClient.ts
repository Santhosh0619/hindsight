import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Nothing this phase is genuinely live data yet — later phases override
      // per-query as their data actually needs to be fresh.
      staleTime: 5 * 60 * 1000,
      retry: 1,
    },
  },
});
