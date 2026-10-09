import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { isApiError } from "./api/errors";
import { routerFuture, routes } from "./routes";

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Contract errors (4xx) are final; retry only network/5xx failures once.
        retry: (count, err) => count < 1 && !(isApiError(err) && err.status < 500),
        refetchOnWindowFocus: false,
      },
    },
  });
}

const queryClient = createQueryClient();
const router = createBrowserRouter(routes, { future: routerFuture });

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </QueryClientProvider>
  );
}
