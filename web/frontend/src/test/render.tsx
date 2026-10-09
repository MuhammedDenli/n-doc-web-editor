import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { routerFuture, routes } from "../routes";

/** Render the whole app (real routes, MSW API) at `path`. */
export function renderApp(path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path], future: routerFuture });
  const result = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </QueryClientProvider>,
  );
  return { ...result, router, client };
}
