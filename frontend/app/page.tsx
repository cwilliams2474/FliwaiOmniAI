import Link from 'next/link';

export default function Home() {
  return (
    <main style={{ padding: 40, maxWidth: 1100, margin: '0 auto' }}>
      <section className="card" style={{ marginTop: 40 }}>
        <h1 style={{ fontSize: 48, marginBottom: 10 }}>FLIWAI OmniAI</h1>
        <p style={{ fontSize: 20, color: '#cbd5e1' }}>
          Your all-in-one AI platform for IT support, business documents, automation, tickets, inventory, and file analysis.
        </p>
        <div style={{ display: 'flex', gap: 12, marginTop: 24 }}>
          <Link href="/dashboard"><button>Open Dashboard</button></Link>
          <Link href="/login"><button>Login</button></Link>
        </div>
      </section>
    </main>
  );
}
