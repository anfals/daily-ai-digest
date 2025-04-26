import React, { useState } from "react";

function App() {
  const [topic, setTopic] = useState("");
  const [phone, setPhone] = useState("");
  const [status, setStatus] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus("Sending...");
    const resp = await fetch("http://localhost:8000/api/digest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, phone_number: phone })
    });
    const data = await resp.json();
    if (data.status === "digest_sent" || data.status === "received") {
      setStatus("Request received! You'll get a text soon.");
    } else {
      setStatus("Error. Try again.");
    }
  };

  return (
    <div style={{ maxWidth: 400, margin: "80px auto", padding: 24, border: "1px solid #ccc", borderRadius: 8 }}>
      <h2>Daily News Digest</h2>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 12 }}>
          <input
            type="text"
            value={topic}
            onChange={e => setTopic(e.target.value)}
            placeholder="Enter topic (e.g. AI, sports)"
            required
            style={{ width: "100%", padding: 8 }}
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <input
            type="tel"
            value={phone}
            onChange={e => setPhone(e.target.value)}
            placeholder="Enter phone number"
            required
            style={{ width: "100%", padding: 8 }}
          />
        </div>
        <button type="submit" style={{ width: "100%", padding: 10 }}>
          Get My Digest
        </button>
      </form>
      <div style={{ marginTop: 16 }}>{status}</div>
    </div>
  );
}

export default App;
