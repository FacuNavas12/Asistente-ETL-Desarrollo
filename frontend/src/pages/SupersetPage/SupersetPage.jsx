import Layout from "@/components/layout/Layout";

export default function SupersetPage() {
  return (
    <Layout>
      <div style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        flex: 1,
        gap: "12px",
        minHeight: "60vh",
      }}>
        <h1 style={{ fontSize: "72px", fontWeight: 800, margin: 0, color: "var(--text-1)" }}>
          Upss
        </h1>
        <p style={{ fontSize: "18px", color: "var(--text-2)", margin: 0 }}>
          página en mantenimiento
        </p>
      </div>
    </Layout>
  );
}
