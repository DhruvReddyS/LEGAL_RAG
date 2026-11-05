"use client";

import { useEffect } from "react";

/** A screen that throws must not leave a white page with no way forward. */
export default function ErrorScreen({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error(error); }, [error]);
  return (
    <main className="error-screen">
      <div>
        <h1>This screen could not be shown.</h1>
        <p>Nothing you saved has been lost. Try again, and if it happens a second time, reload the page.</p>
        <div className="error-screen-actions">
          <button type="button" className="button-primary" onClick={reset}>Try again</button>
          <a className="button-secondary" href="/">Back to the start</a>
        </div>
      </div>
    </main>
  );
}
