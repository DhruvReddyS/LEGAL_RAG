import Link from "next/link";

export default function NotFound() {
  return (
    <main className="error-screen">
      <div>
        <h1>There is no page at this address.</h1>
        <p>It may have moved, or the address may be mistyped.</p>
        <div className="error-screen-actions">
          <Link className="button-primary" href="/">Back to the start</Link>
        </div>
      </div>
    </main>
  );
}
