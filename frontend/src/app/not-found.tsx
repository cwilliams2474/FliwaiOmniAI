import Link from "next/link";

export default function NotFound() {
  return (
    <div className="auth">
      <div className="card">
        <h1>Page not found</h1>
        <p className="sub">That address doesn't exist in OmniAI.</p>
        <Link className="btn pri" href="/">Go to overview</Link>
      </div>
    </div>
  );
}
