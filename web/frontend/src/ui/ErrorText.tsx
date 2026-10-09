import { errorMessage } from "../api/errors";

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p className="error" role="alert">
      {errorMessage(error)}
    </p>
  );
}
